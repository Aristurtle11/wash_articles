# 洗稿机器

本工程专注洗稿

## 复制开发环境

激活python虚拟环境

执行：

```shell
pip install -r requirements.txt
```

## 使用方法

以下步骤假设你已经在项目根目录 `/home/user/wash_articles` 下，并且完成了依赖安装。

### 1. 第一次跑之前要做的准备

1. **复制默认配置：** 项目已经提供了 `config.ini`，直接使用即可。如果你想放在别的路径，可以复制一份，然后在运行命令时用 `--config` 指定新路径。
2. **理解目录结构：** 配置里的 `data_dir`、`processed_dir` 等路径决定了爬虫输出。默认会在 `data/processed` 里写入 `*.jsonl` 数据，在 `data/raw` 里存放下载的原始资源（例如图片），`data/logs` 里放日志，`data/state` 里放 cookies。
3. **准备默认请求头（可选）：** 如果目标网站需要特定请求头或 cookies，可以编辑 `src/settings/default_headers.template.json`，然后运行任意爬虫；系统会自动生成 `src/settings/default_headers.json`。也可以执行 `python fetch_cookies.py <目标URL>` 来用真实请求刷新 cookies。

### 2. 修改配置文件 `config.ini`

1. **选择默认爬虫：** 在 `[app]` 段落里把 `default_spider` 改成你想自动运行的名字，例如 `realtor`。
2. **调整保存位置：** 如果不希望把数据放在项目目录里，可以把 `[paths]` 中的各项替换成绝对路径。
3. **设置网络参数：** `[http]` 段落里的 `timeout`（超时时间，秒）、`min_delay`/`max_delay`（两次请求间的随机间隔，秒）、`max_attempts`（失败重试次数）、`backoff_factor`（指数退避倍率）都能直接修改。
4. **为每个爬虫准备专属配置：** 每个 `[spider:名字]` 段落都会作为字典传入爬虫实例，常见键是 `start_url`。例如：

   ```ini
   [spider:example]
   start_url = https://example.com/

   [spider:realtor]
   start_url = https://www.realtor.com/...具体文章链接...
   ```

### 3. 运行已有爬虫

1. **直接运行默认爬虫：**

   ```shell
   python main.py
   ```

   程序会读取 `config.ini`，使用 `[app]` 中 `default_spider` 对应的爬虫。

2. **运行指定爬虫：**

   ```shell
   python main.py --spider realtor
   ```

   如果你把配置放在其他位置，记得加上 `--config`：

   ```shell
   python main.py --spider realtor --config /path/to/other_config.ini
   ```

3. **查看输出在哪：** 爬虫结束后，处理过的数据会写入 `data/processed/<爬虫名>.jsonl`，原始资源会出现在 `data/raw/<爬虫名>/`，日志在 `data/logs/wash.log`。

### 4. 新增一个爬虫的流程

1. **创建爬虫文件：** 在 `src/spiders/` 里新增 `my_site_spider.py`，内容可以从 `example_spider.py` 拷贝后修改，最小示例如下：

   ```python
   from __future__ import annotations
   from typing import Iterable, Iterator

   from bs4 import BeautifulSoup
   from src.core.base_spider import BaseSpider
   from src.core.http_client import HttpRequest, HttpResponse


   class MySiteSpider(BaseSpider):
       name = "my_site"

       def start_requests(self) -> Iterable[HttpRequest]:
           yield HttpRequest(url=self.config["start_url"])

       def parse(self, response: HttpResponse) -> Iterator[dict]:
           soup = BeautifulSoup(response.text, "html.parser")
           title = soup.title.string.strip() if soup.title else ""
           yield {"source_url": response.url, "title": title}
   ```

   记得根据目标站点实际结构，补充你需要的解析逻辑。

2. **注册新爬虫：** 编辑 `src/spiders/__init__.py`：

   - 在文件顶部新增 `from .my_site_spider import MySiteSpider`
   - 在 `SPIDER_REGISTRY` 字典里加入 `MySiteSpider.name: MySiteSpider`

3. **为新爬虫写配置：** 在 `config.ini` 里新增：

   ```ini
   [spider:my_site]
   start_url = https://目标站点的入口地址
   ```

4. **运行测试：**

   ```shell
   python main.py --spider my_site
   ```

   如果代码报错，可以先用 `print()` 或日志定位问题；常见原因是 HTML 结构和预期不同。

### 5. 进阶：更新 cookies（可选）

有些网站需要经常刷新 cookies。可以在登录浏览器后复制目标页面地址，执行：

```shell
python fetch_cookies.py "https://目标站点的页面"
```

脚本会用当前配置请求该页面，把新的 cookies 写入 `data/state/cookies.txt` 并更新默认请求头。

按照以上步骤操作，哪怕是第一次接触爬虫的初级程序员，也可以顺利配置并运行本项目。
