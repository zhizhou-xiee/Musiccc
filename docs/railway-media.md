# Railway 媒体部署

## 已确认边界

负责人已确认：Musiccc 可以与 Readdd 位于同一 Railway Project；“独立”的本意是不得混入迎风小镇。Musiccc 仍使用独立 Service、Bucket、变量、部署和日志，不引用 CRO-TOWN 的数据库、变量、内部网络或 API。

本机 Railway CLI 旧链接仍指向 CRO-TOWN。在执行任何写操作前，必须显式重新链接并核对 Project 与 Service；不得依赖当前目录遗留状态。

## 部署换班

Musiccc 的运行时数据均来自镜像与专属 Bucket，不依赖持久卷。2026-10-15 核对确认原 `musiccc-volume` 仅含文件系统自动生成的 `lost+found`，且代码没有 `/data` 读写；该卷已从 Musiccc Service 解绑但未删除。

`railway.json` 配置 `/healthz` 部署健康检查、新旧实例 10 秒重叠与 15 秒退出缓冲。应用直接以 Node 启动，并在 `SIGTERM` / `SIGINT` 时停止接受新请求、关闭空闲连接、等待 HTTP 与 MCP 处理器结束；最长 10 秒后关闭遗留连接，避免正常部署换班被误判成异常退出。

## 推荐媒体路径

720p MV 存入 Musiccc 专属的 Railway Bucket `jieyue-media`。Bucket 为私有；应用访问 `/music/media/jieyue-mv-720p.mp4` 时生成六小时有效的签名 GET URL，并以 307 跳转，让浏览器直接从 Bucket 获取视频。这样保留 Range 请求能力，也不让视频流经过应用进程。

Railway 当前 Bucket 价格为 `$0.015 / GB-month`，API 操作和 Bucket egress 免费。27 MB 文件的月度用量会参与 Workspace 总量计算并按官方规则取整。负责人于 2026-10-15 批准最高 `$0.02 / 月`，专属 Bucket `jieyue-media` 已在 `XXX系列 / production` 创建。

## Bucket 创建后的配置

在 Musiccc Service 的 Variables 中使用 Railway 的 Bucket 自动注入功能。服务兼容 Railway 原生变量名：

- `ENDPOINT`
- `ACCESS_KEY_ID`
- `SECRET_ACCESS_KEY`
- `BUCKET`
- `REGION`

也支持带 `JIEYUE_BUCKET_` 前缀的同义变量，以避免未来同一 Service 接入多个 Bucket。凭据只保存在 Railway 变量中，不写入 Git、文档或日志。

上传命令必须在确认 CLI 已链接到 Musiccc Service 后执行：

```bash
railway run pnpm upload:video -- "/Users/htc/Desktop/借月MV_小机们的中秋_预览720p.mp4"
```

脚本上传为 `jieyue-mv-720p.mp4`，设置 `video/mp4` 和一天缓存，并用 `HeadObject` 校验远端大小。上传完成后的验收还必须检查 307 跳转、200/206 Range、Content-Type、拖动、桌面浏览器与真机 iPhone Safari。

## 2026-10-15 临时域名验收

- Bucket 上传与 `HeadObject` 校验通过：28,175,300 字节，`video/mp4`；
- `/music/media/jieyue-mv-720p.mp4` 返回 307 短期签名地址；
- Bucket Range 返回 `206 Partial Content`、`Accept-Ranges: bytes`，抽样范围 `0-1023/28175300`；
- 文件头为 ISO Base Media / H.264 兼容 MP4；
- 公网页面加载后 `duration=255.000998`、`readyState=4`、无媒体错误；
- 浏览器实际播放、暂停和跳转到 Bridge `190.86s` 均通过。

真机 iPhone Safari 与弱网仍需后续人工验收。
