# Deep-Reach

**给 AI agent 一个免费优先、按层降级、可读可写的通用上网入口。**

先走平台原生免费接口（P0），再走公开网页 / OpenCLI 公开命令（P1），再用第三方采集服务（P2）；登录态页面和写操作走 bsk UI 回退（P3）。产品调研（社媒、Amazon、众筹、专利/版权）是第一个完整验证的垂直；其他网站默认只依赖公开网页、P2 或 bsk 回退。

- 产品定义：[PRODUCT.md](PRODUCT.md)
- 重构计划：[REFACTOR_PLAN.md](REFACTOR_PLAN.md)

## 状态

- 版本 **0.11.1**；250 个单元测试。
- 21 个可见渠道，10 个有 P0 覆盖；8 个 default 渠道 live smoke 通过（P0/P1，未含 P3）。
- `channels` / `doctor` 的 `status` 是**当前环境实测值**（`ready` / `degraded` / `fallback` / `needs_setup` / `needs_login` / `needs_key` / `experimental`）；`declared_status` 保留注册表声明。
- 可读可写：写操作由动作声明决定；P3 bsk 可执行写操作，调用方需确认用户意图。

## 快速开始

需要 Python 3.10+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
cd deep-reach
uv sync
uv run deep-reach doctor
uv run deep-reach tiers
uv run deep-reach channels
uv run deep-reach bilibili search "收纳" --limit 5
```

> `uv run` 使用项目内 `.venv` 和 `uv.lock`，不安装到全局 PATH。  
> 一次性工具用 `uvx`；需要全局命令用 `uv tool install`。

## 分层：P0 → P1 → P2 → P3

| 层 | 含义 | 凭证 | 已接后端 |
|---|---|---|---|
| **P0** | 官方接口：官方 API 免费层、公开 JSON、官方 CLI | none / key / oauth | `bilibili-public`、`tencent-quote`、`tencent-search`、`youtube-api`、`github-api`、`v2ex-public`、`xueqiu-api`、`ebay-api`、`etsy-api`、`producthunt-api`、`uspto-odp`、`epo-ops` |
| **P1** | 公开网页：直连 HTTP、Jina Reader、OpenCLI 公开命令 | none / 可选 key | `http-read`、`jina`、`opencli-*`（仅公开） |
| **P2** | 第三方搜索/采集引擎 | key / quota | `tavily`、`brave`、`firecrawl`、`brightdata` |
| **P3** | bsk UI 回退：agent 驱动，不写站点 recipe | public / login | `deep-reach bsk`（守卫版） |

规则：

- P0 → P1 → P2 自动排序；P3 是回退引导，不参与自动 backend 链。
- 缺 key 只跳过需要 key 的后端；登录动作只尝试 `supports_login` 的后端。
- P0 配额耗尽、未登录会继续降层；`RATE_LIMITED` / `BUSY` / 风控 / 参数错误 / 404 是终止错误。
- 自动后端全部失败或没有登录后端时，返回 `NEED_UI`，由 agent 用 `deep-reach bsk` 接手。
- P3 守卫只拦直接 fetch/XHR 站点内部接口和 `debug replay`；bsk 其他能力（含写操作）可用。

```bash
uv run deep-reach tiers          # 分层定义 + 每个渠道的覆盖
uv run deep-reach tiers --json
```

## 可靠性

多个 agent 命令同时跑时，不会一起撞平台（方案对齐 Agent-Reach）：

- **并发槽**：同一站点最多 2 个浏览器查询，全局最多 4 个；OS 文件锁，跨进程生效。
- **搜索间隔**：同一渠道的浏览器搜索至少间隔 10 秒（每个任务检查一次，不是每个请求）。
- **同站请求上限**：同一渠道所有后端请求最多 40 次/分钟（滑动窗口，跨进程共享预算）。
- **渠道冷却**：确认限流后，整个渠道冷却 1 小时。
- **限流即止**：`RATE_LIMITED` / `BUSY` 立即终止本次动作，不换后端；`NEED_LOGIN` / `QUOTA_EXHAUSTED` 仍可降层（不同凭证/额度路径）。
- **后端暂停**：`TIMEOUT` 60 秒、`UPSTREAM_BROKEN` 120 秒、`NEED_SETUP` 60 秒；期间跳过并记 `skipped`。
- **动作截止**：每次动作一个总预算；排队时间不占用预算。
- **免费额度**：YouTube / eBay / Etsy 的每日额度记在本地账本，耗尽自动降层。
- **状态可查**：`deep-reach state` 看冷却、暂停和当日 quota，`--clear` 清空。

状态在 `~/.deep-reach/state.json`，只存错误码和时间戳，不存查询、结果、cookie 或 key。

## 产品承诺

- **一个动词表**：`search` / `read` / `comments` / `product` / `bestsellers` / `quote`。
- **可读可写**：写操作由动作声明决定；P3 bsk 可写，但写操作有副作用，必须确认用户意图。
- **按层降级**：原生免费接口 → OpenCLI → 第三方阅读器；不调用付费 API。
- **没有 key 也能跑**：缺 key / 缺登录只降级对应渠道。
- **说人话**：错误码之外，`doctor` 告诉你下一步。
- **列出的渠道必须能用**：没实现的只出现在 `roadmap`。
- **本地优先**：配置、状态、浏览器 profile 都在本机。

## 渠道分级

```bash
uv run deep-reach channels      # 默认显示已实现渠道；每行 status 是当前环境实测值
uv run deep-reach roadmap       # 尚未实现的渠道
uv run deep-reach capabilities  # 每个渠道能做什么、不能做什么
```

| 级别 | 含义 |
|---|---|
| `default` | 装好就能跑：B站、YouTube、微博 hot、雪球、Amazon、web、GitHub、V2EX |
| `optional` | 需要登录或免费 key：X、Reddit、小红书、知乎、抖音、eBay、Etsy、USPTO、EPO |
| `experimental` | 可能不稳定：Product Hunt、Kickstarter、CNIPA、版权 |
| `planned` | 只在 roadmap：KIPRIS、EUIPO、1688、SellerSprite 等 |

## 常用命令

```bash
# 社媒
uv run deep-reach bilibili search "收纳" --limit 5
uv run deep-reach bilibili read BV1xZ4y1j7qV
uv run deep-reach bilibili comments BV1xZ4y1j7qV --limit 10
uv run deep-reach youtube search "desk organizer" --limit 5
uv run deep-reach weibo hot --limit 10
uv run deep-reach xueqiu quote SH600519
uv run deep-reach xueqiu quote AAPL
uv run deep-reach xueqiu search 茅台 --limit 5
uv run deep-reach xueqiu hot --limit 10
uv run deep-reach xueqiu hot_stocks --limit 10
uv run deep-reach x search "AI" --limit 5

# 开发者社区
uv run deep-reach github search "desk organizer" --limit 5
uv run deep-reach github issues microsoft/vscode --limit 10
uv run deep-reach v2ex hot --limit 10
uv run deep-reach v2ex node create --limit 10

# 电商 / 新品
uv run deep-reach amazon search "desk organizer" --limit 10
uv run deep-reach amazon product B0C9ZHWC9K
uv run deep-reach ebay search "desk organizer" --limit 10
uv run deep-reach ebay read 123456789012
uv run deep-reach etsy search "desk organizer" --limit 10
uv run deep-reach producthunt hot --limit 10

# 专利
uv run deep-reach uspto search "desk organizer" --limit 10
uv run deep-reach epo search "desk organizer" --limit 10
uv run deep-reach epo read EP1234567

# 网页
uv run deep-reach web search "desk organizer" --limit 10
uv run deep-reach web read https://example.com/article

# 诊断
uv run deep-reach doctor
uv run deep-reach doctor --json
uv run deep-reach tiers
uv run deep-reach state
uv run deep-reach state --clear
uv run deep-reach profile status
uv run deep-reach about

# live smoke（default 渠道）
uv run python scripts/smoke.py
```

默认输出一行 JSON；加 `--text` 看人类可读摘要，加 `--pretty` 格式化 JSON。成功时 `tier` 告诉你走的是哪一层。

## Key 文件

真实文件：

```text
~/.deep-reach/keys.yaml
```

模板（随 wheel 打包）：

```text
deep_reach/data/keys.example.yaml
```

运行 `deep-reach setup` 会打印当前安装里的模板绝对路径。所有 key 都是可选的；缺失时对应后端禁用或降级，不阻塞其他渠道。

GitHub token 可选：有 token 5,000 req/h，没有 60 req/h。  
YouTube Data API key 可选：有 key 走 P0，没有 key 自动走 OpenCLI。  
eBay 需要 `official.ebay.client_id` + `client_secret`；Etsy 需要 `official.etsy.api_key`；Product Hunt 需要 `official.producthunt.token`。  
USPTO 需要 `official.uspto.odp_api_key`；EPO OPS 需要 `official.epo.consumer_key` + `consumer_secret`。  
Jina Reader 可填免费 key：无 key 20 RPM，有 key 500 RPM。

P2 搜索/阅读（按顺序降级，缺 key 自动跳过）：

- `search.tavily.api_key`：1,000 credits/月，search basic 1 credit。
- `search.brave.api_key`：每月 $5 credit（约 1,000 次 search），需展示 Brave attribution。
- `search.firecrawl.api_key`：1,000 credits/月，scrape 1 credit/页，search 2 credits/10 条。
- `search.brightdata.api_token` + `serp_zone` / `unlocker_zone`：5,000 credits/月，SERP/Unlocker 共用。

`web search` 顺序：Tavily → Brave → Firecrawl → Bright Data。  
`web read` 顺序：`http-read` → Jina → Firecrawl → Tavily Extract → Bright Data Web Unlocker。

后端可以单独声明 key（`backend.key`），用于同一渠道不同层使用不同 key 的情况。

## 浏览器与 profile

OpenCLI 通过 Browser Bridge 扩展连接 Chrome。先安装 CLI：

```bash
npm install -g @jackwener/opencli   # 当前推荐 2.0.3
```

首次使用还需要手动安装一次扩展：

1. 打开 Chrome。
2. 安装扩展：<https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk>
3. 在 `chrome://extensions` 确认启用。
4. 验证：`uv run deep-reach doctor`

`doctor` 会对比已安装 OpenCLI 与推荐版本（当前 2.0.3），落后时给出升级命令。OpenCLI 不自动升级。

当前 `opencli_profile: auto` 会复用已连接的 Chrome profile。  
如果要做 Agent-Reach 那样的隔离：

```bash
uv run deep-reach profile launch     # 用 %LOCALAPPDATA%\deep-reach\chrome-profile 启动专用 Chrome
# 在这个窗口安装 OpenCLI 扩展
uv run deep-reach profile status     # 获取 contextId
uv run deep-reach profile set <contextId>
```

### bsk UI 回退（P3）

P3 用 `bsk`（Tencent BrowserSkill）驱动真实浏览器，不写站点 recipe。默认使用当前已连接的浏览器 profile；写操作允许，但调用方必须确认用户意图。需要指定浏览器实例时，直接把 bsk 的 `--browser <id|label>` 传给 `deep-reach bsk session start`。

```bash
uv run deep-reach bsk status
uv run deep-reach bsk session start --json
uv run deep-reach bsk navigate https://example.com --session <id>
uv run deep-reach bsk observe --session <id>
uv run deep-reach bsk click @e1 --session <id>
uv run deep-reach bsk session stop <id>
```

守卫只拦截：

- 直接 fetch/XHR 站点内部接口；
- `debug replay`；
- `evaluate` 里的网络调用。

其他 bsk 能力（observe / snapshot / click / fill / extract / network 读取 / debug 捕获 / 写操作）都可用。配置：

```yaml
browser:
  bsk_guard: true       # 只拦截直接内部 API 调用和 debug replay
risk:
  allow_high: true      # false 可整体禁用高风险动作
```

## 架构

```text
deep_reach/
  channels/     # Channel / Action / Backend + tier + curated registry
  backends/     # P0: public/github/v2ex/xueqiu/ebay/etsy/producthunt/uspto/epo
                # P1: http.py / jina.py / opencli.py（公开命令）
                # P2: tavily.py / brave.py / firecrawl.py / brightdata.py
                # P3: bsk_guard.py（bsk UI 回退守卫）
  runtime/      # dispatch / result / keys / doctor / profile / clock / state / health / limits / quota
  data/
    channels.yaml       # 精选渠道 + backend tier（随 wheel 打包）
    keys.example.yaml   # key 模板（随 wheel 打包）
  product.py    # 产品承诺与分层
  cli.py        # deep-reach <channel> <action>
skill/
  SKILL.md                  # agent 使用说明
  references/capabilities.md # 能力契约
```

## 开发

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run pytest -q --cov=deep_reach --cov-report=term-missing
uv run python scripts/smoke.py          # live smoke，需要网络
uv run python scripts/smoke.py --include-optional   # 额外跑需要登录的渠道
```

贡献说明见 [CONTRIBUTING.md](CONTRIBUTING.md)；安全问题见 [SECURITY.md](SECURITY.md)。

- 单元测试不访问网络。
- live smoke 会真实请求平台；浏览器渠道需要 OpenCLI 扩展。
- 发布前至少跑一次 `doctor` 和 default smoke。

## 许可

MIT，见 [LICENSE](LICENSE)。第三方说明见 [NOTICE](NOTICE)。

## 边界

- 不替用户登录；不索要密码；写操作必须确认用户意图。
- P3 bsk 守卫只拦截直接 fetch/XHR 站点内部接口和 `debug replay`，不限制 bsk 其他能力。
- 只使用各家的免费额度/免费 credit；不自动充值，不接需要付费的调用。
- 不自建爬虫集群；P2 只调用第三方公开服务。
- `web read` 默认只访问 http/https 公网地址；localhost、回环、私有网段、链路本地地址会被拒绝，重定向目标也会重新校验。确实需要访问内网时，显式设置 `DEEP_REACH_ALLOW_PRIVATE_URLS=1`。
- 不承诺完整评论树、不承诺理解图片/视频。
- 平台页面改版或风控会导致渠道暂时不可用；`doctor` 会标明。
