# 系统架构概览

```
/wash_articles/
├── config.ini
├── main.py
├── requirements.txt
├── src/
│   ├── app/
│   │   └── runner.py
│   ├── core/
│   │   ├── base_spider.py
│   │   ├── http_client.py
│   │   └── rate_limiter.py
│   ├── pipelines/
│   │   ├── base_pipeline.py
│   │   ├── data_saver.py
│   │   └── transform.py
│   ├── settings/
│   │   ├── loader.py
│   │   └── default_headers.json
│   ├── spiders/
│   │   └── example_spider.py
│   └── utils/
│       ├── file_helper.py
│       ├── html.py
│       └── logging.py
├── scripts/
│   └── fetch_cookies.py
├── data/
│   ├── logs/
│   ├── processed/
│   ├── raw/
│   └── state/
└── docs/
    └── *.md
```

- **app**：命令行入口层，负责解析参数、调度爬虫与管道。
- **core**：核心能力层，提供 HTTP 客户端、爬虫基类与限速工具。
- **spiders**：各站点爬虫实现，继承 `BaseSpider` 并聚焦解析逻辑。
- **pipelines**：数据处理流水线，负责清洗、转换与落盘。
- **settings**：配置加载与默认请求头管理。
- **utils**：通用工具函数，供各层复用。
- **scripts**：一次性或辅助脚本，例如更新 Cookie。
- **data**：所有运行产物与状态文件统一归档。
