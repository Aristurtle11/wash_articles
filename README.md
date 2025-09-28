# 洗稿机器

本仓库提供一条从采集原始文章、提取资源，到使用 Gemini 翻译，再将图文素材推送到微信公众号草稿箱的自动化流水线。下文按时间顺序列出需要准备的环境、核心命令以及数据产物位置。

## 环境准备

1. **基础依赖**
   - Python 3.11+
   - 推荐使用虚拟环境：`python -m venv .venv && source .venv/bin/activate`
   - 安装项目依赖：
     ```bash
     pip install -r requirements.txt
     ```
2. **外部凭证**
   - Gemini：`export GEMINI_API_KEY="<你的API Key>"`
   - 微信公众号：`export WECHAT_APP_ID="..."` 与 `export WECHAT_APP_SECRET="..."`

## Step 1：抓取文章与图片

1. **配置爬虫**（`config.ini`）
   - `[app] default_spider` 决定默认执行的爬虫，例如 `realtor`。
   - `[paths]` 控制输出目录，默认生成于 `data/`。
   - 每个 `[spider:<name>]` 段定义入口 URL 及自定义参数。
2. **运行爬虫**
   ```bash
   python main.py                # 使用默认爬虫
   python main.py --spider realtor
   ```
3. **产出目录**
   - 原始文本、图片：`data/raw/<channel>/`
   - 处理后的 JSONL：`data/processed/<channel>.jsonl`
   - 日志：`data/logs/`

若目标站点需要特殊 Cookie，可通过 `scripts/fetch_cookies.py <URL>` 预先刷新 `data/state/cookies.txt`。

## Step 2：使用 AI 翻译文章

1. **确认配置**
   - `config.ini` 的 `[ai]` 段定义默认模型、Prompt、输出目录与输入文件的 glob 模式。
   - Prompt 模板位于 `prompts/translation_prompt.txt`，可按需修改语气与约束。
2. **执行翻译**
   ```bash
   python scripts/translate_texts.py
   ```
   常用参数：
   - `--input "data/raw/realtor/*_core_paragraphs.txt"` 指定翻译源。
   - `--output-dir data/translated/realtor` 调整译文目录。
   - `--overwrite` 允许覆盖旧译文。
3. **产出目录**
   - 译文默认写入 `data/translated/<channel>/...*.translated.txt`
   - 输入文件与译文保持相对目录一致，便于后续匹配图片资源。

若遇到 API 限额或网络问题，脚本会给出详细日志，便于重试。

## Step 3：AI 排版译文

1. **准备格式化**
   ```bash
   python scripts/format_articles.py
   ```
   常用参数：
   - `--input "data/translated/realtor/*.translated.txt"` 指定需要排版的译文。
   - `--output-dir data/translated/realtor` 改变 HTML 输出位置。
   - `--overwrite` 允许覆盖已有 `.formatted.html`。
2. **结果**
   - 每个译文旁会生成对应的 `*.formatted.html`，内含简单 CSS 与结构化 HTML，但仍保留 `{{[Image N]}}` 占位符，方便后续替换。

## Step 4：上传微信图文草稿

1. **验证凭证**
   ```bash
   python scripts/get_wechat_token.py --token-cache data/state/wechat_token.json
   ```
   - `--force-refresh` 可忽略缓存重新获取。
2. **上传并生成草稿**
   ```bash
   python scripts/publish_wechat_article.py \
     --channel realtor \
     --title "示例标题" \
     --dry-run          # 先查看预览 JSON（可选）
   ```
   - 脚本会自动上传 `data/raw/<channel>/images/image_*.{jpg,png}` 为永久素材，并将返回的 `media_id` 与 `url` 注入译文。
   - 如存在 `.formatted.html`，会以该 HTML 作为稿件主体；否则退回 Markdown→HTML 转换流程。
   - 去掉 `--dry-run` 后会调用微信 `draft/add` 接口，成功时输出草稿 `media_id`。
3. **命令输出**
   - 每张图片对应的 `media_id` 与 URL
   - 提交给微信的 JSON 结构，便于审查或复用

如仅需单独上传素材，可使用：
```bash
python scripts/upload_wechat_image.py --channel realtor
```

## 常用辅助脚本

- `scripts/clean_project.sh`：清理缓存与数据产物。
- `scripts/publish_content.py`：后续可扩展为多平台发布入口。
- `scripts/translate_texts.py --help`、`scripts/publish_wechat_article.py --help` 获取详尽参数说明。

## 目录速览

```
├─ config.ini                 # 统一配置入口（爬虫、路径、AI 参数）
├─ data/                      # 爬取数据、译文、状态缓存
├─ prompts/                   # 翻译 Prompt 模板
├─ scripts/                   # 抓取后处理、翻译、发布脚本
├─ src/
│  ├─ core/                   # HTTP 客户端、爬虫基类
│  ├─ platforms/wechat/       # 微信凭证、素材上传、草稿客户端
│  ├─ services/wechat_workflow.py  # 图文发布 orchestrator
│  └─ ...
└─ tests/                     # 针对发布工作流的示例测试
```

按照以上步骤即可完成“抓取 → 翻译 → 草稿上传”的整条流水线。遇到问题时，可查看 `data/logs/` 下的日志或运行脚本的 `--help` 获取更多调试信息。
