# JieYue Music

《借月》人机双端音乐展厅的独立仓库。

当前状态：Phase 0 技术验证与音乐时间轴初稿。GitHub 独立仓库已创建；已生成待人工校对的歌词时间轴；尚未创建或连接任何 Railway、对象存储、生产域名或付费资源。

## 隔离原则

- 本仓库必须独立于迎风小镇主仓库、数据库、内部 API 和现有 MCP 服务运行。
- Railway Project、Service、环境变量、构建、日志和静态媒体存储均应独立管理。
- `crotown.app/music` 的正式路径接入必须另行审批；在此之前使用独立临时域名验收。
- 音频分析只允许离线执行，网页与 MCP 请求不得触发实时音频分析。

Phase 0 结论与待确认项见 [docs/phase-0-assessment.md](docs/phase-0-assessment.md)，已确认素材见 [docs/asset-inventory.md](docs/asset-inventory.md)。

歌词时间轴初稿位于 `data/songs/jieyue/timeline.draft.json`，人工校对表位于 [docs/timeline-review.md](docs/timeline-review.md)。所有自动时间戳在人工试听确认前均不得标记为正式数据。
