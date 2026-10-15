# 《借月》MCP 服务

## 当前实现

服务同时提供：

- `GET /music`：人类网页；
- `POST /music/mcp`：MCP Streamable HTTP；
- `GET /healthz`：不依赖外部服务的健康检查。

MCP 使用官方 TypeScript SDK v2 的无状态 `createMcpHandler`，默认兼容当前 2026-07-28 协议与 2025-era 的 stateless Streamable HTTP。代码不创建数据库，不保存用户身份或欣赏进度。

## 四个只读工具

- `music_catalog`：歌曲、版本、时长、署名、演唱者和感知说明；
- `music_start`：返回第一段与客户端游标；
- `music_next`：从游标推进一段；同一游标重复调用结果一致；
- `music_seek`：按毫秒、段落 ID、歌词行 ID 或旧游标跳转与回听。

游标只包含数据修订号、歌曲 ID 和段落序号，经严格校验后使用。它不授予任何权限，也不包含个人数据，因此无需服务端会话或签名。不同客户端持有自己的游标，互不覆盖。

## 音乐感知数据

`scripts/build_mcp_data.py` 从已审核时间轴、人工听音事件和离线自动曲线生成 `data/songs/jieyue/mcp.json`：

- 12 个音乐段落；
- 72 句歌词与稳定演唱者 ID；
- 33 条人工听音事实；
- 每段四条、每条最多五个采样点的离线曲线；
- 旋律轮廓、调性和拍号保持 `unknown`。

每次工具调用最多返回一个段落。当前最大一段的 `structuredContent + text` 为 7,293 UTF-8 字节，低于代码中的 32 KiB 硬上限。数据明确声明：这是人工标注和离线测量，不代表模型直接听到了原始音频。

## 本地运行

要求 Node.js 22+ 与 pnpm：

```bash
pnpm install --frozen-lockfile
python3 scripts/build_mcp_data.py
pnpm test
pnpm start
```

默认监听 `0.0.0.0:3000`。部署环境可设置：

- `PORT`；
- `HOST=0.0.0.0`；
- `PUBLIC_BASE_URL=https://example.invalid`；
- `ALLOWED_HOSTS`：额外允许的 hostname，以逗号分隔；
- `RAILWAY_PUBLIC_DOMAIN`：Railway 提供时自动加入 Host/Origin 白名单。
- `JIEYUE_VIDEO_URL`：对象存储/CDN 上的 MP4 HTTPS 地址，运行时注入网页数据。

## 安全与资源边界

- Host 与 Origin 白名单防止 DNS rebinding；无 Origin 的服务器端 MCP 客户端允许通过。
- MCP 请求体上限 64 KiB。
- 单 IP 每分钟 60 次 MCP 请求；同时最多处理 20 次 MCP 请求。
- 单次工具结果上限 32 KiB。
- 请求和工具调用不执行音频分析。
- 日志不记录请求正文、游标、歌词或密钥。
- 第一版匿名只读；若正式公开后需要滥用防护，可在入口层增加 bearer/OAuth，但不在本地伪造认证兼容性。

## 已验证与未验证

自动测试已经验证：

- 2025-era 初始化、工具发现和四工具调用；
- 2026-07-28 modern era 自动协商；
- 开始、推进、按时间/段落/歌词跳转、回听；
- 重复游标幂等、不同客户端游标隔离；
- 关键 119.138 秒交接和尾奏基底事实存在；
- 无效或旧修订游标被拒绝。

2026-10-15 在独立 Railway 临时端点 `https://musiccc-production.up.railway.app/music/mcp` 完成公网冒烟测试：legacy 与 modern era 均可初始化并发现四个工具；开始、推进、三类跳转、两客户端隔离、重复游标幂等和 8 路并发目录调用均通过。抽样最大工具结果为 6,945 UTF-8 字节。恶意 Origin 返回 403。

人类网页与脚本、样式、歌曲数据和海报均已从公网成功加载。MP4 仍等待独立对象存储/CDN 地址，因此现阶段播放器会明确显示加载失败；这不影响 MCP 文本/结构化音乐感知服务。

尚未宣称 GPT、Claude、Gemini 的具体产品客户端已经连接成功。那需要在临时公网域名部署后分别实测；服务器本地通过协议测试不等于客户端把音频传给模型，也不等于模型听到了声音。
