# 爬虫 HTTP 上下文同步计划

本文档旨在系统性地分析并解决当前爬虫项目在面对高级反爬虫机制时遇到的挑战。

## 1. 现象描述 (Phenomenon)

当前项目中存在两种截然不同的运行结果，具体表现如下：

-   **成功的场景**:
    -   **命令**: `python scripts/fetch_cookies.py https://www.realtor.com/news/...`
    -   **行为**: 该脚本使用 **Playwright** 库驱动一个真实的无头浏览器内核 (Chromium) 访问目标网站。
    -   **结果**: 脚本**运行成功**。它能够正确执行网站部署的 JavaScript 质询 (JS Challenge)，通过服务器的验证，最终获取到有效的会话 Cookie 并将其保存到 `data/state/cookies.txt` 文件中。

-   **失败的场景**:
    -   **命令**: `python main.py --spider realtor`
    -   **行为**: 该命令启动核心爬虫。爬虫的 `HttpClient` (基于 Python 内置的 `urllib` 库) 会首先加载 `data/state/cookies.txt` 文件，然后带着这些有效的 Cookie 去请求目标页面。
    -   **结果**: 爬虫**运行失败**。尽管携带了由真实浏览器环境获取的有效 Cookie，服务器依然拒绝了请求，并返回 `urllib.error.HTTPError: HTTP Error 429: Too Many Requests` 错误。

## 2. 问题定义 (Problem)

**核心问题是：请求上下文的不一致性导致爬虫身份暴露。**

我们的工作流被割裂为两个独立的阶段，每个阶段使用行为特征完全不同的客户端与服务器交互：

1.  **认证阶段 (`fetch_cookies.py`)**: 使用一个**高度伪装的、类似真人的客户端** (Playwright) 通过了服务器的身份验证，拿到了“门票” (Cookie)。
2.  **爬取阶段 (`main.py`)**: 换上一个**简陋的、具有明显机器人特征的客户端** (`HttpClient`)，虽然手持有效的“门票”，但其本身的“外貌”和“行为”与领票者完全不符，因此在“二次安检”时被服务器识别并拦截。

## 3. 问题分析 (Analysis)

现代网站的反爬虫系统是多维度、全流程的，它不仅仅在入口处进行一次性验证。服务器在处理**每一次请求**时，都会对客户端进行指纹分析。

-   **Playwright 客户端的指纹**:
    -   **请求头 (Headers)**: 发送一套非常完整且复杂的请求头，包含了 `User-Agent`, `Accept-Language`, `Sec-Ch-Ua` 等十几个字段，这些字段共同构成了一个难以与真实浏览器区分的“指纹”。
    -   **JavaScript 执行能力**: 能够执行 JS，从而通过动态计算或环境检测类的反爬虫脚本。
    -   **TLS 指纹**: 在建立 HTTPS 连接时的握手信息也与主流浏览器一致。
    -   **结论**: 服务器信任这个客户端，并授予其 Cookie。

-   **HttpClient (`urllib`) 客户端的指纹**:
    -   **请求头 (Headers)**: 仅使用了项目中一个静态、简化的 `default_headers.template.json` 作为模板，缺少大量浏览器特有的请求头字段。这是一个非常明显的机器人特征。
    -   **JavaScript 执行能力**: 完全没有。
    -   **TLS 指纹**: 与 Python 库的默认行为一致，和浏览器不同。
    -   **结论**: 尽管它出示了有效的 Cookie，但服务器通过对其请求头的分析，轻松识别出这是一个自动化程序，并触发了 `429` 速率限制/拒绝策略。

**根本原因**: 我们成功地用一个“特工”骗取了信任，但在执行任务时却派出了一个“机器人”。服务器的防御机制在每一次交互中都会进行身份校验，它发现持有有效凭证的访问者，其指纹特征与最初建立信任时的特征完全不匹配，因此判定为非法访问。

## 4. 修改计划 (Modification Plan)

为了解决这个问题，我们必须**实现请求上下文的同步与持久化**。核心目标是让执行爬取任务的 `HttpClient` 能够完美地**复用** Playwright 成功通过验证时的**完整浏览器指纹**（主要是请求头）。

### 阶段一：捕获并持久化完整的浏览器请求头

在这一阶段，我们将升级 `scripts/fetch_cookies.py`，使其在获取 Cookie 的同时，捕获并保存当时浏览器发送的**所有请求头**。

-   **步骤 1.1：在 `config.toml` 中定义请求头的保存位置**
    -   在 `[paths]` 部分新增 `header_jar = "data/state/headers.json"`。
-   **步骤 1.2：更新 `src/settings/loader.py` 以识别新配置**
    -   在 `PathSettings` 数据类中增加 `header_jar: Path` 字段。
-   **步骤 1.3：升级 `scripts/fetch_cookies.py` 以捕获并保存请求头**
    -   利用 Playwright 的 `page.on("request", ...)` 事件监听器。
    -   捕获主导航请求 (`request.is_navigation_request()`) 的所有请求头。
    -   将捕获的请求头（移除 `Cookie` 字段以避免冲突）以 JSON 格式写入 `header_jar` 指定的文件中。

### 阶段二：让 `HttpClient` 使用捕获的浏览器上下文

改造核心的 `HttpClient`，让它“智能地”加载并使用我们新捕获的请求头。

-   **步骤 2.1：修改 `src/core/http_client.py` 的初始化逻辑**
    -   修改 `HttpClient.__init__` 的构造函数，不再直接接收 `default_headers` 字典，而是接收 `PathSettings` 对象。
    -   在 `__init__` 内部，实现新的加载逻辑：
        a.  优先检查并加载 `paths.header_jar` (`headers.json`) 文件。
        b.  如果该文件不存在或加载失败，则**回退**到加载静态的 `default_headers.template.json` 文件。
-   **步骤 2.2：更新 `HttpClient` 的实例化调用**
    -   修改 `src/app/runner.py` 中创建 `HttpClient` 实例的代码，将 `config.paths` 对象传递给其构造函数。

### 阶段三：执行与验证

完成代码修改后，定义新的标准作业流程 (SOP) 以验证方案的有效性。

-   **步骤 3.1：生成上下文**
    -   运行 `python scripts/fetch_cookies.py <url>`。
    -   **预期结果**: `data/state/` 目录下同时生成 `cookies.txt` 和 `headers.json`。
-   **步骤 3.2：执行爬虫**
    -   运行 `python main.py --spider realtor`。
    -   **预期结果**: `HttpClient` 加载 `headers.json` 和 `cookies.txt`，请求成功，不再出现 `429` 错误。

### 4. 风险与后续步骤

-   **动态令牌风险**：如果目标网站还校验随时间变化的动态令牌（如 `x-csrf-token`），本计划可能依然会失败。届时需要进一步扩展此方案以处理动态令牌。
-   **文档更新**：计划成功实施后，需要更新相关模块的文档（如 `docs/scripts.md` 和 `docs/core_layer.md`）以反映新的工作流程。