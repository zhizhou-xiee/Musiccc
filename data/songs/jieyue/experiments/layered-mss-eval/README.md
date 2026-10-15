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

只有同时提供 `--execute`、明确批准的美元上限和 API 密钥才会发送推理请求。执行前会读取 OpenRouter 实时价格，最坏情况估算超过批准上限时拒绝运行。API 密钥不会写入仓库、请求结果或日志。

推荐先使用隐藏输入配置本机密钥。密钥只写入权限为 `0600`、且被 Git 忽略的 `.secrets/openrouter_api_key`：

```bash
python3 scripts/configure_openrouter_key.py
```

也可以改用环境变量 `OPENROUTER_API_KEY`；环境变量优先于本机密钥文件。

```bash
OPENROUTER_API_KEY=... python3 scripts/run_openrouter_cross_model_eval.py \
  --execute --approved-cap-usd 0.20
```

首次外部预跑发现三个模型默认启用隐藏推理，导致 1,200-token 输出预算主要被推理占用，不能用于正式评分。正式配置为 GPT 与 Claude 关闭推理，并把正文上限调整为 1,800 token；Gemini 3.8 Flash 的当前端点强制启用推理，因此限定为 256-token 推理预算，其余预算留给正文。这个供应商差异必须随结果报告。预跑保留为兼容性失败案例，不计入对照结果。

跨模型运行清单：

- `20261015T064813Z`：无效预跑；默认隐藏推理耗尽正文预算。
- `20261015T065427Z`：三模型参数 smoke；定位 Claude 截断与 Gemini 参数错误。
- `20261015T065536Z`：Gemini 禁用推理 smoke；端点拒绝，费用为 0。
- `20261015T065602Z`：Gemini 限定推理预算 smoke；成功。
- `20261015T065625Z`：正式修正版，27 / 27 成功；唯一计分 run。

正式评分见 `cross-model-scorecard.json`，完整报告见 `docs/mss-cross-model-eval-report.md`。原始响应、usage 与 manifest 位于 `cross-model-results/`。所有结果已扫描，未包含 API key。

`results/a_lyrics_only.md`、`results/b_natural_layers.md` 和 `results/c_mss_layers.md` 是预跑原文；预跑暴露连续事件结束时间缺失后，修订条件重新生成，`results/b_natural_layers_r2.md` 与 `results/c_mss_layers_r2.md` 为最终计分样本。歌词条件没有变化，因此没有重复调用。`scorecard.json` 记录最终评分。

重新生成：

```bash
python3 scripts/build_layered_mss_eval.py
```
