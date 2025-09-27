# 发布流程指南（草稿）

本文档描述即将上线的发布框架骨架，帮助后续在微信和其他自媒体平台落地自动化。实现细节仍在迭代中。

## 目录结构
- `src/platforms/`：跨平台抽象与微信适配器骨架。
- `src/security/`：凭证与密钥加载接口。
- `src/services/publishing_service.py`：发布流程协调器。
- `scripts/publish_content.py`：命令行入口。

## 配置要求
- 通过环境变量提供微信公众号凭证：`export WECHAT_APP_ID=...`、`export WECHAT_APP_SECRET=...`。
- `data/state/wechat_token.json` 将用于缓存 Token（后续实现）。
- 不允许在任何配置文件中存储上述敏感信息。

## 下一步工作
- 完成凭证缓存、令牌刷新与文件权限设置。
- 实现图片上传、占位符替换与正式发布逻辑。
- 扩展自动化测试，覆盖主要分支路径。
- 编写平台工厂装配代码以及完整 CLI 执行路径。
