# B站解析

自动解析 B站视频、番剧、直播、专栏及动态链接，发送标题、封面、正文等信息。支持新版 opus 图文和手机动态分享链接，并可分别控制各群的卡片解析。

## 运行环境

Python 3.10 或更高版本，NoneBot2、OneBot V11、SAA 和 Localstore。可放入[绪山真寻](https://github.com/zhenxun-org/zhenxun_bot)使用，依赖详见 `requirements.txt`。

## 安装

### 方式一：放入真寻插件目录

下载本仓库，将其中的 `nonebot_plugin_analysis_bilibili/` 目录复制到 `zhenxun/plugins/`。在运行真寻的虚拟环境中安装仓库根目录 `requirements.txt` 中的依赖，然后重启真寻。

### 方式二：通过外部目录加载

下载本仓库到自选位置，安装 `requirements.txt` 中的依赖。在真寻实际使用的环境配置文件中，将仓库根目录追加到 `EXT_PATH`，例如：

```dotenv
EXT_PATH=["/path/to/插件仓库"]
```

保留已有的其他路径，保存配置后重启真寻。

## 使用

私聊或群聊发送 B站链接即可解析，包括 `b23.tv` 短链接、BV/av 视频号、番剧、直播、专栏、动态及 `/opus/` 图文链接。群内 JSON/XML 卡片由下面的双开关控制。

启用 `analysis_enable_search` 后，可发送 `搜视频 关键词`，返回第一个视频结果。

图片按消息能力发送，遇到不支持的发送环境时尝试回退纯文本。合并转发消息会跳过。

## 卡片解析开关

**全局总开关与群开关默认均关闭，两者都开启时才解析该群的卡片。** 文本链接仍正常解析，私聊卡片不在群卡片开关的处理范围内。

| 操作位置 | 权限 | 命令 | 作用 |
|---|---|---|---|
| 私聊机器人 | NoneBot 超级用户 | `启用b站卡片解析` | 打开全局总开关 |
| 私聊机器人 | NoneBot 超级用户 | `禁用b站卡片解析` | 关闭全局总开关，保留各群设置 |
| 群聊 | 群主、群管理员或超级用户 | `启用b站卡片解析` | 打开当前群的卡片开关 |
| 群聊 | 群主、群管理员或超级用户 | `禁用b站卡片解析` | 关闭当前群的卡片开关 |

命令中的 `b站` 也可写为 `B站`。先打开群开关、后打开全局开关同样生效。用户和群黑白名单仍会限制解析范围。

## 配置

在运行真寻实际使用的环境配置文件中设置以下可选项，保存后重启：

```dotenv
ANALYSIS_DISPLAY_IMAGE=true
ANALYSIS_ENABLE_SEARCH=false
ANALYSIS_REQUEST_TIMEOUT=15
ANALYSIS_REANALYSIS_TIME=0
```

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `analysis_display_image` | `true` | 显示封面和动态图片 |
| `analysis_display_image_list` | `[]` | 总图片开关关闭时，可指定显示图片的类型：`video`、`bangumi`、`live`、`article`、`dynamic` |
| `analysis_images_size` | 空字符串 | 图片尺寸，例如 `100w`、`100h`、`100h_100w` |
| `analysis_cover_images_size` | 空字符串 | 视频、番剧、直播封面尺寸，优先于通用尺寸 |
| `analysis_whitelist` | `[]` | 允许解析的用户 ID 列表 |
| `analysis_group_whitelist` | `[]` | 允许解析的群 ID 列表 |
| `analysis_blacklist` | `[]` | 不解析的用户 ID 列表 |
| `analysis_group_blacklist` | `[]` | 不解析的群 ID 列表 |
| `analysis_desc_blacklist` | `[]` | 解析结果省略末尾简介的群 ID 列表 |
| `analysis_reanalysis_time` | `0` | 群内重复解析间隔，单位秒；0 时只记住最近一条，正数时同时记录窗口内多条链接 |
| `analysis_enable_search` | `false` | 启用 `搜视频` |
| `analysis_use_on_message` | `false` | 使用消息监听器替代正则监听器，两种模式均只注册一次解析处理 |
| `analysis_trust_env` | `false` | 使用系统环境中的代理配置 |
| `analysis_request_timeout` | `15` | 每个 HTTP 请求的超时秒数，最小为 1；无效配置回退 15 秒 |
| `analysis_bilibili_cookie` | 空字符串 | 可选 B站 Cookie，从部署环境读取 |

设置任一白名单后，优先按用户白名单或群白名单放行，黑名单不再参与判断。ID 支持字符串或整数列表，例如 `ANALYSIS_GROUP_WHITELIST=[123456789]`。

Cookie 可使用 `.env` 中的 `ANALYSIS_BILIBILI_COOKIE` 配置。请把实际登录 Cookie 保存在自己的部署配置中；本仓库仅包含读取逻辑。

接口遇到 HTTP 412/429、业务风控错误码、验证凭据或非 JSON 响应时会有限重试，视频接口持续不可用时返回可读提示。搜索使用主站 Cookie、ticket 和 WBI 签名；密钥与 ticket 在内存中缓存一小时。

## 数据迁移

卡片开关保存在 Localstore 管理的 `card_parse.json` 中，通常位于 `data/nonebot_plugin_analysis_bilibili/`，具体以运行时 Localstore 配置为准。迁移机器人时备份该文件并放回对应数据目录，重启后即可读取原开关。

重复解析缓存、匿名指纹及签名缓存保存在内存中，重启后重新建立。

## 来源与许可

原作者：[mengshouer](https://github.com/mengshouer)。上游仓库：[nonebot_plugin_analysis_bilibili](https://github.com/mengshouer/nonebot_plugin_analysis_bilibili)。

沿用上游 `pyproject.toml` 声明的 MIT 许可，完整文本见 [LICENSE](LICENSE)。修改记录见 [CHANGELOG.md](CHANGELOG.md)。WBI 实现参考 [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign/wbi.md)。
