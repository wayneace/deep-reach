# Deep-Reach 产品定义

> 版本：0.14.2
> 日期：2026-11-11

## 一句话

给 AI agent 一个**免费优先、按层降级、可读可写**的通用上网入口：先走官方免费接口，再走公开网页 / OpenCLI 公开命令，再用第三方采集服务，登录态和写操作走 bsk UI 回退。

产品调研（社媒、Amazon、众筹、专利/版权）是第一个被完整验证的垂直；其他网站默认只依赖公开网页、P2 采集或 bsk 回退，不单独写适配器。

## 用户与任务

用户：个人亚马逊卖家 / 小团队产品开发者，用 AI agent 做选品和市场调研。

通用任务：

1. 读取一个公开网页 / JSON 接口。
2. 在社媒平台搜索、读帖、读评论。
3. 在电商、众筹、专利网站检索公开信息。

四类产品调研任务：

1. **社媒口碑**：用户在真实场景里怎么用、夸什么、骂什么、想要什么。
2. **Amazon 选品**：搜索、商品、榜单、评论摘要，验证需求和竞争。
3. **众筹验证**：Indiegogo / Kickstarter 上的新品、价格带、卖点。
4. **专利/版权**：USPTO、EPO、Google Patents、版权登记，做侵权和差异化判断。

## 核心：P0 / P1 / P2 / P3 分层

每个 Action 的后端按层排序，注册表强制排序，YAML 写反了也不会改变顺序。

| 层 | 含义 | 凭证 | 典型后端 |
|---|---|---|---|
| **P0** | 官方接口：官方 API 免费层、公开 JSON、官方 CLI | none / key / oauth | B站公开 API、腾讯行情、YouTube Data API、GitHub / eBay / Etsy / USPTO / EPO |
| **P1** | 公开网页：直连 HTTP、Jina Reader、OpenCLI 公开命令 | none / 可选 key | 直连 HTTP、Jina Reader、微博热榜、B站公开搜索、Amazon 公开页 |
| **P2** | 第三方搜索/采集引擎 | key / quota | Tavily、Brave、Firecrawl、Bright Data |
| **P3** | bsk UI 回退：agent 驱动，不写站点 recipe | public / login | `deep-reach bsk`（守卫版） |

降级规则：

- 缺 key 只跳过需要 key 的后端，不影响同层其他后端。
- 登录动作只尝试声明 `supports_login` 的后端；没有登录后端时直接返回 `NEED_UI`。
- P0 配额耗尽（`QUOTA_EXHAUSTED`）、未登录（`NEED_LOGIN`）都**继续尝试下一层**，不直接失败。
- 风控/验证码（`PLATFORM_BLOCKED`）、参数错误、404 是终止错误，不继续撞。
- 全部失败且动作声明 `ui_fallback` 时返回 `NEED_UI`，由 agent 用 `deep-reach bsk` 接手。
- P3 守卫只拦截直接 fetch/XHR 站点内部接口和 `debug replay`；bsk 其他能力（含写操作）可用。

## 产品承诺

1. **一个动词表**：`search`、`read`、`comments`、`product`、`bestsellers`、`quote`。  
   Agent 不需要知道底层是官方 API、OpenCLI 还是阅读器。
2. **可读可写**：写操作由动作声明；P3 bsk 可写，但写操作有副作用，必须确认用户意图。
3. **按层降级**：P0 → P1 → P2 → P3，先便宜后昂贵；只使用免费额度/免费 credit，不自动充值。
4. **没有 key 也能跑**：缺 key / 缺登录只降级对应渠道，不阻塞其他渠道。
5. **说人话**：错误码之外，必须告诉用户下一步做什么。
6. **列出的渠道必须能用**：每个可见渠道至少有一条已验证路径；未实现的不进 CLI。
7. **本地优先**：配置、状态、浏览器 profile 都在本机；不上传数据。
8. **证据可追溯**：每条结果带 `source`、`url`、`backend`、`tier`、`fetched_at`。
9. **不互相踩**：同站并发槽、搜索间隔、限流冷却、失败后端暂停；多个 agent 命令同时跑也不会一起撞平台。
10. **密钥不泄露**：keys 文件 `0600`、目录 `0700`；子进程不继承 Deep-Reach key；错误和输出脱敏；跨域重定向不带凭据头。
11. **不碰主浏览器登录态**：P1 OpenCLI 只使用显式绑定的专用 Chrome profile；未绑定就不运行，绝不自动选择第一个已连接 profile。

## 非目标

- 不做未经用户确认的写操作，不做社媒管理。
- 不自建爬虫集群；P2 只调用第三方公开服务。
- 不接付费 API（X API、Keepa、WIPO 付费、Lens 等）。
- 不做多用户 / 云服务 / 分布式。
- 不承诺完整评论树、不承诺理解图片/视频。
- 不做结果 cache；每次动作走真实上游。
- 不单独接入 1688 CLI / SellerSprite skill；需要时直接用 OpenCLI 公开能力。

## 渠道分级

| 级别 | 含义 | 用户预期 |
|---|---|---|
| `default` | 无 key、无登录也能用，或只需要公开网页 | 装好就能跑 |
| `optional` | 需要登录或免费 key，但已实现 | 按提示登录/填 key 后可用 |
| `experimental` | 可能受反爬/页面改版影响 | 明确标注不稳定 |

`level` 描述可用性；`tier` 描述后端路径。两者正交：一个 `default` 渠道可以同时有 P0、P1 和 P3 回退。

## 与 Agent-Reach 的关系

Agent-Reach 是同类产品，Deep-Reach 参考它的 Channel / Action / Backend、权限边界、doctor、能力契约和精选渠道。

差异：

| 维度 | Agent-Reach | Deep-Reach |
|---|---|---|
| 定位 | 通用 agent 上网层 | 通用 agent 上网层 + 产品调研垂直验证 |
| OpenCLI | 固定在 1.8.7 | 跟随最新版，`doctor` 对比推荐版本 |
| 后端顺序 | 有序 fallback | 显式 P0/P1/P2/P3，注册表强制排序 |
| 配额/限流 | 后端 health / cooldown | 配额或限流自动降层 |
| 官方 API | 刻意不接 | P0 免费层优先 |
| 产品调研 | 不覆盖 | Amazon / 众筹 / 专利是验证垂直 |

## v0.11 范围

### 已实现

- `default`：bilibili、youtube、weibo、xueqiu、amazon、web、github、v2ex。
- `optional`：x、reddit、xiaohongshu、zhihu、douyin。
- `experimental`：producthunt、kickstarter、cnipa、copyright。
- P0 后端：`bilibili-public`、`tencent-quote`、`tencent-search`、`youtube-api`（需 key）、`github-api`（token 可选）、`v2ex-public`、`ebay-api`、`etsy-api`、`producthunt-api`、`uspto-odp`、`epo-ops`。
- P1 后端：`http-read`、`jina`、OpenCLI 公开命令。
- P2 后端：`tavily-search` / `tavily-extract`、`brave-search`、`firecrawl-search` / `firecrawl-scrape`、`brightdata-serp` / `brightdata-unlocker`。
- P3 后端：`deep-reach bsk`（bsk UI 回退，agent 驱动；守卫拦截直接内部 API 调用和 `debug replay`）。
- 雪球编排：`tencent-quote` / `tencent-search` → `xueqiu-api`；`hot` / `hot_stocks` 失败时走 bsk 回退。
- R3 可靠性：跨进程并发槽、10 秒搜索间隔、1 小时渠道冷却、60–120 秒后端暂停、动作级 deadline。
- 环境感知状态：`doctor` / `channels` 的 `status` 反映 key、OpenCLI 连接、bsk 可用性和可用动作；`declared_status` 保留注册表原值。
- URL 边界：`web read` 默认只访问 http/https 公网地址；每次重定向重新校验；`DEEP_REACH_ALLOW_PRIVATE_URLS=1` 可显式放行私有地址。

### 下一步

- 有 key 后：live 校验 eBay / Etsy / Product Hunt / USPTO / EPO。
- 有 P2 key 后：live 校验 `web search` 和 `web read` 的 Tavily / Brave / Firecrawl / Bright Data。
- Indiegogo 不做（Cloudflare 拦截，无公开 API）。
- 其他站点：不写专属适配器，只走公开网页 / P2 / bsk 回退。

## 成功标准

- 8 个 default 渠道 smoke 通过（B站、YouTube、微博 hot、雪球 quote、Amazon、web、GitHub、V2EX）。
- 每个 P0 后端可单独调用，且失败时能自动降层。
- 第二次同渠道搜索自动等待 10 秒；限流后 1 小时内不再撞该渠道。
- 缺 key / 缺登录时 `doctor` 能说清楚下一步。
- P3 bsk 守卫拦截直接内部 API 调用；写操作放行但需确认用户意图。
- 每个可见渠道都有 capability note。
- 255 个单元测试 + 1 个 live smoke 脚本。
