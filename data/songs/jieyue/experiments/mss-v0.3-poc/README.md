# MSS/0.3 self-describing candidate

这一版针对跨模型测试暴露的三个问题：乐器缩写歧义、`^n` 基底回溯，以及进入/退出方向混淆。

原则：

- 乐器值使用可读的稳定 ID，不使用 `lw?`、`lb?`、`ek`。
- 每个事件直接携带完整 `background` 与 `foreground`，不引用其他事件。
- `background_enter`、`background_exit`、`foreground_enter`、`foreground_exit` 为有方向字段。
- 继续保留客观数值曲线，不加入情绪、比喻或听后感。
- 为回收 token，每条曲线从最多 16 个关键点降到 8 个；事件方向优先于曲线采样密度。

生成：

```bash
python3 scripts/build_mss_v03.py
```

`outputs/mss.v03.json` 是完整结构，`outputs/mss_v03_800.txt` 是模型注入候选。字节代理只用于预筛；最终是否低于 800 token 必须以三家模型实际 usage 差值为准。

## 复测结论

最终候选实际为 GPT 480、Claude 642、Gemini 642 token，跨模型客观题均值 9.8889 / 10；但 90 个客观回答中仍有 2 个明确方向矛盾，超过预设上限 1。因此本候选不进入第一版 MCP 默认路线。

第一版统一采用“预生成客观音乐摘要＋数值曲线”。MSS/0.3 保留为研究产物，不做运行时切换。详细结果见 `scorecard.json` 与 `docs/mss-v0.3-eval-report.md`。
