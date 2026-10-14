# 《借月》时间轴数据

- `timeline.reference.json`：当前校对基准。包含人工波形标记的 72 个开口时间、估算唱完时间、字幕显示时间、主唱与和声角色、13 个段落、17 个 MV 分镜、9 个乐器事件和 380 个自动检测节拍。
- `timeline.draft.json`：Whisper 自动对齐的旧初稿，用作来源对照，不再作为校对器默认输入。
- `timeline.draft.lrc`：由自动对齐旧初稿生成的 LRC 预览。
- `subtitles/zh-CN.srt`：终版 MV 使用的中文字幕时间。
- `source/`：负责人提供的终版 MV 分拍资料和第 5 句人工校对导出原件；媒体文件仍不进入 Git。

人工标记的开口时间现在是主参考。唱完时间来自分离人声后的估算，仍需试听；第 5 句原始开口是参照第二段主歌补出的 00:40.000，之后已由负责人试听修订并确认成 00:40.800–00:43.160。约 95.7 BPM 和逐拍数组均为未人工核对的自动检测结果，只能辅助观察。

源 MP3、MV、Whisper 模型和 Whisper 原始转写不进入普通 Git 历史。JSON 中记录最终母带的 SHA-256，用于避免误用其他音频版本。

## 生成方式

构建脚本为 `scripts/build_timeline_draft.py`，依赖见 `scripts/requirements-alignment.txt`。脚本读取：

1. 负责人提供的歌词与演唱者分配；
2. `whisper.cpp` 的整曲 token 时间戳 JSON；
3. 可选的分段提示转写 JSON，用于纠正明显包含间奏的粗区间。

脚本始终保留人工提供的歌词正文，Whisper 只提供候选时间位置，不会用识别文本覆盖歌词。

## 导入终版 MV 分拍资料

`scripts/import_mv_timing.py` 会交叉检查 JSON、SRT 与旧时间轴的 72 句歌词和起点，随后生成 `timeline.reference.json`。它分别保存：

1. 人工看人声波形标记的开口时间；
2. 从分离人声估算的唱完时间；
3. 为阅读体验延长过的 SRT 显示结束时间；
4. 原来的 Whisper 自动对齐证据。

三种结束/对齐数据不可互相冒充。正式时间轴只有在剩余例外和估算边界试听确认后才可标记为 `manually_verified`。
