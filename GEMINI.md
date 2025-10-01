# Project Overview

This project is a Python-based automated pipeline designed to fetch articles from websites, translate them using the Gemini AI model, and then publish them as drafts to the WeChat Official Accounts platform. The entire workflow is configurable through a `config.toml` file and can be executed via a series of command-line scripts.

## Core Technologies

*   **Python 3.11+**: The primary programming language.
*   **Gemini AI**: Used for translating and formatting articles.
*   **BeautifulSoup**: For parsing HTML and extracting article content.
*   **TOML**: For configuration management.

## Architecture

The project follows a modular architecture, with distinct components for different stages of the pipeline:

*   **Spiders**: Responsible for fetching raw article content and images from target websites. Each spider is a subclass of `BaseSpider` and implements the logic for a specific site.
*   **Pipelines**: A series of processing steps that transform the raw data. This includes saving the data, translating text, and formatting content.
*   **AI Nodes**: These modules interact with the Gemini API for tasks like translation, formatting, and title generation. They are configured via `config.toml` and use prompt templates stored in the `prompts/` directory.
*   **Platforms**: Contains platform-specific clients, with the initial focus on the WeChat Official Accounts platform. This includes API clients for handling authentication, media uploads, and draft creation.
*   **Services**: High-level workflows that orchestrate the entire process, from fetching content to publishing a draft. The `wechat_workflow.py` is a key example, coordinating image uploads and article creation.
*   **Scripts**: A collection of command-line scripts that act as the entry points for various pipeline stages, such as `translate_texts.py` and `publish_wechat_article.py`.

# Building and Running

## Setup

1.  **Create a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure environment variables:**
    ```bash
    export GEMINI_API_KEY="<Your Gemini API Key>"
    export WECHAT_APP_ID="<Your WeChat App ID>"
    export WECHAT_APP_SECRET="<Your WeChat App Secret>"
    ```

## Running the Pipeline

The pipeline is executed in several steps, controlled by individual scripts:

1.  **Fetch Articles**: Run a spider to download articles and images.
    ```bash
    # Run the default spider defined in config.toml
    python main.py

    # Run a specific spider
    python main.py --spider realtor
    ```

2.  **Translate Articles**: Use Gemini to translate the downloaded text.
    ```bash
    python scripts/translate_texts.py --channel realtor
    ```

3.  **Format Articles**: Convert the translated text into HTML.
    ```bash
    python scripts/format_articles.py --channel realtor
    ```

4.  **Publish to WeChat**: Upload images and create a draft article in WeChat.
    ```bash
    python scripts/publish_wechat_article.py --channel realtor
    ```

# Development Conventions

*   **Configuration**: All project settings, including API keys, file paths, and pipeline stages, are managed in the `config.toml` file.
*   **Modularity**: The project is divided into loosely coupled modules, making it easy to extend. New spiders can be added by creating a new class in the `src/spiders` directory and inheriting from `BaseSpider`.
*   **Logging**: The application uses Python's built-in `logging` module. Logs are configured in `src/utils/logging.py` and are saved to the `data/logs` directory.
*   **Testing**: The `tests/` directory contains unit and integration tests. While the test coverage is not exhaustive, it provides a foundation for verifying the core components, such as the WeChat workflow.
