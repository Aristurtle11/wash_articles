# Data 目录结构

- `data/<channel>/raw/`：原始抓取内容（HTML、图片、二进制资源）。
- `data/<channel>/translated/`：AI 翻译后的纯文本结果（`*.translated.txt`）。
- `data/<channel>/formatted/`：排版完成的 HTML（`*.formatted.html`）。
- `data/<channel>/titles/`：AI 生成的候选标题（`*.title.txt`）。
- `data/<channel>/artifacts/`：爬虫与发布阶段生成的结构化产物（如 JSONL、Payload 快照）。
- `data/logs/`：运行日志或调试输出，可与 logging 配置结合使用。
- `data/state/`：全局状态文件（`cookies.txt`、凭证缓存等）。

> 读取配置时会确保上述目录存在；可通过 `pipeline.default_channel` 控制默认频道。
