# Core 层接口说明

## HttpClient
- **位置**：`src/core/http_client.py`
- **职责**：统一管理 HTTP 请求、Cookie 持久化与重试策略。
- **初始化参数**：
  - `http_settings`: `HttpSettings`，包含 `timeout`、`min_delay`、`max_delay`、`max_attempts`、`backoff_factor`。
  - `cookie_path`: CookieJar 存储路径。
  - `default_headers`: 默认请求头字典，可由 `settings.load_default_headers()` 提供。
  - `header_saver`: 持久化请求头的回调（默认写回 `default_headers.json`）。
- **核心方法**：
  - `fetch(HttpRequest) -> HttpResponse`: 发送请求并自动应用限速、重试、Cookie 更新。
  - `default_headers`: 只读属性，返回当前默认请求头副本。
  - `_decode_body(body, encoding)`: 内部方法，支持 `gzip`/`deflate`/`br` 解压。

## HttpRequest
- **位置**：`src/core/http_client.py`
- **字段**：`url`, `method`, `headers`, `data`, `min_delay`, `max_delay`, `max_attempts`, `backoff_factor`, `timeout`。
- **用途**：描述一次待发送的请求；未提供的字段将继承 `HttpSettings` 默认值。

## HttpResponse
- **位置**：`src/core/http_client.py`
- **字段**：`url`, `status`, `headers`, `body`, `text`, `elapsed`。
- **用途**：封装响应原始二进制以及解码文本，供爬虫解析。

## BaseSpider
- **位置**：`src/core/base_spider.py`
- **职责**：规定爬虫生命周期和解析流程。
- **重要方法**：
  - `prepare()`: 运行前钩子，默认空实现。
  - `start_requests()`: 必须重写，返回 `Iterable[HttpRequest]`。
  - `parse(response)`: 必须重写，返回 `Iterator[Any]`，产出 item。
  - `handle_item(item)`: 处理管道输出，默认空实现，可用来统计或产出结果。
- **运行流程**：`run()` 调用 `prepare()` → 遍历 `start_requests()` → `HttpClient.fetch` → `parse()` → 交给 `PipelineManager`。

## RateLimiter
- **位置**：`src/core/rate_limiter.py`
- **职责**：提供随机延时策略，支持 `min_delay` 与 `max_delay`。
- **方法**：
  - `compute_delay()`：返回下次应等待的秒数。
  - `sleep()`：阻塞当前线程相应时长并返回实际等待值。
