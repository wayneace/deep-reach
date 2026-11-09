# Changelog

## Unreleased

- `doctor` / `channels` 的 `status` 改为环境实测值（`ready` / `degraded` / `needs_setup` / `needs_login` / `needs_key` / `experimental`）；新增 `declared_status`、`runnable`、`available_actions`、`unavailable_actions`。多 key 渠道（eBay / EPO）要求所有 key 齐全；`xueqiu` 的 `hot` / `hot_stocks` 需要 cookie。
- `web read` / `http-read` 只允许 http/https，并默认拒绝 localhost、回环、私有/链路本地/保留地址；每次重定向都会重新校验；`DEEP_REACH_ALLOW_PRIVATE_URLS=1` 可显式放行私有地址。
- `keys.example.yaml` 移入 `deep_reach/data/` 并随 wheel 打包；`deep-reach setup` 打印包内模板路径。
- EPO OPS 的 `Range` 确认是 URL 参数，新增请求形状回归测试。
- 收尾：`channels` 新增 `effective_next_action`；畸形 URL 统一返回 `BAD_INPUT`；补充 hostname→私有 IP 回归测试。

## v0.8.0 — 2026-11-09

R5 Wave 2：专利检索。

- 新增 `uspto`：`search` / `read`，USPTO ODP 专利申请与授权检索，需要 `official.uspto.odp_api_key`。
- 新增 `epo`：`search` / `read`，EPO OPS 全球专利检索（US/CN/JP/EP），需要 consumer key/secret，免费 4GB/周。
- ODP 使用 `X-API-Key` 与 Lucene 风格查询；OPS 使用 OAuth2 client credentials + CQL。
- 按你的决定，Indiegogo 不做编排，从 roadmap 移除。
- 新增 5 个 USPTO/EPO 解析测试；85 个测试通过。

### 工程收尾

- 同站请求上限从 80 次/分钟调整为 **40 次/分钟**（仍是跨进程共享的滚动窗口）。
- `channels.yaml` 移入包内 `deep_reach/data/` 并作为 package data 打包；wheel 安装不再退化为 2 个渠道。
- 新增 `scripts/check_wheel.py` 与 CI 打包检查，防止 wheel 丢失渠道注册表。
- 同步 PRODUCT / README / SKILL / REFACTOR_PLAN 的限流数字、测试数字与路径。
- 修正 `channels.yaml` 的 planned 注释，以及 `product.py` 中不存在的 `patent` 动词。

## v0.7.0 — 2026-11-09

R5 Wave 1：电商与新品官方 API。

- 新增 `ebay`：`search` / `read`，eBay Browse API，免费 5,000 calls/day。
- 新增 `etsy`：`search` / `read`，Etsy Open API v3，免费 10,000 calls/day。
- `producthunt` 新增 P0 `producthunt-api`（GraphQL，需要 developer token）；无 token 时 OpenCLI 改用 `posts`，不再走失败的 `hot`。
- 新增每日免费额度账本 `runtime/quota.py`：YouTube / eBay / Etsy；80% 不警告，耗尽抛 `QUOTA_EXHAUSTED` 并降层。
- `doctor` / `state` 显示当日 quota 使用量。
- Indiegogo 官方 private API 被 Cloudflare 拦截（403），保持 planned，不伪装成可用。
- 新增 9 个 R5 解析与 quota 测试；80 个测试通过。

## v0.6.1 — 2026-11-09

- 同站请求上限从 60 次/分钟调整为 **80 次/分钟**。
- 明确：这是跨进程共享预算，两个并行任务合计 80 次/分钟，不是各 80 次。

## v0.6.0 — 2026-11-09

新增同站请求频率上限：

- 同一渠道所有后端请求最多 **60 次/分钟**，滑动窗口，跨进程文件锁。
- 超限时在动作预算内等待；预算不足返回 `BUSY`（本地保护，不触发渠道冷却或后端暂停）。
- `deep-reach state` 显示最近一分钟每站请求数。
- 新增 1 个测试。

## v0.5.1 — 2026-11-09

对齐 Agent-Reach 的保守终止策略：

- `RATE_LIMITED` / `BUSY` 进入 `FINAL_CODES`：本次动作不再尝试其他后端；渠道冷却仍为 1 小时。
- `NEED_LOGIN` / `QUOTA_EXHAUSTED` 保持可降层：P0/P1 是不同凭证与额度路径，不能因为 P0 缺 cookie 就放弃已登录的浏览器。
- 新增 2 个终止/降层边界测试。

## v0.5.0 — 2026-11-09

R3 可靠性与雪球编排，方案对齐 Agent-Reach：

- 新增跨进程文件锁槽位：同站 2 个、全局 4 个浏览器并发；排队时间不计入超时。
- 浏览器搜索按渠道 10 秒间隔限速；实测第二次 Amazon 搜索等待约 10 秒。
- `RATE_LIMITED` 触发渠道级 1 小时冷却；`TIMEOUT` / `UPSTREAM_BROKEN` / `NEED_SETUP` 触发后端 60–120 秒暂停。
- 失败后端在后续命令中标记 `skipped`，不再重复撞；成功一次即清除暂停。
- 每次动作一个 deadline；HTTP 后端用线程强制截止，浏览器后端用进程树超时。
- 状态存 `~/.deep-reach/state.json`，只含错误码和时间戳，不含查询、结果、cookie 或 key。
- 新增 `deep-reach state [--json] [--clear]`；`doctor` 显示冷却和暂停数量。
- 雪球按 Agent-Reach 编排：`tencent-quote` → `xueqiu-api` → OpenCLI；`tencent-search` → `xueqiu-api` → OpenCLI。
- 新增 `xueqiu hot_stocks`；`hot` / `hot_stocks` 支持可选 `xueqiu.cookie`。
- 腾讯行情支持美股 ticker（`AAPL`、`BRK.B`）。
- 新增 13 个可靠性 / 雪球测试。

## v0.4.0 — 2026-11-09

新增两个 P0 渠道：

- `github`：`search` / `read` / `issues`，公开 REST API，token 可选。
- `v2ex`：`hot` / `node` / `read` / `comments`，公开 v1 API，无需 token。
- `fetch_json` 支持返回数组，供 GitHub issues 和 V2EX 列表接口使用。
- 修复 OpenCLI 超时：Windows `.cmd` shim 会留下 node 子进程占住管道，现在超时用 `taskkill /T` 杀整棵进程树。
- 新增 9 个 GitHub / V2EX 解析测试；default smoke 扩展到 8 个渠道。

## v0.3.0 — 2026-11-08

P0 / P1 / P2 分层：

- `BackendSpec.tier`（`p0` / `p1` / `p2`），默认 `p1`；注册表强制按层稳定排序。
- backend 级 `key`，同一渠道不同层可用不同 key。
- 配额耗尽、限流、未登录自动降层；错误按可行动性排序。
- 新增 P0 后端：`bilibili-public`、`tencent-quote`、`http-read`、`youtube-api`。
- 新增 `deep-reach tiers`；`doctor` 显示每渠道 tier 覆盖和 OpenCLI 推荐版本。
- 移除未注册的 `bili-cli`、`xueqiu-public`、`firecrawl`、`brightdata` 声明，列出的后端必须能用。
- 新增 `truststore`，修复 uv Python 在 Windows 上的 CA 证书问题。
- 新增 8 个分层测试。

## v0.2.0 — 2026-11-08

产品化重构：

- 精选 `config/channels.yaml`：default / optional / experimental / planned 分级。
- 主 CLI 改为 `deep-reach <channel> <action>`，不再以 `run --param` 为主路径。
- 新增 `doctor`：状态 + 下一步提示。
- 新增 `channels` / `capabilities` / `roadmap` / `about` / `setup` / `profile` / `update` / `uninstall --dry-run`。
- 新增 Jina Reader 后端，`web read` 可用。
- 新增 `profile status/set/launch`，支持专用 Chrome profile。
- 新增 `skill/SKILL.md` 和 `skill/references/capabilities.md`。
- 新增产品契约测试、doctor 测试、profile 测试、live smoke 脚本。
- 未实现渠道移入 `planned`，不再出现在 `channels` 主列表。
