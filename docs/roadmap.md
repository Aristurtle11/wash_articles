# 工程优化 Roadmap


关键问题

  - 运行链路靠多个独立脚本串联，缺少统一编排；状态通过文件名隐式传递，重复执行难
  以追踪依赖和失败节点。
  - AI 相关类（翻译、排版、取标题）代码高度重复，提示路径/输出目录配置分散在
  config.ini，增加维护成本。
  - 微信发布流程逻辑集中在脚本里，无法复用；publish_content.py 等半成品脚本容易
  误导。
  - 数据目录混合多类产物（原文、译文、排版、标题、上传副本），命名不一致，难以对
  账或清理。
  - 缺少端到端测试与防护：AI 调用失败、素材缺失、标题生成异常仅打印日志；没有验
  证 .formatted.html 与上传前 payload 的一致性。

  优化建议

  - 构建统一流水线：在 src/app/ 增加一个 Pipeline 层（或 DAG），显式描述“抓取→翻
  译→排版→标题→发布”的依赖关系与缓存策略，并提供单一 CLI 入口（如 python main.py
  pipeline run --channel realtor --publish），这样可支持断点续跑、跳过已完成步
  骤、集中处理错误重试。
  - 抽象 AI 节点基类：提炼出 BaseAIGenerator（处理 from_config、相对路径、写入文
  件、thinking_budget等通用流程），子类仅专注 prompt 渲染与结果清洗，同时在配置
  层将[ai]、[formatting]、[title]合并成统一的[[ai.stage]]` TOML 或 JSON 配置，减
  少重复字段并便于扩展。
  - 模块化微信发布：将标题决策、图片注入、payload 组装拆分成可注入的 service；脚
  本层只解析参数并调用 service。把 publish_content.py 更新成真正的多平台入口或移
  除，避免出现未实现的命令。
  - 重整数据目录结构：采用按阶段/通道分层的层级（如 data/<channel>/raw,
  translated, formatted, titles, payloads），每步输出附带 JSON 元数据（时间戳、
  来源文件、依赖 media 列表），并在 scripts/clean_project.sh 中按阶段清理，提升
  可追踪性。
  - 加强测试与校验：新增端到端 dry-run 测试，覆盖占位符替换、标题回退、payload
  结构；对 AI 响应引入 schema 校验和重试策略；引入快照测试验证 .formatted.html
  与最终 HTML 的一致性；引入 lint/typing（ruff, mypy）把关重复逻辑。
  - 提升交互体验：在 CLI 中提供 --stage、--resume、--inspect 等子命令，输出结构
  化日志（JSON 行）供后续分析；为常见错误（API Key 缺失、图片数量不足）提供清晰
  提示和建议。

  这些调整能让流水线更加可视化、可维护，并为后续扩展多平台或替换模型奠定良好架构
  基础。


以下任务按照推荐顺序列出。完成后请勾选对应复选框，便于追踪进度。

- [x] 统一配置：迁移 `config.ini` 至结构化配置（如 `config.toml`/JSON），集中定义 AI 阶段；提供迁移脚本。
- [x] 重构数据目录：采用 `data/<channel>/{raw,translated,formatted,titles,artifacts}` 结构，并更新脚本、清理策略。
- [x] 抽象 AI 基类：新增 `BaseAIGenerator`，让翻译/排版/标题继承并复用通用逻辑。
- [x] 统一 Prompt 管理：按阶段分目录存放模板，支持多模板加载。
- [x] 构建流水线编排：新增 `src/app/pipeline.py` 描述 `Fetch→Translate→Format→Title→Publish` 的依赖关系。
- [x] CLI 统一入口：提供 `pipeline run/resume/inspect/clean` 命令，输出结构化日志。
- [x] 模块化微信发布：拆分 `WeChatArticleWorkflow`，分离图片同步、HTML 注入、payload 构造逻辑。
- [ ] 更新发布脚本：精简 `publish_wechat_article.py`，完善或移除 `publish_content.py`。
- [ ] 引入 lint/typing：配置 `ruff`、`mypy` 等工具，并整合至 CI / 辅助脚本。
- [ ] 端到端 dry-run 测试：新增完整流程测试，覆盖占位符替换、标题回退、payload 校验。
- [ ] 增强错误提示：为常见异常提供明确诊断与恢复建议。
- [ ] 日志与监控：统一日志格式（JSON），记录阶段耗时与失败快照。

更新 Roadmap 后，请在完成任务时勾选对应复选框。并且每完成一步，自动提交一次git add . && git commit -m $本次修改的内容
