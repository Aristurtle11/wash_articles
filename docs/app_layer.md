# App 层接口说明

## runner.run
- **位置**：`src/app/runner.py`
- **功能**：CLI 入口。解析命令行参数、加载配置、实例化客户端与管道、执行指定爬虫。
- **参数**：`argv: Sequence[str] | None`，默认读取 `sys.argv[1:]`。
- **流程**：
  1. `configure_logging()` 初始化日志。
  2. `load_config()` 按需加载配置文件。
  3. 确定爬虫名（CLI 参数优先，其次配置默认值）。
  4. 构建 `HttpClient`、`TransformPipeline`、`DataSaverPipeline`。
  5. 读取爬虫私有配置并执行 `spider.run()`。
- **扩展点**：可在解析参数时增加自定义选项（如并发度、输出路径），或在运行前动态调整管道列表。
