# JieYue Music

《借月》人机双端音乐展厅的独立仓库。

当前状态：Phase 0 技术验证与音乐时间轴校对。GitHub 独立仓库已创建；终版 MV 使用的人工开口时间已导入为校对基准；尚未创建或连接任何 Railway、对象存储、生产域名或付费资源。

## 隔离原则

- 本仓库必须独立于迎风小镇主仓库、数据库、内部 API 和现有 MCP 服务运行。
- Railway Project、Service、环境变量、构建、日志和静态媒体存储均应独立管理。
- `crotown.app/music` 的正式路径接入必须另行审批；在此之前使用独立临时域名验收。
- 音频分析只允许离线执行，网页与 MCP 请求不得触发实时音频分析。

Phase 0 结论与待确认项见 [docs/phase-0-assessment.md](docs/phase-0-assessment.md)，已确认素材见 [docs/asset-inventory.md](docs/asset-inventory.md)。

音乐感知候选 A/B 的首轮本地验证见 [docs/perception-ab-report.md](docs/perception-ab-report.md)。当前建议使用预生成音乐摘要作为唯一默认路线，尚待项目负责人确认。

候选 C「Music Semantic Score」的单曲 PoC 见 [docs/mss-poc-report.md](docs/mss-poc-report.md) 与 [MSS 实验目录](data/songs/jieyue/experiments/mss-poc/README.md)。MSS/0.1 已能表示 12 个段落和 33 个可溯源听音事件；同证据、同约 800 Token 的自然语言与 MSS 当前显式信息覆盖打平，仍需真实模型盲测，尚未替换候选 B。

MSS/0.2 的 curve-first 实验见 [docs/mss-v0.2-curve-report.md](docs/mss-v0.2-curve-report.md) 与 [曲线实验目录](data/songs/jieyue/experiments/mss-curve-poc/README.md)。这一版将情绪和比喻排除在核心层之外，用四条离线测量曲线、33 条分层客观事件和显式未知项保留音乐运动；持续基底与当前前景不再混作替换关系。

分层表示的首轮隔离子代理盲测见 [docs/mss-layered-blind-test-report.md](docs/mss-layered-blind-test-report.md) 与 [实验目录](data/songs/jieyue/experiments/layered-mss-eval/README.md)。本轮未调用外部模型或产生费用；结果只支持继续验证 MSS，不能宣称跨模型兼容。

统一歌曲资料位于 `data/songs/jieyue/metadata.json`，当前校对基准位于 `data/songs/jieyue/timeline.reference.json`。Whisper 旧初稿保留在 `data/songs/jieyue/timeline.draft.json` 作为对照；人工开口、估算唱完、字幕显示边界和自动节拍在数据中分别标注，不会混作同一种精度。

本地歌词时间轴校对器位于 [tools/timeline-review](tools/timeline-review/README.md)。它直接读取本机母带，在浏览器本地保存进度并导出带人工审核记录的 JSON；不会上传或提交音频文件。

本地音乐摘要校对器位于 [tools/summary-review](tools/summary-review/README.md)。它把人工歌词、演唱者和乐器粗标与自动声学测量并排展示，支持逐段循环试听、修改摘要、确认状态以及 JSON 导入导出。

本地 MSS 听音事件校对器位于 [tools/mss-review](tools/mss-review/README.md)。它逐条呈现 33 个可溯源音乐事件，支持点状/连续事件循环试听、时间微调、乐器候选与语义字段修订、审核状态及 JSON 导入导出。

`/music` 人类端初版位于 [web/music](web/music/README.md)。页面使用浏览器原生视频控件，并从统一歌曲元数据生成作品署名、演唱者与段落跳转数据。
