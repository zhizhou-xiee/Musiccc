# 正式域名路由

## 当前入口

- 人类网页：`https://crotown.app/music`
- MCP：`https://crotown.app/music/mcp`
- 独立源站：`https://musiccc-production.up.railway.app`

2026-10-15 经负责人批准，Cloudflare Worker `musiccc-path-router` 开始承接唯一的路由模式 `crotown.app/music*`。Worker 只代理精确的 `/music` 与 `/music/...`；例如 `/musical` 会回到迎风小镇原有源站，不属于 Musiccc。

## 隔离边界

- 未修改迎风小镇仓库、Railway Service、数据库、内部 API 或默认路由。
- 未更改 `crotown.app` DNS；现有域名与非 `/music` 路径仍使用原有入口。
- Worker 保留 HTTP 方法、请求体和流式响应，因而同一路径可承载网页与 MCP POST 请求。
- 视频端点的 307 跳转原样返回浏览器；视频随后直接从 Musiccc 私有 Bucket 获取，不经过 Worker 或迎风小镇应用。

Worker 源码与配置位于 `edge/cloudflare/`。当前使用 Cloudflare Workers Free 配额，未升级套餐或创建新增付费资源。

## 2026-10-15 验收

- `/music`、脚本、样式、歌曲元数据与海报均返回 200。
- 视频端点返回 307，并跳转到带时效签名的 Musiccc Bucket URL。
- MCP modern era 初始化成功；发现 `music_catalog`、`music_start`、`music_next`、`music_seek`；目录与开始欣赏调用成功。
- `https://crotown.app/` 保持 200，`/musical` 未被 Worker 捕获。

## 回滚

如需立即撤回正式路径，只需删除或停用 Cloudflare 上的 `crotown.app/music*` Worker route。Musiccc Railway 临时域名仍可独立运行；回滚不需要修改迎风小镇代码或数据库。
