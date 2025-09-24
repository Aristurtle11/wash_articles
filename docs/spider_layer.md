# Spiders 层接口说明

## Registry (`src/spiders/__init__.py`)
- `SPIDER_REGISTRY`: 映射爬虫名称到类。
- `get_spider(name)`：根据名称返回爬虫类，未注册时抛出 `KeyError`。
- **扩展方式**：新增爬虫时在模块中导入类并写入 `SPIDER_REGISTRY`。

## ExampleSpider (`src/spiders/example_spider.py`)
- **继承自**：`BaseSpider`。
- **配置项**：读取 `config.spiders["example"]` 中的 `start_url`。
- **流程**：
  1. 在 `start_requests()` 中 yield `HttpRequest`。
  2. `parse()` 使用 `BeautifulSoup` 提取 `<title>` 与 `<a>` 链接数量。
  3. 产出结构化字典交给管道处理。
- **作为模板**：建议在新站点中仿照此模式实现 `start_requests` 与 `parse`。
