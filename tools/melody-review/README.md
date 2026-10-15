# 《借月》旋律与和声候选校对台

这是一个只在本机浏览器中工作的 PoC 校对工具。它读取已提交的自动候选 JSON，但母带由使用者通过文件选择器临时载入，不会复制、上传或写进仓库。

从仓库根目录启动静态服务器：

```bash
python3 -m http.server 4173
```

然后打开 `http://127.0.0.1:4173/tools/melody-review/`。

校对流程：

1. 选择本机 WAV 或 MP3 母带。
2. 逐句播放母带与合成候选轮廓。
3. 将每句标记为已确认、需修正、无法判断或仍待校对。
4. 导出 `jieyue.melody-harmony.reviewed.json`。

页面不会修改 `candidates.json`。只有后续明确导入并验证的字段才可以进入 MSS 或 MCP。
