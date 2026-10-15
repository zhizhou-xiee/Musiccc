# Layered MSS blind evaluation

这一轮只检验“持续基底＋当前前景”的表达是否比歌词基线更容易被语言模型正确读取，同时观察结构化 MSS 与同证据自然语言的差异。

三种条件共享相同歌词、演唱者和时间轴：

- `a_lyrics_only`：只有共享歌词，没有音乐表示。
- `b_natural_layers`：追加客观自然语言、叠层关系与四条稀疏曲线。
- `c_mss_layers`：追加同证据的分层 MSS 与四条稀疏曲线。

每个测试实例只能看到一种条件，不得看到答案或其他条件的回复。客观题首先评分；开放题只在事实忠实的前提下观察解释差异，不能用“写得好听”代替理解正确。

当前首轮使用同一模型家族的隔离子代理，只能发现表示歧义和提示问题，不能证明 GPT、Claude、Gemini 的跨模型兼容性。跨模型测试需要另行登记目标模型、调用次数、实际 Token 与预计费用。

## 跨模型计划

`openrouter-plan.json` 登记第二轮的模型、价格快照、调用次数和成本上限。计划使用 GPT‑6 Luna、Claude Haiku 5.5、Gemini 3.8 Flash；三种条件各独立重复 3 次，共 27 次调用。

执行器默认只做免费干跑：

```bash
python3 scripts/run_openrouter_cross_model_eval.py
```

只有同时提供 `--execute`、明确批准的美元上限和环境变量 `OPENROUTER_API_KEY` 才会发送推理请求。执行前会读取 OpenRouter 实时价格，最坏情况估算超过批准上限时拒绝运行。API 密钥不会写入仓库、请求结果或日志。

```bash
OPENROUTER_API_KEY=... python3 scripts/run_openrouter_cross_model_eval.py \
  --execute --approved-cap-usd 0.10
```

`results/a_lyrics_only.md`、`results/b_natural_layers.md` 和 `results/c_mss_layers.md` 是预跑原文；预跑暴露连续事件结束时间缺失后，修订条件重新生成，`results/b_natural_layers_r2.md` 与 `results/c_mss_layers_r2.md` 为最终计分样本。歌词条件没有变化，因此没有重复调用。`scorecard.json` 记录最终评分。

重新生成：

```bash
python3 scripts/build_layered_mss_eval.py
```
