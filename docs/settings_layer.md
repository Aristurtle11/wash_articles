# Settings 层接口说明

## loader.load_config
- **输入**：可选 `config_path`（CLI `--config` 或环境变量 `WASH_CONFIG`）；默认读取项目根目录下的 `config.ini`。
- **返回**：`AppConfig`，包含：
  - `default_spider`: 默认爬虫名。
  - `http`: `HttpSettings`（`timeout`, `min_delay`, `max_delay`, `max_attempts`, `backoff_factor`）。
  - `paths`: `PathSettings`（`data_dir`, `raw_dir`, `processed_dir`, `log_dir`, `state_dir`, `cookie_jar`）。
  - `spiders`: 每个 `[spider:xxx]` 小节的键值对。
- **副作用**：确保数据目录和 Cookie 存储路径存在。

## load_default_headers / save_default_headers
- **用途**：读取或写回 `src/settings/default_headers.json`。
- **策略**：若文件缺失，则尝试复制 `default_headers.template.json`；再失败则返回空字典。

## project_path
- **功能**：基于项目根拼接路径，便于生成绝对路径。
