from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import CookieJar
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageSegment,
    PrivateMessageEvent,
)
from nonebot.exception import FinishedException
import pytest
from yarl import URL

from test_api import FakeResponse, FakeSession


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://www.bilibili.com/opus/12345", "/opus/detail?id=12345"),
        ("https://m.bilibili.com/dynamic/12345", "/detail?id=12345"),
        ("https://t.bilibili.com/12345", "/detail?id=12345"),
        ("https://www.bilibili.com/video/BV1234567890", "view?bvid=BV1234567890"),
        ("https://live.bilibili.com/12345", "getInfoByRoom?room_id=12345"),
        ("abcBV1234567890xyz", ""),
        ("have12345", ""),
        ("https://example.test", ""),
    ],
)
def test_link_routes_and_boundaries(analysis_module, text, expected):
    url, _, _ = analysis_module.extract(text)
    assert url.endswith(expected) if expected else url == ""


def test_cache_expires_without_timer_threads(monkeypatch):
    from nonebot_plugin_analysis_bilibili import ExpiringCache as module

    clock = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    cache = module.ExpiringCache(10)
    cache.set("first")
    clock[0] = 105
    cache.set("second")
    assert cache.get("first") == "first"
    clock[0] = 110
    assert cache.get("first") is None
    assert cache.get("second") == "second"
    clock[0] = 116
    cache.set("third")
    assert set(cache.cache) == {"third"}


def test_default_cache_remembers_only_last_link():
    from nonebot_plugin_analysis_bilibili.ExpiringCache import ExpiringCache

    cache = ExpiringCache(0)
    cache.set("first")
    cache.set("second")
    assert cache.get("first") is None
    assert cache.get("second") == "second"


def test_only_one_analysis_listener_is_registered(init_plugin):
    import nonebot_plugin_analysis_bilibili as plugin

    handlers = [
        matcher
        for matcher in init_plugin.matcher
        if any(handler.call is plugin.handle_analysis for handler in matcher.handlers)
    ]
    assert handlers == [plugin.analysis_bili]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://img.test/a.jpeg", True),
        ("https://img.test/a.JPG", True),
        ("https://img.test/a.webp", True),
        ("https://img.test/a.jfif", True),
        ("a.jpeg", False),
        ("一段正文.jpg", False),
        ("", False),
    ],
)
def test_images_require_url_and_full_extension(value, expected):
    import nonebot_plugin_analysis_bilibili as plugin

    assert plugin.is_image(value) is expected


@pytest.mark.parametrize(
    ("global_on", "group_on", "expected"),
    [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_card_switch_requires_both_scopes(global_on, group_on, expected):
    from nonebot_plugin_analysis_bilibili import card_parse_config as cards

    cards.set_global_card_parse(global_on)
    cards.set_group_card_parse("20001", group_on)
    assert cards.can_parse_card("20001") is expected
    assert cards.can_parse_card(None) is False
    assert cards.can_parse_card("another-group") is False
    cards.data = {}
    assert cards.can_parse_card("20001") is expected


def test_disabling_cards_keeps_plain_links():
    import nonebot_plugin_analysis_bilibili as plugin

    event = Mock(spec=GroupMessageEvent)
    event.group_id = 20001
    event.get_message.return_value = Message(
        "https://www.bilibili.com/video/BV1234567890"
    ) + MessageSegment.json("card-link")
    assert (
        plugin.get_analysis_text(event) == "https://www.bilibili.com/video/BV1234567890"
    )


@pytest.mark.parametrize("private", [True, False])
async def test_enable_command_preserves_global_and_group_scopes(private, monkeypatch):
    import nonebot_plugin_analysis_bilibili as plugin
    from nonebot_plugin_analysis_bilibili import card_parse_config as cards

    event = Mock(spec=PrivateMessageEvent if private else GroupMessageEvent)
    event.group_id = 20001
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(plugin.enable_card_parse, "finish", finish)
    with pytest.raises(FinishedException):
        await plugin.handle_enable_card_parse(event)
    assert cards.is_global_card_parse_enabled() is private
    assert cards.is_group_card_parse_enabled("20001") is (not private)


async def test_voucher_is_not_treated_as_success(analysis_module, monkeypatch):
    session = FakeSession(
        FakeResponse(
            status=200,
            content_type="application/json",
            payload={"code": 0, "data": {"v_voucher": "validation"}},
        )
    )
    monkeypatch.setattr(analysis_module, "init_cookie", AsyncMock())
    assert (
        await analysis_module.fetch_api(session, "https://example.test", retry=1)
        is None
    )


async def test_retry_preserves_ticket_and_replaces_risky_fingerprint(
    analysis_module, monkeypatch
):
    session = FakeSession(
        FakeResponse(status=429, content_type="application/json", payload={"code": 0}),
        FakeResponse(
            status=200,
            content_type="application/json",
            payload={"code": 0, "data": {"ok": True}},
        ),
    )
    session.cookie_jar = CookieJar()
    session.cookie_jar.update_cookies(
        {"bili_ticket": "ticket", "buvid3": "old", "SESSDATA": "expired"}
    )
    analysis_module._cached_spi_cookies.update({"buvid3": "old"})
    init = AsyncMock()
    monkeypatch.setattr(analysis_module, "init_cookie", init)
    monkeypatch.setattr(analysis_module.asyncio, "sleep", AsyncMock())
    result = await analysis_module.fetch_api(session, "https://example.test")
    assert result["data"]["ok"]
    assert analysis_module._cached_spi_cookies == {}
    assert set(session.cookie_jar.filter_cookies(URL("https://api.bilibili.com"))) == {
        "bili_ticket"
    }
    assert init.await_args_list[0].kwargs == {"use_config": True}
    assert init.await_args_list[1].kwargs == {"use_config": False}


async def test_search_warms_main_site_and_reuses_session(analysis_module, monkeypatch):
    session = FakeSession(FakeResponse(status=200, content_type="text/html"))
    session.cookie_jar = CookieJar()
    query = AsyncMock(return_value="keyword=test&w_rid=signature")
    ticket = AsyncMock(return_value="search-ticket")
    fetch = AsyncMock(
        return_value={
            "code": 0,
            "data": {
                "result": [
                    {"result_type": "video", "data": [{"arcurl": "https://video.test"}]}
                ]
            },
        }
    )
    monkeypatch.setattr(analysis_module, "get_query", query)
    monkeypatch.setattr(analysis_module, "get_ticket", ticket)
    monkeypatch.setattr(analysis_module, "fetch_api", fetch)
    assert (
        await analysis_module.search_bili_by_title("test", session)
        == "https://video.test"
    )
    assert session.requested_urls == ["https://www.bilibili.com"]
    query.assert_awaited_once_with({"keyword": "test"}, session=session)
    ticket.assert_awaited_once_with(session=session)
    assert fetch.await_args.kwargs == {
        "headers": {"Referer": "https://search.bilibili.com/"}
    }
    assert (
        session.cookie_jar.filter_cookies(URL("https://api.bilibili.com"))[
            "bili_ticket"
        ].value
        == "search-ticket"
    )


async def test_wbi_cache_and_existing_session(monkeypatch):
    from nonebot_plugin_analysis_bilibili import wbi

    clock = [10.0]
    monkeypatch.setattr(wbi.time, "monotonic", lambda: clock[0])
    response = FakeResponse(
        status=200,
        content_type="application/json",
        payload={
            "data": {
                "wbi_img": {
                    "img_url": "https://img.test/" + "a" * 32 + ".png",
                    "sub_url": "https://img.test/" + "b" * 32 + ".png",
                }
            }
        },
    )
    session = SimpleNamespace(get=Mock(return_value=response))
    monkeypatch.setattr(
        wbi, "ClientSession", Mock(side_effect=AssertionError("extra session"))
    )
    first = await wbi.getWbiKeys(session)
    assert await wbi.getWbiKeys(session) == first
    assert session.get.call_count == 1
    clock[0] = 3611
    assert await wbi.getWbiKeys(session) == first
    assert session.get.call_count == 2
    params = {"keyword": "test"}
    wbi.encWbi(params, *first)
    assert params == {"keyword": "test"}


async def test_ticket_cache_and_existing_session(monkeypatch):
    from nonebot_plugin_analysis_bilibili import wbi

    clock = [10.0]
    monkeypatch.setattr(wbi.time, "monotonic", lambda: clock[0])
    response = FakeResponse(
        status=200,
        content_type="application/json",
        payload={"code": 0, "data": {"ticket": "valid-ticket"}},
    )
    session = SimpleNamespace(post=Mock(return_value=response))
    monkeypatch.setattr(
        wbi, "ClientSession", Mock(side_effect=AssertionError("extra session"))
    )
    assert await wbi.get_ticket(session) == "valid-ticket"
    assert await wbi.get_ticket(session) == "valid-ticket"
    assert session.post.call_count == 1
    clock[0] = 3611
    assert await wbi.get_ticket(session) == "valid-ticket"
    assert session.post.call_count == 2


async def test_invalid_ticket_is_not_cached():
    from nonebot_plugin_analysis_bilibili import wbi

    response = FakeResponse(
        status=412, content_type="application/json", payload={"code": -412}
    )
    with pytest.raises(RuntimeError):
        await wbi.get_ticket(SimpleNamespace(post=Mock(return_value=response)))
    assert wbi._ticket_cache is None


async def test_opus_outputs_body_and_pictures(analysis_module, monkeypatch):
    payload = {
        "code": 0,
        "data": {
            "item": {
                "id_str": "12345",
                "modules": [
                    {
                        "module_type": "MODULE_TYPE_TITLE",
                        "module_title": {"text": "标题"},
                    },
                    {
                        "module_type": "MODULE_TYPE_CONTENT",
                        "module_content": {
                            "paragraphs": [
                                {"text": {"nodes": [{"word": {"words": "正文"}}]}},
                                {"pic": {"pics": [{"url": "https://img.test/a.jpeg"}]}},
                            ]
                        },
                    },
                ],
            }
        },
    }
    monkeypatch.setattr(analysis_module, "fetch_api", AsyncMock(return_value=payload))
    message, url = await analysis_module.opus_detail("https://api.test", object())
    assert "12345" in url
    assert "正文" in message
    assert message[0] == ["https://img.test/a.jpeg"]


async def test_dynamic_falls_back_to_desktop_api(analysis_module, monkeypatch):
    desktop = {
        "code": 0,
        "data": {
            "item": {
                "id_str": "12345",
                "type": "DYNAMIC_TYPE_WORD",
                "modules": [
                    {
                        "module_type": "MODULE_TYPE_DESC",
                        "module_desc": {"text": "桌面正文"},
                    },
                ],
            }
        },
    }
    fetch = AsyncMock(side_effect=[None, desktop])
    monkeypatch.setattr(analysis_module, "fetch_api", fetch)
    message, url = await analysis_module.dynamic_detail(
        "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail?id=12345", object()
    )
    assert message[0] == "桌面正文"
    assert "/desktop/v1/detail" in fetch.await_args_list[1].args[1]


async def test_bili_keyword_prefers_opus_but_can_fall_back(
    analysis_module, monkeypatch
):
    opus = AsyncMock(return_value=(None, None))
    dynamic = AsyncMock(return_value=(["动态正文"], "https://t.bilibili.com/12345"))
    monkeypatch.setattr(analysis_module, "opus_detail", opus)
    monkeypatch.setattr(analysis_module, "dynamic_detail", dynamic)
    result = await analysis_module.bili_keyword(
        "group", "https://www.bilibili.com/opus/12345", object()
    )
    assert result == ["动态正文"]
    assert "/opus/detail" in opus.await_args.args[0]
    assert "/opus/detail" not in dynamic.await_args.args[0]
