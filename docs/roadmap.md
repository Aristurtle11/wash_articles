# 工程优化 Roadmap

以下任务按照推荐顺序列出。完成后请勾选对应复选框，便于追踪进度。

- [x] 统一配置：迁移 `config.ini` 至结构化配置（如 `config.toml`/JSON），集中定义 AI 阶段；提供迁移脚本。
- [x] 重构数据目录：采用 `data/<channel>/{raw,translated,formatted,titles,artifacts}` 结构，并更新脚本、清理策略。
- [x] 抽象 AI 基类：新增 `BaseAIGenerator`，让翻译/排版/标题继承并复用通用逻辑。
- [x] 统一 Prompt 管理：按阶段分目录存放模板，支持多模板加载。
- [x] 构建流水线编排：新增 `src/app/pipeline.py` 描述 `Fetch→Translate→Format→Title→Publish` 的依赖关系。
- [x] CLI 统一入口：提供 `pipeline run/resume/inspect/clean` 命令，输出结构化日志。
- [ ] 模块化微信发布：拆分 `WeChatArticleWorkflow`，分离图片同步、HTML 注入、payload 构造逻辑。
- [ ] 更新发布脚本：精简 `publish_wechat_article.py`，完善或移除 `publish_content.py`。
- [ ] 引入 lint/typing：配置 `ruff`、`mypy` 等工具，并整合至 CI / 辅助脚本。
- [ ] 端到端 dry-run 测试：新增完整流程测试，覆盖占位符替换、标题回退、payload 校验。
- [ ] 增强错误提示：为常见异常提供明确诊断与恢复建议。
- [ ] 日志与监控：统一日志格式（JSON），记录阶段耗时与失败快照。

更新 Roadmap 后，请在完成任务时勾选对应复选框。并且每完成一步，自动提交一次git add . && git commit -m $本次修改的内容
