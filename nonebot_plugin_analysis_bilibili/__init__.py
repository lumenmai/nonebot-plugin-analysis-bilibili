import re
from typing import List, Union
from aiohttp import ClientSession, ClientTimeout
from nonebot import on_regex, logger, require, on_message, on_command
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN, GROUP_OWNER
from nonebot.permission import SUPERUSER
from nonebot.rule import Rule
from nonebot.plugin import PluginMetadata
from .analysis_bilibili import (
    analysis_request_timeout,
    b23_extract,
    bili_keyword,
    config,
    search_bili_by_title,
)
from .card_parse_config import (
    can_parse_card,
    is_global_card_parse_enabled,
    set_global_card_parse,
    set_group_card_parse,
)

require("nonebot_plugin_saa")
from nonebot_plugin_saa import (  # noqa: E402
    MessageFactory,
    MessageSegmentFactory,
    Text,
    Image,
)

__plugin_meta__ = PluginMetadata(
    name="analysis_bilibili",
    description="自动解析bilibili链接内容",
    usage="""
        自动解析bilibili文本链接内容
        启用b站卡片解析：启用本群B站卡片解析
        禁用b站卡片解析：禁用本群B站卡片解析
    """.strip(),
    type="application",
    homepage="https://github.com/mengshouer/nonebot_plugin_analysis_bilibili",
)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Origin": "https://www.bilibili.com",
    "Referer": "https://www.bilibili.com/",
}

whitelist = [str(i) for i in getattr(config, "analysis_whitelist", [])]
group_whitelist = [str(i) for i in getattr(config, "analysis_group_whitelist", [])]
blacklist = [str(i) for i in getattr(config, "analysis_blacklist", [])]
group_blacklist = [str(i) for i in getattr(config, "analysis_group_blacklist", [])]
desc_blacklist = [str(i) for i in getattr(config, "analysis_desc_blacklist", [])]
trust_env = getattr(config, "analysis_trust_env", False)
enable_search = getattr(config, "analysis_enable_search", False)
use_on_message = getattr(config, "analysis_use_on_message", False)
card_segment_types = {"json", "xml"}


async def is_enable_search() -> bool:
    return enable_search


async def is_normal(event: Event) -> bool:
    user_id = str(event.get_user_id())
    group_id = str(
        event.group_id
        if hasattr(event, "group_id")
        else event.channel_id
        if hasattr(event, "channel_id")
        else None
    )

    if user_id in whitelist or group_id in group_whitelist:
        return True

    if len(whitelist) > 0 or len(group_whitelist) > 0:
        return False

    if user_id in blacklist or group_id in group_blacklist:
        return False

    return True


pattern = (
    r"^(?:(?:av|cv)\d+|BV[a-zA-Z0-9]{10})|"
    r"(?:b23\.tv|bili(?:22|23|33|2233)\.cn|\.bilibili\.com|QQ小程序(?:&amp;#93;|&#93;|\])哔哩哔哩).{0,500}"
)

if use_on_message:
    analysis_bili = on_message(rule=is_normal, block=False, priority=11)
else:
    analysis_bili = on_regex(pattern, rule=is_normal, block=False, priority=11)


rule = Rule(is_enable_search, is_normal)
search_bili = on_regex(r"^搜视频.*", rule=rule)
enable_card_parse = on_command(
    "启用b站卡片解析",
    aliases={"启用B站卡片解析"},
    permission=SUPERUSER | GROUP_ADMIN | GROUP_OWNER,
    block=True,
    priority=5,
)
disable_card_parse = on_command(
    "禁用b站卡片解析",
    aliases={"禁用B站卡片解析"},
    permission=SUPERUSER | GROUP_ADMIN | GROUP_OWNER,
    block=True,
    priority=5,
)


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".jfif", ".webp")


def is_image(msg: str) -> bool:
    return msg.startswith(("http://", "https://")) and msg.lower().endswith(
        IMAGE_EXTENSIONS
    )


def flatten(container):
    for i in container:
        if isinstance(i, (list, tuple)):
            yield from flatten(i)
        else:
            yield i


def format_msg(msg_list: List[Union[List[str], str]], is_plain_text: bool = False):
    flatten_msg_list = list(flatten(msg_list))
    if is_plain_text:
        return "".join([i for i in flatten_msg_list if not is_image(i)])

    msg: List[MessageSegmentFactory] = []

    for i in flatten_msg_list:
        if not i:
            continue
        elif is_image(i):
            msg.append(Image(i))
        else:
            msg.append(Text(i))
    return msg


def get_event_group_id(event: Event) -> str | None:
    if isinstance(event, GroupMessageEvent):
        return str(event.group_id)
    if hasattr(event, "group_id"):
        return str(event.group_id)
    if hasattr(event, "channel_id"):
        return str(event.channel_id)
    return None


def get_analysis_text(event: Event) -> str:
    message = event.get_message()
    group_id = get_event_group_id(event)
    msg_list = []

    for segment in message:
        if segment.type == "text":
            msg_list.append(str(segment.data.get("text", "")))
        elif segment.type in card_segment_types and can_parse_card(group_id):
            msg_list.append(str(segment))

    return "".join(msg_list)


async def send_msg(msg_list: List[Union[List[str], str, bool]]) -> None:
    if msg_list is False:
        return
    if not msg_list:
        logger.warning("此次解析的内容为空，接口可能被修改，需要更新！")
        return

    try:
        await MessageFactory(format_msg(msg_list)).send()
    except RuntimeError:
        await analysis_bili.send(format_msg(msg_list, is_plain_text=True))
    except Exception as e:
        logger.exception(e)
        logger.warning(f"错误的内容：{msg_list}\n此次解析的内容可能被风控！")


async def get_msg(
    event: Event, text: str, search: bool = False
) -> Union[List[str], bool]:
    group_id = get_event_group_id(event)

    timeout = ClientTimeout(total=analysis_request_timeout)
    async with ClientSession(
        trust_env=trust_env, headers=headers, timeout=timeout
    ) as session:
        if search:
            text = await search_bili_by_title(text, session=session)
        else:
            if re.search(r"(b23.tv)|(bili(22|23|33|2233).cn)", text, re.I):
                # 提前处理短链接，避免解析到其他的
                text = await b23_extract(text, session=session)

        msg = await bili_keyword(group_id, text, session=session)

    if msg:
        if isinstance(msg, str):
            # 说明是错误信息
            await analysis_bili.finish(msg)

        if group_id in desc_blacklist:
            if msg[-1].startswith("简介"):
                msg[-1] = ""

    return msg


@analysis_bili.handle()
async def handle_analysis(event: Event) -> None:
    message = event.get_message()
    # 不解析转发消息，可能会过长导致匹配时间过长
    for segment in message:
        if segment.type == "forward":
            logger.debug("analysis_bilibili 忽略转发消息")
            return

    text = get_analysis_text(event)
    if not re.search(pattern, text):
        return
    # on_regex
    msg = await get_msg(event, text)
    await send_msg(msg)


@search_bili.handle()
async def handle_search(event: Event) -> None:
    msg = await get_msg(event, str(event.get_message())[3:].strip(), search=True)
    await send_msg(msg)


@enable_card_parse.handle()
async def handle_enable_card_parse(event: Event) -> None:
    if isinstance(event, PrivateMessageEvent):
        set_global_card_parse(True)
        await enable_card_parse.finish(
            "已启用B站卡片解析全局总开关，已启用的群局部设置将生效。"
        )

    if isinstance(event, GroupMessageEvent):
        group_id = str(event.group_id)
        set_group_card_parse(group_id, True)
        if is_global_card_parse_enabled():
            await enable_card_parse.finish("已启用本群B站卡片解析。")
        await enable_card_parse.finish(
            "已记录启用本群B站卡片解析，但全局总开关当前关闭，需要超管私聊启用。"
        )

    await enable_card_parse.finish("当前会话不支持设置B站卡片解析。")


@disable_card_parse.handle()
async def handle_disable_card_parse(event: Event) -> None:
    if isinstance(event, PrivateMessageEvent):
        set_global_card_parse(False)
        await disable_card_parse.finish(
            "已禁用B站卡片解析全局总开关，群局部设置已保留。"
        )

    if isinstance(event, GroupMessageEvent):
        set_group_card_parse(str(event.group_id), False)
        await disable_card_parse.finish("已禁用本群B站卡片解析。")

    await disable_card_parse.finish("当前会话不支持设置B站卡片解析。")
