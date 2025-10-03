# 爬虫 HTTP 上下文同步计划

## 1. 问题背景

当前爬虫工作流分为两步：
1.  使用 `scripts/fetch_cookies.py`（基于 Playwright）模拟真实浏览器，通过 JavaScript 质询，获取并保存有效的 `cookies.txt`。
2.  运行 `main.py --spider <name>` 时，核心爬虫 `HttpClient`（基于 `urllib`）加载 `cookies.txt` 并发起实际的爬取请求。

尽管 Cookie 是有效的，但第二步依然被服务器以 `429 Too Many Requests` 拒绝。根本原因在于**请求上下文的不一致性**：服务器在处理每一次请求时，不仅验证 Cookie，还会检查请求的“指纹”，尤其是请求头（Headers）。

- **Playwright 客户端**：拥有完整的、浏览器级别的请求头，被服务器信任。
- **HttpClient 客户端**：仅携带了 Cookie，但其自身的请求头是 Python `urllib` 库的默认值或一个简化的静态模板，这暴露了其作为自动化程序的本质。

服务器检测到持有有效“门票”（Cookie）的访问者，其“外貌特征”（请求头）与当初领票的人完全不符，因此判定为机器人行为并予以拦截。

## 2. 核心目标

**实现请求上下文的同步与持久化**。

我们的目标是，让执行爬取任务的 `HttpClient` 在发出请求时，能够完美地**复用** Playwright 成功通过验证时的**完整浏览器上下文**（主要是请求头），从而确保服务器在每一次交互中都认为它是一个真实的浏览器。

## 3. 详细实施计划

我们将分三个阶段，步步递进地完成改造。

### 阶段一：捕获并持久化完整的浏览器请求头

在这一阶段，我们的主战场是 `scripts/fetch_cookies.py`，需要赋予它捕获并保存请求头的新能力。

**步骤 1.1：确定请求头的保存位置**

为了与 `cookies.txt` 的管理方式保持一致，我们将把捕获的请求头保存为一个新的 JSON 文件。

-   **操作**：在 `config.toml` 的 `[paths]` 部分，新增一个配置项 `header_jar`。
    ```toml
    [paths]
    # ... (已有配置)
    cookie_jar = "data/state/cookies.txt"
    header_jar = "data/state/headers.json" # <-- 新增此行
    ```

**步骤 1.2：更新配置加载模块**

为了让程序能识别新的 `header_jar` 配置。

-   **操作**：修改 `src/settings/loader.py` 中的 `PathSettings` 数据类（或对应的 Pydantic模型），增加 `header_jar: str` 字段，使其能够正确解析 `config.toml` 中的新配置。

**步骤 1.3：升级 `scripts/fetch_cookies.py` 以捕获请求头**

这是本阶段的核心。我们需要利用 Playwright 的网络拦截能力。

-   **操作**：
    1.  在 `fetch` 函数中，当 Playwright 导航到目标页面时，我们需要监听 `request` 事件。
    2.  通过事件监听，捕获到浏览器为加载主文档（`main_frame`）而发出的那个**初始请求**。
    3.  从这个请求对象中，提取出**所有的请求头** (`request.headers`)。
    4.  将提取到的请求头字典（需要过滤掉 Playwright 内部或 Cookie 相关的头，避免重复）序列化为 JSON 格式。
    5.  将其写入由 `config.paths.header_jar` 指定的文件路径中（例如 `data/state/headers.json`）。

### 阶段二：让 `HttpClient` 使用捕获的浏览器上下文

现在，我们需要改造核心的 `HttpClient`，让它“智能地”加载并使用我们新捕获的请求头。

**步骤 2.1：修改 `HttpClient` 的初始化逻辑**

-   **操作**：
    1.  定位到 `src/core/http_client.py` 中的 `HttpClient.__init__` 方法。
    2.  修改其加载默认请求头的逻辑。当前的逻辑可能是直接从 `src/settings/default_headers.template.json` 加载。
    3.  新的逻辑应该是：
        a.  首先，检查 `config.paths.header_jar` 指定的路径（如 `data/state/headers.json`）是否存在。
        b.  如果**存在**，则加载这个 JSON 文件作为默认请求头。这将是最高优先级的动态“指纹”。
        c.  如果**不存在**，则回退到原有的逻辑，加载静态的 `default_headers.template.json` 文件。这保证了在没有执行过 `fetch_cookies.py` 时程序的兼容性。
    4.  确保加载后，将 `Cookie` 头从请求头中移除，因为它会由 `CookieJar` 自动管理，手动添加可能导致冲突。

### 阶段三：执行与验证

完成代码修改后，我们需要一个清晰的执行流程来验证方案的有效性。

**步骤 3.1：定义新的标准作业流程 (SOP)**

1.  **第一步：生成上下文**
    -   运行 `python scripts/fetch_cookies.py <url>`。
    -   **预期结果**：`data/state/` 目录下会生成或更新两个文件：`cookies.txt` 和 `headers.json`。

2.  **第二步：执行爬虫**
    -   运行 `python main.py --spider realtor`。
    -   **预期结果**：
        -   `HttpClient` 会加载 `headers.json` 和 `cookies.txt`。
        -   爬虫发出的请求将携带与真实浏览器几乎一致的请求头和 Cookie。
        -   服务器不再返回 `429` 错误，爬取任务成功执行。

## 4. 风险与后续步骤

-   **动态令牌风险**：如果 `realtor.com` 不仅校验静态请求头，还校验随时间或请求变化的动态令牌（如 `x-csrf-token`），本计划可能依然会失败。如果发生这种情况，下一步的计划将是：在阶段一捕获这个动态令牌，并在阶段二的 `HttpClient` 中设计一种机制来更新和使用它。
-   **文档更新**：计划成功实施后，需要更新 `docs/scripts.md` 和 `docs/core_layer.md`，反映 `fetch_cookies.py` 的新功能和 `HttpClient` 的新行为。

此计划通过捕获并复用成功的请求上下文，旨在从根本上解决爬虫被识别的问题，使项目更加健壮和可靠。
