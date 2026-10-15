# Music Semantic Score (MSS) PoC v0.1

本目录验证能否把《借月》转换为供语言模型阅读的结构化音乐表示。它是候选 C，与现有自然语言摘要候选 B 对照；不接入生产 MCP，不进行运行时动态路由。

## 输入证据

- `timeline.reference.json`：段落、歌词、稳定演唱者 ID 与时间轴。
- `source/detailed-listening-annotations.json`：项目负责人提供的精细乐器、音区、演奏动作和进入退出记录。
- `candidate_a_features.json`：最终 MP3 母带的离线自动响度与频谱测量。

所有字段保留来源和不确定性。`低音提琴类`、`沙鼓类`、`古筝或琵琶`不会被强行提升为确定乐器；没有可靠结果的拍号、调性和动机保持 `unknown`。

## 生成

```bash
python3 scripts/build_mss_poc.py
```

输出：

- `outputs/mss.full.json`：完整、可解析的 MSS/0.1。
- `outputs/mss_300.txt`：结构优先的极简档。
- `outputs/mss_800.txt`：包含完整事件流和压缩声学关系的标准档。
- `outputs/mss_1500.txt`：带中文事件说明、置信状态与关系的细节档。
- `outputs/legacy_summary_baseline.txt`：使用旧粗标的候选 B，保留用于发现过期结论，不作为公平格式对照。
- `outputs/natural_800.txt`：与 MSS 使用同一批新证据、同样约 800 Token 预算的自然语言基线。
- `metrics.json`：大小、Token 代理区间和信息覆盖计数。
- `evaluation-rubric.json`：人工事实题及各表示的显式信息覆盖判定。

本机没有供应商 tokenizer，Token 使用 UTF-8 字节数除以 4 至除以 3的透明区间，仅用于本地比较。实际计费 Token 与真实模型答题能力仍需后续客户端实验。

## 当前边界

- 只验证《借月》一首歌，避免在没有人工参考答案时让系统自己出题、自己判卷。
- 不输出简化 MIDI：当前没有可靠、人工核验的主旋律转录。
- 不声称 MSS 等于原生听音；它是对音乐结构和事件的符号化表达。
- `motifs` 暂为空，直到获得可靠旋律分离、音高轮廓或人工旋律标注。
