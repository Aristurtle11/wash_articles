# Repository Guidelines

## Project Structure & Module Organization
Core crawler logic lives in `src`. `src/core` contains HTTP client and spider base classes; `src/spiders` holds concrete crawlers; `src/pipelines` and `src/repositories` handle post-processing and persistence; `src/settings` centralizes configuration helpers; `src/utils` and `src/app` wrap orchestration bits. Shared prompts and documents sit in `prompts/` and `docs/`. Runtime artifacts and checkpoints are under `data/` (`raw/`, `processed/`, `logs/`, `state/`). Tests stay in `tests/`, mirroring the module names they verify. Scripts for maintenance and cookie management live in `scripts/`.

## Build, Test, and Development Commands
`pip install -r requirements.txt` installs Python dependencies. `python main.py` runs the default spider declared in `config.toml`; add `--spider name` or `--config path` for overrides. Use `python scripts/fetch_cookies.py <url>` to refresh session data. `python -m pytest` executes the automated test suite; append `-k`, `-s`, or `--maxfail=1` while iterating locally.
`python scripts/get_wechat_token.py` fetches and caches the WeChat access token (set `WECHAT_APP_ID/WECHAT_APP_SECRET` first). `python scripts/upload_wechat_image.py --channel <name>` 上传所有 `image_*` 素材。`python scripts/format_articles.py --channel <name>`（通过 `--input` 指定译文）可生成 `.formatted.html`。最终利用 `python scripts/publish_wechat_article.py --channel <name> --title "…"` 完成草稿提交。

## Coding Style & Naming Conventions
Stick to Python 3.11+, four-space indentation, and keep `from __future__ import annotations` at the top of new modules. Type annotate public APIs and prefer explicit return types. Classes use `PascalCase`, modules and functions use `snake_case`, and spider names match their `BaseSpider.name` attribute. Keep imports sorted by standard-library, third-party, and local packages. Favor small, composable methods and reuse utilities before adding new helpers.

## Testing Guidelines
All new behavior requires a focused pytest covering success and failure paths. Place files under `tests/` using `test_<module>.py`, and mirror fixtures like `tmp_path` when touching the filesystem. Mock network access; do not rely on live HTTP endpoints. Aim to keep coverage parity with existing modules, and expand shared fixtures when multiple spiders need the same setup.

## Commit & Pull Request Guidelines
Follow the repository’s short, descriptive commit style—single-line summaries in Chinese (or English when clearer), written in present tense (e.g., "补充 Realtor 爬虫过滤"). Group related changes per commit. Pull requests should describe the problem, the solution, and testing evidence; link tracker issues when available and add console snippets or sample output from `data/<channel>/artifacts/` to illustrate results.
