# JieYue Music

《借月》人机双端音乐展厅的独立仓库。

当前状态：Phase 0 技术验证与音乐时间轴校对。GitHub 独立仓库已创建；终版 MV 使用的人工开口时间已导入为校对基准；尚未创建或连接任何 Railway、对象存储、生产域名或付费资源。

## 隔离原则

- 本仓库必须独立于迎风小镇主仓库、数据库、内部 API 和现有 MCP 服务运行。
- Railway Project、Service、环境变量、构建、日志和静态媒体存储均应独立管理。
- `crotown.app/music` 的正式路径接入必须另行审批；在此之前使用独立临时域名验收。
- 音频分析只允许离线执行，网页与 MCP 请求不得触发实时音频分析。

Phase 0 结论与待确认项见 [docs/phase-0-assessment.md](docs/phase-0-assessment.md)，已确认素材见 [docs/asset-inventory.md](docs/asset-inventory.md)。

统一歌曲资料位于 `data/songs/jieyue/metadata.json`，当前校对基准位于 `data/songs/jieyue/timeline.reference.json`。Whisper 旧初稿保留在 `data/songs/jieyue/timeline.draft.json` 作为对照；人工开口、估算唱完、字幕显示边界和自动节拍在数据中分别标注，不会混作同一种精度。

本地歌词时间轴校对器位于 [tools/timeline-review](tools/timeline-review/README.md)。它直接读取本机母带，在浏览器本地保存进度并导出带人工审核记录的 JSON；不会上传或提交音频文件。

`/music` 人类端初版位于 [web/music](web/music/README.md)。页面使用浏览器原生视频控件，并从统一歌曲元数据生成作品署名、演唱者与段落跳转数据。
