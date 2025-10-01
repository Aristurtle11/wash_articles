# Scripts 说明

## `scripts/fetch_cookies.py`
- **用途**：向指定 URL 发送请求，刷新本地 CookieJar，并更新默认请求头中的 `Cookie` 字段。
- **命令示例**：
  ```bash
  python scripts/fetch_cookies.py https://example.com --config config.toml
  ```
- **输出**：在控制台打印响应体前 200 个字符的 JSON 序列化片段，便于快速查看。
- **实现要点**：
  - 复用 `HttpClient`，保持与爬虫一致的会话逻辑。
  - 通过 `load_config` 获取 Cookie 存储路径，保证状态落在 `data/state/` 目录。
