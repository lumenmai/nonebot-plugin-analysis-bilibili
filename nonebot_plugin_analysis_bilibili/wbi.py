from functools import reduce
from hashlib import md5
import hashlib
import hmac
import urllib.parse
import time
from aiohttp import ClientSession, ClientTimeout

# doc: https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign/wbi.md

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.bilibili.com/",
}
CACHE_TTL = 3600
_wbi_cache: tuple[str, str, float] | None = None
_ticket_cache: tuple[str, float] | None = None

# fmt: off
mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]
# fmt: on


def getMixinKey(orig: str):
    "对 imgKey 和 subKey 进行字符顺序打乱编码"
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, "")[:32]


def encWbi(params: dict, img_key: str, sub_key: str):
    "为请求参数进行 wbi 签名"
    mixin_key = getMixinKey(img_key + sub_key)
    curr_time = round(time.time())
    params = dict(params)
    params["wts"] = curr_time  # 添加 wts 字段
    params = dict(sorted(params.items()))  # 按照 key 重排参数
    # 过滤 value 中的 "!'()*" 字符
    params = {
        k: "".join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)  # 序列化参数
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()  # 计算 w_rid
    params["w_rid"] = wbi_sign
    return params


async def _get_wbi_keys(session: ClientSession):
    async with session.get("https://api.bilibili.com/x/web-interface/nav") as resp:
        try:
            json_content = await resp.json(content_type=None)
        except Exception as e:
            content_type = resp.headers.get("Content-Type", "unknown")
            raise RuntimeError(
                f"WBI密钥接口返回非JSON响应 "
                f"(HTTP {resp.status} / Content-Type {content_type})"
            ) from e

    data = json_content.get("data") if isinstance(json_content, dict) else None
    wbi_img = (data or {}).get("wbi_img") or {}
    img_url = wbi_img.get("img_url")
    sub_url = wbi_img.get("sub_url")
    if not img_url or not sub_url:
        code = json_content.get("code") if isinstance(json_content, dict) else None
        raise RuntimeError(
            f"WBI密钥接口缺少必要字段 (HTTP {resp.status} / code {code})"
        )

    img_key = img_url.rsplit("/", 1)[1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]
    return img_key, sub_key


async def getWbiKeys(session: ClientSession = None):
    "获取最新的 img_key 和 sub_key"
    global _wbi_cache
    now = time.monotonic()
    if _wbi_cache and now < _wbi_cache[2]:
        return _wbi_cache[0], _wbi_cache[1]
    if session is not None:
        img_key, sub_key = await _get_wbi_keys(session)
    else:
        async with ClientSession(
            headers=headers, timeout=ClientTimeout(total=15)
        ) as own_session:
            img_key, sub_key = await _get_wbi_keys(own_session)
    _wbi_cache = (img_key, sub_key, time.monotonic() + CACHE_TTL)
    return img_key, sub_key


def hmac_sha256(key: str, message: str) -> str:
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


async def _get_ticket(session: ClientSession) -> str:
    ts = int(time.time())
    params = {
        "key_id": "ec02",
        "hexsign": hmac_sha256("XgwSnGZ1p", f"ts{ts}"),
        "context[ts]": str(ts),
        "csrf": "",
    }
    async with session.post(
        "https://api.bilibili.com/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket",
        params=params,
    ) as resp:
        content = await resp.json(content_type=None)
        data = content.get("data") if isinstance(content, dict) else None
        ticket = (data or {}).get("ticket")
        if not ticket or resp.status != 200 or content.get("code") != 0:
            code = content.get("code") if isinstance(content, dict) else None
            raise RuntimeError(
                f"B站 ticket 获取失败 (HTTP {resp.status} / code {code})"
            )
    return ticket


async def get_ticket(session: ClientSession = None) -> str:
    """获取搜索使用的 ticket，成功结果缓存一小时。"""
    global _ticket_cache
    now = time.monotonic()
    if _ticket_cache and now < _ticket_cache[1]:
        return _ticket_cache[0]
    if session is not None:
        ticket = await _get_ticket(session)
    else:
        async with ClientSession(
            headers=headers, timeout=ClientTimeout(total=15)
        ) as own_session:
            ticket = await _get_ticket(own_session)
    _ticket_cache = (ticket, time.monotonic() + CACHE_TTL)
    return ticket


async def get_query(params: dict, session: ClientSession = None):
    """
    获取签名后的查询参数
    """
    img_key, sub_key = await getWbiKeys(session)
    signed_params = encWbi(params=params, img_key=img_key, sub_key=sub_key)
    query = urllib.parse.urlencode(signed_params)
    return query
