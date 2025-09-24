# Utils 层接口说明

## file_helper
- `ensure_parent(path)`: 若父目录不存在则创建，返回原 Path。
- `read_text(path, encoding='utf-8')`: 读取文本文件。
- `write_text(path, data, encoding='utf-8')`: 写入文本并确保父目录存在。

## html
- `load_local_html(path, parser='html.parser')`: 读取本地 HTML 文件并返回 `BeautifulSoup` 对象。

## logging
- `configure_logging(level=logging.INFO)`: 使用统一格式初始化根 logger（仅在未配置时生效）。
- `get_logger(name)`: 获取具名 logger。
