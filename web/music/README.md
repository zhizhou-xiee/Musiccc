# `/music` 人类端

轻量、无框架的《借月》正式 MV 展示页。浏览器使用原生 `<video>` 控件，不自动播放，保留 16:9 原画面比例，并通过 `playsinline` 支持 iPhone Safari 页内播放。

## 数据

`data/song.json` 是生成产物，来源为：

- `data/songs/jieyue/metadata.json`
- `data/songs/jieyue/timeline.reference.json`

更新上述数据后运行：

```sh
python3 scripts/build_web_data.py
```

可以用 `JIEYUE_VIDEO_URL` 指定对象存储/CDN 地址；未设置时使用本地相对地址 `./media/jieyue-mv-720p.mp4`。

## 本地媒体

源 MP4 不进入普通 Git 历史。本地预览时，将获准公开的文件复制为：

```text
web/music/media/jieyue-mv-720p.mp4
```

在仓库根目录启动静态服务器时，应以 `web` 作为文档根目录，这样页面地址就是 `/music/`。正式部署需要媒体源或 CDN 正确支持 Range 请求、`video/mp4` 内容类型与缓存头。

仓库提供了支持单段字节 Range 的本地预览服务器，便于真实检查视频拖动：

```sh
python3 scripts/serve_web.py --port 4174
```

然后访问 `http://127.0.0.1:4174/music/`。这个脚本只用于本地验收，不替代正式媒体 CDN。
