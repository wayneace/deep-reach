# P2 搜索/阅读后端设计（Tavily / Brave / Firecrawl / Bright Data）

日期：2026-11-09

## 1. 意图

当前 P2 只有 `jina` 一个后端，且只能做 URL → Markdown。agent 缺少一个
通用的网页搜索入口，也缺少在 Jina 失败后继续降级的能力。

本设计新增四个第三方 P2 服务：

- **Tavily**：搜索 + URL 提取
- **Brave Search**：网页搜索
- **Firecrawl**：搜索 + 网页抓取（Markdown）
- **Bright Data**：SERP 搜索 + Web Unlocker 反爬抓取

Bright Data 的强项是反爬抓取，因此：

- **搜索链放在最后**：Tavily → Brave → Firecrawl → Bright Data
- **阅读链作为最后的强兜底**：Jina → Firecrawl → Tavily → Bright Data

## 2. 目标与非目标

### 目标

- 新增 `web search` action，让 agent 能在没有站点专属 API 时做通用网页搜索。
- 扩展 `web read` 和现有 4 个阅读动作的 P2 降级链。
- 所有 provider 的 key 都可选；缺 key 只跳过该 provider，不阻塞其他 provider。
- 保持只读、免费额度优先、失败可降层。
- 对 401/403/429/5xx 给出可行动的错误码。

### 非目标

- 不做 crawl / map / batch / 浏览器自动化；只做 search / read。
- 不做本地月度额度账本（见 §9，后续版本）。
- 不自动充值、不接付费调用；只使用各家的免费额度/免费 credit。
- 不把通用搜索挂到站点专属 `search` 上（结果语义不对）。

## 3. 方案选择

### 方案 A（采用）

新增 `web search`（P2-only），并扩展阅读动作的 P2 链。

- 优点：语义清晰；通用搜索和站点搜索分开；阅读链可复用；改动局限在
  `channels.yaml` + 新后端 + 测试。
- 缺点：`web` channel 在没有任何搜索 key 时会从 `ready` 变为 `degraded`
  （read 仍可用），需要更新相关测试。

### 方案 B（否决）

把通用搜索挂到每个站点的 `search` action 上，用 `site:` 限定域名。

- 否决原因：结果形状、排序、分页都与站点原生搜索不同；Brave/Bright Data
  对 `site:` 的支持和额度消耗不稳定；容易误导 agent。

### 方案 C（否决）

新增独立 `search` channel。

- 否决原因：和 `web` 边界重复；多一个顶层 channel，收益不足。

## 4. 动作与后端顺序

### 4.1 新增 `web search`

参数：`query`，`limit`（默认 10，最大 20）。

顺序：

1. `tavily-search` — `search.tavily.api_key`
2. `brave-search` — `search.brave.api_key`
3. `firecrawl-search` — `search.firecrawl.api_key`
4. `brightdata-serp` — `search.brightdata.api_token` + `search.brightdata.serp_zone`

### 4.2 阅读链

`web read`：

1. `http-read`（P0）
2. `jina`（P2，无 key 也可用，20 RPM）
3. `firecrawl-scrape`（P2）
4. `tavily-extract`（P2）
5. `brightdata-unlocker`（P2）

以下动作追加同样的 P2 阅读链（在现有 `jina` 之后）：

- `amazon product`：`opencli-amazon` → `jina` → `firecrawl-scrape` →
  `tavily-extract` → `brightdata-unlocker`
- `kickstarter read`、`cnipa read`、`copyright read`：
  `http-read` → `jina` → `firecrawl-scrape` → `tavily-extract` →
  `brightdata-unlocker`

## 5. Key 配置

```yaml
search:
  tavily:
    api_key: ""
  brave:
    api_key: ""
  firecrawl:
    api_key: ""
  brightdata:
    api_token: ""
    serp_zone: ""
    unlocker_zone: ""
  jina:
    api_key: ""
```

说明：

- Bright Data 的 SERP 和 Web Unlocker 是不同 zone，分别配置。
- Brave 当前免费额度是每月 $5 credit（约 1,000 次 search），且需要展示
  Brave attribution；不是旧的无条件 2,000 次免费计划。
- Bright Data 免费额度 5,000 credits/月，SERP/Unlocker 共用。
- Tavily 1,000 credits/月（basic search 1 credit）。
- Firecrawl 1,000 credits/月（scrape 1 credit/页，search 2 credits/10 条）。

## 6. 实现结构

新增文件：

```text
deep_reach/backends/tavily.py      # tavily-search, tavily-extract
deep_reach/backends/brave.py       # brave-search
deep_reach/backends/firecrawl.py   # firecrawl-search, firecrawl-scrape
deep_reach/backends/brightdata.py  # brightdata-serp, brightdata-unlocker
```

共享逻辑：

- 复用 `backends/http.py` 的 `fetch` / `fetch_json`（URL 校验、TLS、gzip、
  超时、重定向校验）。
- 为 P2 增加可选的 HTTP 状态码映射：401/403 → `NEED_SETUP`，402/429 →
  `QUOTA_EXHAUSTED`，其余保持现有映射。
- `brightdata-unlocker` 复用 `public.py` 的 `html_to_text`。
- 所有 item 通过 `make_item(source=channel.name, category=channel.category,
  platform="web", title, url, text, backend=spec.label)` 输出。

## 7. 错误与降级语义

P2 provider 的错误映射：

| HTTP / 情况 | 错误码 | 是否继续降层 |
|---|---|---|
| 401 / 403 | `NEED_SETUP` | 是 |
| 402 / 429 | `QUOTA_EXHAUSTED` | 是 |
| 404 | `NOT_FOUND` | 否（终止） |
| 5xx / 网络 | `UPSTREAM_BROKEN` | 是 |
| 超时 | `TIMEOUT` | 是 |
| 返回空/无法解析 | `UPSTREAM_BROKEN` | 是 |

说明：

- P0/P1 的 `RATE_LIMITED` 终止策略不变。
- P2 的 429 视为「该 provider 的免费额度不可用」，映射为
  `QUOTA_EXHAUSTED`，允许继续尝试下一个 P2 provider。这是本设计唯一的
  语义扩展。
- 搜索成功但结果为空：返回 `[]`，视为成功，不继续降层。

## 8. 测试

单元测试（不访问网络）：

- 每个 provider 的请求形状：URL、method、headers、body 参数。
- 每个 provider 的响应解析：正常结果、空结果、缺字段、坏 JSON。
- 错误映射：401/403/402/429/5xx/超时。
- key 门禁：缺 key 时 backend 被跳过，通道进入 `needs_key` / `degraded`。
- 注册表顺序：`web search` 的 4 个 P2 顺序；阅读链顺序。
- `doctor` / `channels`：无 key 时 `web search` 不可用，提示 key 文件；
  有 key 时可用。

Live 校验（需要 key，手动）：

```bash
uv run deep-reach web search "desk organizer" --limit 5
uv run deep-reach web read https://example.com
```

分别只填一家 key 跑一次，确认请求形状和解析。

## 9. 暂不包含

- **月度额度账本**：现有 `quota.py` 只支持日额度。月度 credit 需要新的
  周期模型、跨进程计数和 402/429 对齐，单独排期。
- **Bright Data Web Scraper API**：结构化站点采集（Amazon/LinkedIn 等），
  不在本次范围。
- **Exa**：keys 模板里已预留，但本次按用户列出的四家实现。

## 10. 风险

- 各家 API 版本变化（Firecrawl 已到 v2），需要单元测试锁住请求形状；
  线上 4xx 变化时按 `UPSTREAM_BROKEN` 处理。
- Brave 的免费 credit 需要 attribution，且政策可能再变；文档写明。
- Bright Data 需要用户先创建 SERP / Unlocker zone，配置错误会得到
  `NEED_SETUP`。
- 本地不记月度额度，可能直到 provider 返回 402/429 才发现额度用完；
  作为后续版本补账本。

## 11. 完成标准

- `web search` 在只填任意一家 key 时可用；四家 key 都缺失时给出 key 路径提示。
- `web read` 在 Jina 失败后能继续尝试 Firecrawl/Tavily/Bright Data。
- 142 个现有测试保持通过，新增至少 20 个 P2 测试。
- `doctor` / `channels` / `tiers` 自动反映新的 P2 覆盖。
- 文档（README / PRODUCT / keys.example.yaml / CHANGELOG）同步更新。
