# 《借月》时间轴数据

- `timeline.draft.json`：包含 21 位演唱者、9 个段落和 72 句歌词的结构化时间轴初稿。
- `timeline.draft.lrc`：由同一初稿生成的 LRC 预览。

两份文件均为自动对齐结果，状态是 `draft_unverified`，必须完成人工试听校对后才能生成正式时间轴。

源 MP3、MV、Whisper 模型和 Whisper 原始转写不进入普通 Git 历史。JSON 中记录最终母带的 SHA-256，用于避免误用其他音频版本。

## 生成方式

构建脚本为 `scripts/build_timeline_draft.py`，依赖见 `scripts/requirements-alignment.txt`。脚本读取：

1. 负责人提供的歌词与演唱者分配；
2. `whisper.cpp` 的整曲 token 时间戳 JSON；
3. 可选的分段提示转写 JSON，用于纠正明显包含间奏的粗区间。

脚本始终保留人工提供的歌词正文，Whisper 只提供候选时间位置，不会用识别文本覆盖歌词。
