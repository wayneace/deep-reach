---
name: deep-reach
description: |
  通用 agent 上网入口，按 P0 官方接口 → P1 公开网页 → P2 第三方引擎 → P3 bsk UI 回退降级。
  重点覆盖产品调研：国内外社媒、Amazon 选品、众筹、专利/版权。用 `deep-reach`
  CLI 做搜索、抓取和写操作。当用户要做选品、竞品调研、社媒口碑/差评、Reddit/小红书/
  知乎/微博/B站/抖音搜索、Amazon 商品或榜单、Kickstarter/Indiegogo、USPTO/EPO/
  专利商标检索、GitHub 仓库/issue、V2EX 帖子，或读取公开网页时使用。写操作需用户明确确认；
  不要用于 Amazon 关键词量/流量数据（用 sellersprite-web）或需要付费 API 的场景。
---

# Deep-Reach

Deep-Reach 是 AI agent 的**上网入口**。它不分析；可读可写，写操作由动作声明，
P3 bsk 可执行写操作但需确认用户意图。它负责把分散在社媒、电商、众筹、专利网站和
公开网页上的内容稳定地取回来，并返回统一的 JSON。

后端按层降级：

| 层 | 路径 | 凭证 |
|---|---|---|
| P0 | 官方接口：官方 API 免费层 / 公开 JSON / 官方 CLI | none / key / oauth |
| P1 | 公开网页：直连 HTTP / Jina Reader / OpenCLI 公开命令 | none / 可选 key |
| P2 | 第三方搜索/采集引擎：Tavily / Brave / Firecrawl / Bright Data | key / quota |
| P3 | bsk UI 回退：`deep-reach bsk`（守卫版） | public / login |

## 先看能力

```bash
uv run deep-reach doctor
uv run deep-reach tiers
uv run deep-reach channels
uv run deep-reach capabilities <channel>
uv run deep-reach state
```

- `doctor` 告诉你哪些渠道可用、缺什么、下一步做什么。
- `tiers` 显示分层定义和每个渠道的层级覆盖。
- `channels` 默认显示已实现渠道，`status` 是当前环境实测值；`roadmap` 显示未实现的。
- `capabilities` 是能力契约：能拿什么、不能拿什么、走哪一层。
- `state` 显示限流冷却、暂停的后端和搜索间隔；`--clear` 清空记忆。

## 常用命令

```bash
# 社媒
uv run deep-reach bilibili search "收纳" --limit 5
uv run deep-reach youtube search "desk organizer" --limit 5
uv run deep-reach weibo hot --limit 10
uv run deep-reach xueqiu quote SH600519
uv run deep-reach xueqiu quote AAPL
uv run deep-reach xueqiu search 茅台 --limit 5
uv run deep-reach xueqiu hot --limit 10
uv run deep-reach xueqiu hot_stocks --limit 10
uv run deep-reach x search "AI" --limit 5
uv run deep-reach reddit search "desk" --limit 5
uv run deep-reach xiaohongshu search "露营灯" --limit 5
uv run deep-reach zhihu search "收纳" --limit 5
uv run deep-reach douyin search "收纳" --limit 5

# 开发者社区
uv run deep-reach github search "desk organizer" --limit 5
uv run deep-reach github read owner/repo
uv run deep-reach github issues owner/repo --limit 10
uv run deep-reach v2ex hot --limit 10
uv run deep-reach v2ex node create --limit 10
uv run deep-reach v2ex comments 123456 --limit 20

# 电商 / 新品
uv run deep-reach amazon search "desk organizer" --limit 10
uv run deep-reach amazon product B0C9ZHWC9K
uv run deep-reach amazon bestsellers --limit 20
uv run deep-reach ebay search "desk organizer" --limit 10
uv run deep-reach etsy search "desk organizer" --limit 10
uv run deep-reach producthunt hot --limit 10

# 专利
uv run deep-reach uspto search "desk organizer" --limit 10
uv run deep-reach epo search "desk organizer" --limit 10
uv run deep-reach epo read EP1234567

# 网页
uv run deep-reach web read https://example.com/article
```

默认输出一行 JSON。需要人类可读摘要时加 `--text`；需要格式化 JSON 时加 `--pretty`。

## 结果信封

```json
{
  "schema_version": 1,
  "ok": true,
  "channel": "bilibili",
  "action": "search",
  "backend": "bilibili-public",
  "tier": "p0",
  "items": [
    {"source": "...", "url": "...", "title": "...", "text": "...",
     "author": "...", "published_at": "...", "metrics": {}, "raw": {}}
  ],
  "meta": {"elapsed_ms": 1234, "attempts": [...], "degraded": false},
  "error": null
}
```

Agent 应该 branch `ok` 和 `error.code`，不要解析底层文本。`tier` 表示最终成功的层；
`meta.attempts` 记录每一层的 backend 和结果，`meta.degraded=true` 表示发生过降级。

## 错误处理

| code | 含义 | 行动 |
|---|---|---|
| `NEED_LOGIN` | 需要登录 | 告诉用户在浏览器登录对应站点；不要索要密码 |
| `NEED_SETUP` | 后端/扩展/工具未安装 | 让用户运行 `deep-reach doctor` |
| `KEY_MISSING` | key 缺失 | 告诉用户可选填 key，或使用 fallback |
| `RATE_LIMITED` | 平台限流 | 停止本次动作并冷却渠道 1 小时；不要换后端、换账号或循环重试 |
| `PLATFORM_BLOCKED` | 验证码/风控 | 停止自动化，让用户手动完成 |
| `WRITE_BLOCKED` | 该后端不支持这个写操作 | 换一个支持写的动作，或走 P3 bsk；写操作需确认用户意图 |
| `NEED_UI` | 自动后端无法完成 | 用 `deep-reach bsk ...` 回退；不要直接 fetch 站点内部接口 |
| `POLICY_BLOCKED` | bsk 守卫拦截 | 改用 observe/click/extract/network 读取，不要 fetch/XHR 或 replay |
| `NOT_FOUND` | 内容不存在 | 检查 URL/ID |
| `BAD_INPUT` | 参数错误 | 运行 `deep-reach <channel> <action> --help` |
| `TIMEOUT` | 超时 | 稍后重试，不要循环 |
| `SOURCE_DISABLED` | 没有可用后端 | 运行 `doctor` 看下一步 |
| `BUSY` | 共享浏览器槽位满了 | 停止；等一分钟再试，不要换账号或开新浏览器 |

## 规则

- **写操作**：可以写，但必须先确认用户意图；P3 bsk 可写；未经确认不要发帖、评论、点赞、私信、关注。
- **不碰凭据**：不要索要密码、Cookie、token；让用户自己在浏览器登录或填 key。
- **不编造**：结果来自 `items`；搜索摘要不能当全文。
- **不承诺完整评论树**：`comments` 动作返回的是已加载/可见范围。
- **不把 `raw` 当公开输出**：默认只使用统一字段；需要调试时再看 `raw`。
- **不手动挑后端**：不要指定 tier 或 backend，让 dispatch 按 P0 → P1 → P2 处理；失败时按 `NEED_UI` 走 `deep-reach bsk`。
- **URL 边界**：`web read` 默认拒绝 localhost、回环和内网地址；不要试图绕过，确有需要时由用户显式设置 `DEEP_REACH_ALLOW_PRIVATE_URLS=1`。
- **降级不是失败**：`ok=true` 且 `degraded=true` 表示已自动换层，结果仍可用。
- **平台边界**：`PLATFORM_BLOCKED` 时停止，不要换后端、换账号继续撞。
- **配额边界**：P0 配额用完会自动走 P1/P2；不要为此切换账号。
- **尊重限速**：同渠道搜索自动间隔 10 秒；`RATE_LIMITED` 后渠道冷却 1 小时。不要用并发绕过。
- **本地频率上限**：同一渠道每分钟最多 40 次后端请求；超出会等待，预算不够则返回 `BUSY`。这是本地保护，不是平台封禁。并行任务共享这 40 次，不是每个任务各 40 次。
- **暂停不是坏掉**：`skipped=true` 表示后端在冷却窗口内被跳过，换时间重试即可。

## 能力契约

完整表见 [references/capabilities.md](references/capabilities.md)。
