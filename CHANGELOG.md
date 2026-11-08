# 更新记录

## 2.8.5 — 2026-11-08

- 基于 mengshouer 上游 2.8.4，保留原作者、MIT 声明和完整 Git 历史。
- 支持新版 opus 图文及移动端动态链接，解析正文和图片，兼容桌面动态接口回退。
- 搜索前访问主站，补充 ticket、搜索 Referer、`v_voucher` 验证识别及匿名指纹缓存。
- WBI 密钥和 ticket 缓存一小时，同时保留当前 HTTP 会话、Cookie 及可配置超时。
- 合入无定时线程的重复解析缓存、完整图片后缀识别、链接边界匹配及单次监听注册。
- 保留全局/分群卡片双开关及 Localstore 持久化、管理命令、HTTP 412/429 检查、有限重试和视频解析异常提示。
- 补充两种安装方式、依赖、MIT 许可证文本和独立回归测试。

上游基线：`mengshouer/nonebot_plugin_analysis_bilibili` 的 `b24c80e3e4d608667ba284e9f43276d4ca50143d`。本次保留 `wbi.py` 模块以承接会话复用与异常处理，并合入上游 `sign.py` 的签名缓存及 ticket 功能。
