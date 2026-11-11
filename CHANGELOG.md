# Changelog

## Unreleased

- `deep-reach setup` 现在是首次部署入口：先展示将创建/保留的文件，确认后从包内模板创建 `~/.deep-reach/keys.yaml`（0600），已有文件绝不覆盖。
- 新增 `setup --dry-run` 和 `setup --yes`；非交互环境未加 `--yes` 时不做任何修改。
- `setup` 不直接安装 OpenCLI，而是提示 agent 使用当前客户端的管理器（Cherry Studio 用 `cli_install`，recipe `npm:@jackwener/opencli`；普通环境用 npm）；`doctor` / `update` / OpenCLI 缺失错误使用同一套提示。
- `setup` 汇总创建/保留的文件、仍为空的 key 及用途、扩展商店链接和 `profile launch/status/set` 步骤；不自动打开 Chrome。
- 测试数更新为 307。

## v0.12.0 — 2026-11-11

安全加固与专用浏览器 profile；包含一个破坏性变更。

- **破坏性变更**：移除 `opencli_profile: auto` 和自动选择第一个已连接 profile 的行为。P1 只运行显式绑定的专用 Chrome profile；`auto`、空值或非法 contextId 都视为未配置，P1 显示 `needs_setup`。
- 迁移：运行 `deep-reach profile launch`，在专用窗口安装/启用 OpenCLI 扩展，然后 `deep-reach profile status` + `deep-reach profile set <contextId>`。专用 profile 内需要重新登录 P1 网站；P0/P2 不受影响。
- keys.yaml 在 POSIX 上读取和写入都会收紧到 `0600`；`~/.deep-reach` 和专用 Chrome profile 目录收紧到 `0700`。
- YAML 语法错误只报文件名和行列，不再回显可能含 key 的出错行。
- 已知 key 值从 `ReachError`、JSON、`--text` 摘要和 `doctor` 文本中脱敏；脱敏在 JSON 序列化前执行。
- OpenCLI、bsk、Chrome、npm 和 taskkill 子进程使用过滤后的环境，不再继承 `DEEP_REACH_*` 或名字像凭据的变量。
- 跨域重定向剥离 `Authorization`、`Cookie`、`X-API-Key`、`X-Subscription-Token`、`X-Goog-Api-Key` 等凭据头和敏感查询参数；Jina、Xueqiu 使用同一套重定向校验。
- YouTube API key 从 URL 查询参数移到 `X-Goog-Api-Key` 请求头。
- `doctor --json` 增加 `keys_file_mode`、`keys_file_secure`、`keys_file_note` 和完整的 `profile` 块；`doctor` 文本显示专用 profile、后台窗口模式与权限告警。
- `profile launch` 补充 macOS / Linux 标准 Chrome 路径；`profile set` 校验 contextId 并原子写入，保留 dotfile symlink。
- 移除 `roadmap` 命令和 `planned` 概念；注册表只包含已实现渠道。
- `channels` / `capabilities` 移除 `--all` 参数。
- `doctor` 不再输出 planned 列表和计数。
- 未实现渠道不再占位；以后直接按 P0 → P1 → P2 → P3 添加。
- 自定义 `channels.yaml` 中的 `level: planned` 条目会返回 `CONFIG_ERROR`；请删除占位条目，或实现后再加入。
- 测试数更新为 291。

## v0.11.1 — 2026-11-11

P3 收尾：状态准确性与风险门修正。

- bsk-only 渠道（x / reddit / xiaohongshu / zhihu / douyin）在 bsk 已安装时显示 `fallback`，不再误报 `needs_setup`；bsk 未安装时仍为 `needs_setup`。
- `doctor` summary 增加 `fallback` 计数；`fallback` 渠道计入 `runnable`（手动 UI 路径）。
- 移除未生效的 `browser.bsk_profile`。bsk 始终使用当前已连接的浏览器 profile；需要指定实例时直接传 `--browser <id|label>` 给 `bsk session start`。
- `risk.allow_high` 与高风险警告改为使用 action + backend 的最高风险；`NEED_UI` 的 `meta.risk` 同步。
- `channels` / `doctor` / `capabilities` 的 action risk 显示 backend 声明的风险。
- 移除 1688 / SellerSprite / 贴吧 / 虎扑 planned 条目；不额外接入 1688 CLI 或 SellerSprite skill，OpenCLI 公开能力保持不变。
- 明确不做结果 cache；移除 R3 / 下一步中的相关计划。
- 测试数更新为 254。

## v0.11.0 — 2026-11-10

P3 bsk UI 回退与可写边界。

- 分层扩展为 P0 官方接口 → P1 公开网页 → P2 第三方引擎 → P3 bsk UI 回退。
- P1 只保留 OpenCLI 公开命令；登录态 OpenCLI backend 移除。
- 登录动作没有自动后端时返回 `NEED_UI`，附 `deep-reach bsk` 回退引导与策略。
- 新增 `deep-reach bsk`：透传 bsk 全能力（含写操作）；守卫只拦截直接 fetch/XHR 站点内部接口、`debug replay` 和 `evaluate` 网络调用。
- 移除只读产品边界；OpenCLI 写命令不再被全局拦截；`WRITE_BLOCKED` 仅表示后端不支持写。
- 新增 `POLICY_BLOCKED`；`NEED_UI` 进入终止码。
- `http-read` / Jina 归入 P1；`channels` / `doctor` 显示 risk、ui_fallback、bsk profile/warning。
- bsk 默认 main profile；`browser.bsk_profile` / `browser.bsk_guard` / `risk.allow_high` 可配置。
- 高风险渠道默认开启但警告；`risk.allow_high: false` 可整体禁用高风险动作。

## v0.10.1 — 2026-11-09

- 修正两个 key 提示测试在 Windows 上使用 POSIX 路径字面量导致 CI 失败；功能无变化。

## v0.10.0 — 2026-11-09

- 新增 P2 搜索/阅读后端：Tavily、Brave Search、Firecrawl、Bright Data。
- 新增 `web search`：Tavily → Brave → Firecrawl → Bright Data，缺 key 自动跳过。
- `web read` 和 4 个站点阅读动作的 P2 链扩展为 Jina → Firecrawl → Tavily Extract → Bright Data Web Unlocker。
- P2 的 401/403 映射为 `NEED_SETUP`，402/429 映射为 `QUOTA_EXHAUSTED`（可继续降层）；Jina 的 429 也从 `RATE_LIMITED` 改为 `QUOTA_EXHAUSTED`。
- `keys.example.yaml` 补充四家的 key、zone 与免费额度说明。
- OpenCLI 未安装时，`doctor` / `channels` / `setup` / `update` 和动作错误都会给出安装命令 `npm install -g @jackwener/opencli`；已安装但浏览器未连接时仍提示 Browser Bridge 扩展。
- 缺 key 时，`doctor` / `channels` / `setup` 和 `KEY_MISSING` 错误都会提示 keys 文件路径（默认 `~/.deep-reach/keys.yaml`）和包内模板 `deep_reach/data/keys.example.yaml`。
- `doctor --json` 增加 `opencli.missing`、`keys_template`、`keys_hint`；旧版本或无法解析版本时也会显示升级/排查提示。非缺失类 OpenCLI 错误的 `opencli.installed` 从 `error: ...` 改为 `unavailable`，详情放在 `action`。

## v0.9.3 — 2026-11-09

- 稳定 `test_pacing_waits_between_searches` 的计时断言；v0.9.2 的 CI 在慢 runner 上因此抖动。功能无变化。

## v0.9.2 — 2026-11-09

审查 minor 收尾。

- `keys.yaml` 权限收紧移到写入前；chmod 失败不再中断写入。
- POSIX 进程组清理容忍更多 `OSError`；Ctrl-C 会清理 OpenCLI 子进程。
- Product Hunt 限流匹配支持 `rate-limit` / `rate_limit`，并优先于 token 判断。
- deflate 同时支持 raw 与 zlib-wrapped。
- 补充 fetch→解压集成测试；CI 将 ruff/coverage 合并到现有 3.12 测试腿，避免重复跑。

## v0.9.1 — 2026-11-09

安全/运维加固与 CI 收尾。

- POSIX 下 `keys.yaml` 写入后收紧为 `0600`。
- POSIX 下 OpenCLI 超时改为杀掉整个进程组，避免 wrapper 留下 node 子进程。
- gzip/deflate 解压增加 10MB 输出上限，支持多 member gzip，拒绝压缩炸弹、截断流和损坏数据。
- Product Hunt 错误映射不再把 `moderated` 等普通错误误判为 `RATE_LIMITED`。
- CI 增加 ruff、覆盖率门槛（55%）和最小 `contents: read` 权限；补充 SECURITY.md / CONTRIBUTING.md 与项目 URLs。

## v0.9.0 — 2026-11-09

P0 加固与发布收尾。

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
