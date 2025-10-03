# Settings 层接口说明

## loader.load_config
- **输入**：可选 `config_path`（CLI `--config` 或环境变量 `WASH_CONFIG`）；默认读取项目根目录下的 `config.toml`。
- **返回**：`AppConfig`，包含：
  - `default_spider`: 默认爬虫名。
  - `http`: `HttpSettings`（`timeout`, `min_delay`, `max_delay`, `max_attempts`, `backoff_factor`, `transport`, `use_captured_headers`, `playwright_headless`）。
  - `paths`: `PathSettings`（`data_dir`, `raw_dir`, `translated_dir`, `formatted_dir`, `titles_dir`, `artifacts_dir`, `log_dir`, `state_dir`, `cookie_jar`, `header_jar`, `default_channel`）。
    - 常用方法：`raw_for(channel)`, `translated_for(channel)`, `formatted_for(channel)`, `titles_for(channel)`, `artifacts_for(channel)`。
  - `pipeline`: `PipelineSettings`（`default_channel`, `stages`）。
  - `spiders`: `[[spiders]]` 列表转换的键值对。

### PipelineSettings
- `stages`：字典形式存储 `StageSettings`；每个阶段提供 `model`、`prompt_path`、`output_dir`、`input_glob`、`timeout`、`thinking_budget` 等属性，方便 AI 节点与后续流水线复用。
- 常用别名：`config.ai` 对应 `translate` 阶段，`config.formatting` 对应 `format`，`config.title` 对应 `title`；可通过 `ai_for(channel)` 等方法获取指定频道配置。
- **副作用**：确保数据目录、Cookie 存储路径与 header_jar（首选请求头文件）所在目录存在。

## load_default_headers / save_default_headers
- **用途**：读取或写回 `src/settings/default_headers.json`。
- **策略**：若文件缺失，则尝试复制 `default_headers.template.json`；再失败则返回空字典。

## project_path
- **功能**：基于项目根拼接路径，便于生成绝对路径。
