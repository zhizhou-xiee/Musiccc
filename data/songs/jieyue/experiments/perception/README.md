# 音乐感知 A/B 技术验证

本目录比较三种使用相同歌词、演唱者和段落时间的 MCP 候选输入：

- `lyrics_only.json`：只有歌词与演唱者，用作基线；
- `candidate_a_features.json`：基线加压缩后的段落级声学指标；
- `candidate_b_summaries.json`：基线加预生成音乐摘要；
- `metrics.json`：文件大小、分段累计响应体积和透明的 Token 代理区间。

生成命令：

```sh
python3 scripts/build_perception_prototypes.py --audio /absolute/path/to/final-master.mp3
```

分析只离线读取音频，依赖 FFmpeg，不保存波形或媒体副本，也不调用模型 API。输出中的自动测量和人工粗标注仍需与母带逐段听审，不能作为正式上线数据。

`metrics.json` 中的 Token 数是本地没有供应商 tokenizer 时使用的比较代理，不是 GPT、Claude 或 Gemini 的实际计费 Token。正式决策前仍需在选定客户端/API 上记录真实 usage。
