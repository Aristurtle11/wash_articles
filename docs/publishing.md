# 发布流程指南（草稿）

本文档描述即将上线的发布框架骨架，帮助后续在微信和其他自媒体平台落地自动化。实现细节仍在迭代中。

## 目录结构
- `src/platforms/`：跨平台抽象与微信适配器骨架。
- `src/security/`：凭证与密钥加载接口。
- `src/services/publishing_service.py`：发布流程协调器。
- `scripts/publish_content.py`：命令行入口。
- `scripts/get_wechat_token.py`：获取并缓存 access_token。
- `scripts/upload_wechat_image.py`：批量上传 `images/` 目录下的 `image_*.{jpg,png...}` 为永久素材，记录 `media_id` 与 URL。
- `scripts/format_articles.py`：将译文生成 `.formatted.html`，供统一排版。
- `scripts/publish_wechat_article.py`：一键完成图片上传、占位符替换与草稿创建。

## 配置要求
- 通过环境变量提供微信公众号凭证：`export WECHAT_APP_ID=...`、`export WECHAT_APP_SECRET=...`。
- `data/state/wechat_token.json` 将用于缓存 Token（后续实现）。
- 不允许在任何配置文件中存储上述敏感信息。

## 下一步工作
- 完成凭证缓存、令牌刷新与文件权限设置（token 已支持缓存与过期刷新）。
- 实现图片上传、占位符替换与正式发布逻辑。
- 扩展自动化测试，覆盖主要分支路径。
- 编写平台工厂装配代码以及完整 CLI 执行路径。
