from collections import deque
from importlib import import_module
from unittest.mock import AsyncMock

from aiohttp import CookieJar
import pytest
from yarl import URL


class FakeCookieJar:
    def __init__(self) -> None:
        self.clear_count = 0

    def filter_cookies(self, url):
        return {}

    def clear(self) -> None:
        self.clear_count += 1


class FakeResponse:
    def __init__(
        self,
        *,
        status: int,
        content_type: str,
        payload: object = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.payload = payload
        self.json_error = json_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def json(self, *, content_type=None):
        if self.json_error:
            raise self.json_error
        return self.payload


class FakeSession:
    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = deque(responses)
        self.cookie_jar = FakeCookieJar()
        self.requested_urls: list[str] = []

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.requested_urls.append(url)
        return self.responses.popleft()


@pytest.fixture
def analysis_module():
    return import_module("nonebot_plugin_analysis_bilibili.analysis_bilibili")


async def test_fetch_api_returns_json_response(analysis_module, monkeypatch) -> None:
    session = FakeSession(
        FakeResponse(
            status=200,
            content_type="application/json",
            payload={"code": 0, "data": {"title": "ok"}},
        )
    )
    monkeypatch.setattr(analysis_module, "init_cookie", AsyncMock())

    result = await analysis_module.fetch_api(session, "https://example.test", retry=1)

    assert result == {"code": 0, "data": {"title": "ok"}}
    assert session.requested_urls == ["https://example.test"]


async def test_init_cookie_fetches_anonymous_buvid(
    analysis_module, monkeypatch
) -> None:
    session = FakeSession(
        FakeResponse(
            status=200,
            content_type="application/json",
            payload={"code": 0, "data": {"b_3": "buvid-3", "b_4": "buvid-4"}},
        )
    )
    session.cookie_jar = CookieJar()
    monkeypatch.setattr(analysis_module, "analysis_bilibili_cookie", "")

    await analysis_module.init_cookie(session)

    cookies = session.cookie_jar.filter_cookies(URL("https://api.bilibili.com/"))
    assert cookies["buvid3"].value == "buvid-3"
    assert cookies["buvid4"].value == "buvid-4"


async def test_fetch_api_handles_http_412_html_and_retries(
    analysis_module, monkeypatch
) -> None:
    responses = [
        FakeResponse(
            status=412,
            content_type="text/html; charset=utf-8",
            json_error=ValueError("not json"),
        )
        for _ in range(2)
    ]
    session = FakeSession(*responses)
    monkeypatch.setattr(analysis_module, "init_cookie", AsyncMock())
    sleep = AsyncMock()
    monkeypatch.setattr(analysis_module.asyncio, "sleep", sleep)

    result = await analysis_module.fetch_api(session, "https://example.test")

    assert result is None
    assert len(session.requested_urls) == 2
    assert session.cookie_jar.clear_count == 1
    sleep.assert_awaited_once_with(1)


async def test_fetch_api_handles_json_risk_code(analysis_module, monkeypatch) -> None:
    session = FakeSession(
        FakeResponse(
            status=200,
            content_type="application/json",
            payload={"code": -412, "message": "请求被拦截"},
        )
    )
    monkeypatch.setattr(analysis_module, "init_cookie", AsyncMock())

    result = await analysis_module.fetch_api(session, "https://example.test", retry=1)

    assert result is None


async def test_video_detail_returns_readable_message_when_api_is_unavailable(
    analysis_module, monkeypatch
) -> None:
    fetch_api = AsyncMock(return_value=None)
    monkeypatch.setattr(analysis_module, "fetch_api", fetch_api)

    message, video_url = await analysis_module.video_detail(
        "https://api.bilibili.com/x/web-interface/view?bvid=BV1234567890",
        session=object(),
    )

    assert "安全风控" in message
    assert "ContentTypeError" not in message
    assert video_url is None


def test_parse_cookie_ignores_invalid_items(analysis_module) -> None:
    assert analysis_module.parse_cookie("SESSDATA=abc; invalid; buvid3=xyz=") == {
        "SESSDATA": "abc",
        "buvid3": "xyz=",
    }
