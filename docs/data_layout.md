# Data 目录结构

- `data/raw/`：原始抓取内容（HTML、图片、二进制资源）。
- `data/processed/`：管道处理后的结构化数据（例如 JSONL、CSV）。
- `data/logs/`：运行日志或调试输出，可与 logging 配置结合使用。
- `data/state/`：爬虫状态文件（`cookies.txt`、指纹、断点记录等）。

> 所有子目录在加载配置时自动创建，确保爬虫运行前环境就绪。
