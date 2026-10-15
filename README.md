# JieYue Music

《借月》人机双端音乐展厅的独立仓库。

当前状态：Phase 0 技术路线已锁定，Phase 1 人类网页与 Phase 3 MCP 初版已部署到独立 Railway 临时域名；音乐时间轴仍保留逐项人工校对状态。GitHub 与 Railway 均独立于迎风小镇；Musiccc 专属 Railway Bucket 已连接，正式域名尚未接入。

Railway 的授权隔离边界与媒体上传方案见 [docs/railway-media.md](docs/railway-media.md)。Musiccc 可以与 Readdd 共享 Railway Project，但保持独立 Service 与资源；迎风小镇位于另一 Project，禁止引用。

## 隔离原则

- 本仓库必须独立于迎风小镇主仓库、数据库、内部 API 和现有 MCP 服务运行。
- Railway Project、Service、环境变量、构建、日志和静态媒体存储均应独立管理。
- `crotown.app/music` 的正式路径接入必须另行审批；在此之前使用独立临时域名验收。
- 音频分析只允许离线执行，网页与 MCP 请求不得触发实时音频分析。

Phase 0 结论与待确认项见 [docs/phase-0-assessment.md](docs/phase-0-assessment.md)，已确认素材见 [docs/asset-inventory.md](docs/asset-inventory.md)。

音乐感知候选 A/B 的首轮本地验证见 [docs/perception-ab-report.md](docs/perception-ab-report.md)。跨模型复测后已确定使用“预生成客观音乐摘要＋数值曲线”作为唯一默认路线。

候选 C「Music Semantic Score」的单曲 PoC 见 [docs/mss-poc-report.md](docs/mss-poc-report.md) 与 [MSS 实验目录](data/songs/jieyue/experiments/mss-poc/README.md)。MSS/0.1 已能表示 12 个段落和 33 个可溯源听音事件；同证据、同约 800 Token 的自然语言与 MSS 当前显式信息覆盖打平，仍需真实模型盲测，尚未替换候选 B。

MSS/0.2 的 curve-first 实验见 [docs/mss-v0.2-curve-report.md](docs/mss-v0.2-curve-report.md) 与 [曲线实验目录](data/songs/jieyue/experiments/mss-curve-poc/README.md)。这一版将情绪和比喻排除在核心层之外，用四条离线测量曲线、33 条分层客观事件和显式未知项保留音乐运动；持续基底与当前前景不再混作替换关系。

分层表示的首轮隔离子代理盲测见 [docs/mss-layered-blind-test-report.md](docs/mss-layered-blind-test-report.md) 与 [实验目录](data/songs/jieyue/experiments/layered-mss-eval/README.md)。本轮未调用外部模型或产生费用；结果只支持继续验证 MSS，不能宣称跨模型兼容。

OpenRouter 跨模型正式对照见 [docs/mss-cross-model-eval-report.md](docs/mss-cross-model-eval-report.md)。GPT、Claude、Gemini 的 27 个修正版样本显示自然语言＋曲线为 9.17 / 10，压缩 MSS＋曲线为 9.39 / 10；MSS 增益很小且产生更多自信事实错误，因此当前缩写版不直接进入生产，下一步改为自描述 MSS/0.3 后复测。

MSS/0.3 的三轮复测与最终路线决定见 [docs/mss-v0.3-eval-report.md](docs/mss-v0.3-eval-report.md)。最终候选实测最多 642 token、客观题均值 9.89 / 10，但仍有 2 个明确方向矛盾，未通过预设的 ≤1 安全门槛；因此 MSS 保留为研究产物，不进入第一版 MCP 默认通道。

MCP 服务见 [docs/mcp-service.md](docs/mcp-service.md)。四个只读工具已使用官方 SDK v2 实现，客户端游标无状态；自动测试同时覆盖 2025-era 与 2026-07-28 Streamable HTTP 协议，临时公网端点也已通过 SDK 端到端冒烟测试。具体 GPT、Claude、Gemini 产品客户端仍须分别验证。

统一歌曲资料位于 `data/songs/jieyue/metadata.json`，当前校对基准位于 `data/songs/jieyue/timeline.reference.json`。Whisper 旧初稿保留在 `data/songs/jieyue/timeline.draft.json` 作为对照；人工开口、估算唱完、字幕显示边界和自动节拍在数据中分别标注，不会混作同一种精度。

本地歌词时间轴校对器位于 [tools/timeline-review](tools/timeline-review/README.md)。它直接读取本机母带，在浏览器本地保存进度并导出带人工审核记录的 JSON；不会上传或提交音频文件。

本地音乐摘要校对器位于 [tools/summary-review](tools/summary-review/README.md)。它把人工歌词、演唱者和乐器粗标与自动声学测量并排展示，支持逐段循环试听、修改摘要、确认状态以及 JSON 导入导出。

本地 MSS 听音事件校对器位于 [tools/mss-review](tools/mss-review/README.md)。它逐条呈现 33 个可溯源音乐事件，支持点状/连续事件循环试听、时间微调、乐器候选与语义字段修订、审核状态及 JSON 导入导出。

`/music` 人类端初版位于 [web/music](web/music/README.md)。页面使用浏览器原生视频控件，并从统一歌曲元数据生成作品署名、演唱者与段落跳转数据。
