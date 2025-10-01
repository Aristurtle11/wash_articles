# AI 翻译组件使用说明

本文介绍如何使用项目中新引入的 AI 翻译组件，将现有的 `.txt` 文本（例如 `realtor` 爬虫抓取到的 `*_core_paragraphs.txt`）通过 Gemini API 翻译成简体中文。

## 环境准备

1. **配置 Gemini API Key**
   - 在运行翻译脚本前，请先设置环境变量：
     ```bash
     export GEMINI_API_KEY="你的 API Key"
     ```
   - 或者执行脚本时使用 `--api-key` 参数传入。

2. **检查配置文件**
   - `config.toml` 的 `[pipeline.stages.translate]` 段集中配置翻译阶段。例如：
     ```toml
     [pipeline.stages.translate]
     kind = "translation"
     model = "gemini-2.5-flash"
     prompt_path = "prompts/translation_prompt.txt"
     output_dir = "data/{channel}/translated"
     input_glob = "data/{channel}/raw/**/*.txt"
     target_language = "zh-CN"
     timeout = 30
     thinking_budget = null
     ```
   - 可在此段落调整模型、Prompt、输出目录或目标语言。

3. **Prompt 模版**
   - 项目在 `prompts/translation_prompt.txt` 中预置了通用翻译模板，包含 `{language}` 与 `{text}` 占位符。你可以根据需要调整翻译风格或规则。

## 运行翻译脚本

脚本位置：`scripts/translate_texts.py`。该脚本会根据配置或命令行参数批量翻译匹配到的文本文件。

### 基本用法

```bash
python scripts/translate_texts.py
```

- 默认会按 `config.toml` 中 `[pipeline.stages.translate]` 的 `input_glob` 查找文本文件（如 `data/{channel}/raw/**/*.txt`），
- 译文统一写入 `data/<channel>/translated/`，文件名为原文件名加上 `.translated.txt`。

### 常用参数

- `--input PATTERN [PATTERN ...]`：指定一个或多个 glob 模式，覆盖默认的 `input_glob`。例如：
  ```bash
  python scripts/translate_texts.py --input "data/realtor/raw/*_core_paragraphs.txt"
  ```
- `--prompt PATH`：指定新的 prompt 文件。
- `--output-dir DIR`：修改译文输出目录。
- `--language LANG`：调整目标语言，例如 `--language zh-TW`。
- `--model NAME`：切换 Gemini 模型。
- `--relative-to PATH`：保持输出目录结构与 `PATH` 之下的相对路径一致，默认使用当前频道的 `data/<channel>/raw/`。
- `--overwrite`：允许覆盖已存在的译文文件。
- `--api-key KEY`：直接传入 API Key，优先级高于环境变量。

示例：
```bash
python scripts/translate_texts.py \
  --input "data/realtor/raw/*_core_paragraphs.txt" \
  --output-dir data/realtor/translated \
  --language zh-CN \
  --overwrite
```

## 输出结构

- 译文默认保存在 `data/<channel>/translated/` 目录下，与原始文件保持相同的相对结构，文件名追加 `.translated.txt`。
- 例如，若原文为 `data/realtor/raw/example_core_paragraphs.txt`，译文会保存为：
  `data/<channel>/translated/example_core_paragraphs.translated.txt`

## 调试与日志

- 翻译脚本会打印进度和警告信息。若某个文件已经存在译文且未使用 `--overwrite`，脚本会跳过并记录日志。
- 若 API 返回错误或网络异常，脚本会在标准输出/日志中给出具体原因。

## 扩展建议

- 如需支持多语言翻译或更复杂的策略，可在 `prompts/` 中编写不同的模板，通过命令行参数切换。
- 可根据需求在 `Translator` 层扩展元数据记录（例如保存 prompt 版本、翻译时间），便于审计和追踪。

希望本组件能帮助你快速将抓取的英文文章转换为中文。如果在使用过程中遇到任何问题，欢迎继续提问或反馈。
