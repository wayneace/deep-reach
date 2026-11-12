---
name: deep-reach
description: |
  给 agent 的结构化上网入口：按 P0 官方接口 → P1 公开网页 → P2 第三方引擎 →
  P3 bsk UI 回退降级。重点覆盖产品调研、竞品调研：国内外社媒、Amazon 选品、
  众筹、专利/版权、GitHub/V2EX。
  当用户点名支持的平台、粘贴这些平台的链接、需要评论/字幕/榜单/商品/专利等结构化数据，
  或内置 web search/read 不可用、失败、拿不到正文时使用。
  普通公开网页优先用内置工具；Deep-Reach 补齐结构化数据和登录/反爬场景。
  写操作仅在用户明确要求时执行；付费 API、Amazon 关键词量/流量数据不在范围内。
metadata:
  homepage: https://github.com/wayneace/deep-reach
  version: "0.14.0"
---

# Deep-Reach

Deep-Reach 是 AI agent 的**结构化上网入口**。它不分析；返回统一 JSON，
读操作和写操作都由动作声明。

## 选择路由

| 情况 | 用什么 |
|---|---|
| 普通公开网页，内置 search/read 能拿到正文 | 内置工具 |
| 用户点名支持的平台，或粘贴平台链接 | `deep-reach <channel> <action>` |
| 需要评论、字幕、榜单、商品、专利等结构化数据 | `deep-reach` 对应动作 |
| 内置 search/read 不可用、失败、拿不到正文 | `deep-reach web read` 或对应 channel |
| 登录墙、验证码后的页面、写操作 | `deep-reach bsk`（写前确认） |
| 不确定渠道/参数 | `deep-reach channels --json` |
| 环境、缺 key、OpenCLI/profile 问题 | `deep-reach doctor --json` |

配套规则：

- 平台名或链接只说明来源，不等于授权安装、登录或写操作。
- 先返回已经拿到的公开结果；用户不登录时不要空手而归。
- 不要假设渠道存在；以 `deep-reach channels --json` 的当前环境结果为准。
- 不要一次输出全部 capabilities；需要时查单个渠道。
- 失败时按错误码处理，不要换账号、换后端或循环重试。

## 调用前

- 用一句话说明要用的 channel/action；P3 或写操作必须说明并确认。
- 只有用户明确说“发/评论/点赞/关注/私信”等，才算写操作授权；不要从“帮我看看”推断写意图。
- 不要因为用户提到平台名或粘贴链接就自动安装、登录或写。
- 首次使用或缺配置时，先读 `deep-reach doctor --json`；`setup` 只创建 keys 文件，不启动 Chrome。

## 命令

### 自动路径（P0/P1/P2）

```bash
deep-reach bilibili search "收纳" --limit 5
deep-reach youtube search "desk organizer" --limit 5
deep-reach weibo hot --limit 10
deep-reach xueqiu quote SH600519
deep-reach amazon product B0C9ZHWC9K
deep-reach github search "desk organizer" --limit 5
deep-reach v2ex hot --limit 10
deep-reach web read https://example.com/article
```

### P3 回退

这些 channel 命令在没有自动后端时返回 `NEED_UI`；直接走 `deep-reach bsk ...` 更快：

```bash
deep-reach bsk status
deep-reach bsk session start --json
deep-reach bsk navigate https://example.com --session <id>
deep-reach bsk observe --session <id>
deep-reach bsk click @e1 --session <id>
deep-reach bsk session stop <id>
```

对应渠道：`x`、`reddit`、`xiaohongshu`、`zhihu`、`douyin`。

### 需要 key

```bash
deep-reach web search "desk organizer" --limit 10
deep-reach ebay search "desk organizer" --limit 10
deep-reach etsy search "desk organizer" --limit 10
deep-reach uspto search "desk organizer" --limit 10
deep-reach epo search "desk organizer" --limit 10
```

缺 key 时用 `deep-reach doctor --json` 看 `keys_file` 和缺失项；不要把 key 打印出来。

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
| `NEED_LOGIN` | 需要登录 | P1：在专用 Chrome profile 登录；P3：在当前浏览器登录。不要索要密码或 Cookie |
| `NEED_SETUP` | 后端/扩展/工具未安装 | 读 `deep-reach doctor --json`；OpenCLI 缺失时按客户端安装，再 `profile launch`/`profile status`/`profile set` |
| `KEY_MISSING` | key 缺失 | 读 `doctor --json` 的 `keys_file`；让用户填 `~/.deep-reach/keys.yaml`，不要回显 key |
| `UPSTREAM_BROKEN` | 平台临时不可用 | 自动尝试下一层；全失败时按平台名告诉用户，不要循环重试 |
| `QUOTA_EXHAUSTED` | 免费额度用完 | 自动降层；全耗尽时告诉用户，不要换账号 |
| `RATE_LIMITED` | 平台限流 | 停止本次动作并冷却渠道 1 小时；不要换后端、换账号或循环重试 |
| `PLATFORM_BLOCKED` | 验证码/风控 | 停止自动化，让用户手动完成 |
| `WRITE_BLOCKED` | 该后端不支持这个写操作 | 换一个支持写的动作，或走 P3 bsk；写操作需确认用户意图 |
| `NEED_UI` | 自动后端无法完成 | 用 `deep-reach bsk ...` 回退；不要直接 fetch 站点内部接口 |
| `POLICY_BLOCKED` | bsk 守卫拦截 | 改用 observe/click/extract/network 读取，不要 fetch/XHR 或 replay |
| `NOT_FOUND` | 内容不存在 | 检查 URL/ID |
| `BAD_INPUT` | 参数错误 | 运行 `deep-reach channels --json` 或 `deep-reach <channel> <action> --help` |
| `TIMEOUT` | 超时 | 稍后重试，不要循环 |
| `SOURCE_DISABLED` | 没有可用后端 | 运行 `deep-reach doctor --json` 看下一步 |
| `CONFIG_ERROR` | 配置文件错误 | 让用户修 `keys.yaml`；不要回显文件内容或 key |
| `BUSY` | 共享浏览器槽位满了 | 停止；等一分钟再试，不要换账号或开新浏览器 |

`NEED_SETUP` 的完整步骤：

1. 运行 `deep-reach doctor --json`，读 `opencli.missing`、`profile.configured`、`keys_file`。
2. OpenCLI 缺失：Cherry Studio 用 `cli_install`（recipe `npm:@jackwener/opencli`）；
   其他客户端用 `npm install -g @jackwener/opencli@2.0.3`。
3. 运行 `deep-reach profile launch`，在专用窗口安装/启用扩展；
   再运行 `deep-reach profile status`，然后 `deep-reach profile set <contextId>`。
4. 绑定后 P1 动作会自动启动专用 Chrome profile、等待扩展连接，并在动作结束后关闭它。

## 规则

- **写操作**：可以写，但必须先确认用户意图；P3 bsk 可写；未经确认不要发帖、评论、点赞、私信、关注。
- **不碰凭据**：不要索要密码、Cookie、token；让用户自己在浏览器登录或填 key。
- **不共享登录态**：P1 只使用显式绑定的专用 Chrome profile；P3 使用当前浏览器；不要把主浏览器登录态复制给 P1。
- **不编造**：结果来自 `items`；搜索摘要不能当全文。
- **不承诺完整评论树**：`comments` 动作返回的是已加载/可见范围。
- **不把 `raw` 当公开输出**：默认只使用统一字段；需要调试时再看 `raw`。
- **不手动挑后端**：不要指定 tier 或 backend，让 dispatch 按 P0 → P1 → P2 处理；失败时按 `NEED_UI` 走 `deep-reach bsk`。
- **URL 边界**：`web read` 默认拒绝 localhost、回环和内网地址；不要试图绕过，确有需要时由用户显式设置 `DEEP_REACH_ALLOW_PRIVATE_URLS=1`。
- **降级不是失败**：`ok=true` 且 `degraded=true` 表示已自动换层，结果仍可用。
- **平台边界**：`PLATFORM_BLOCKED` 时停止，不要换后端、换账号继续撞。
- **配额边界**：P0 配额用完会自动走 P1/P2；不要为此切换账号。
- **尊重限速**：同渠道搜索自动间隔 10 秒；`RATE_LIMITED` 后渠道冷却 1 小时。不要用并发绕过。
- **本地频率上限**：同一渠道每分钟最多 40 次后端请求；超出会等待，预算不够则返回 `BUSY`。并行任务共享这 40 次，不是每个任务各 40 次。
- **暂停不是坏掉**：`skipped=true` 表示后端在冷却窗口内被跳过，换时间重试即可。

## 能力契约

完整表见 [references/capabilities.md](references/capabilities.md)。
实际可用性以 `deep-reach channels --json` 为准；`fallback` 表示只有手动 bsk UI 路径。

## 安装 skill

如果客户端有技能市场（marketplace，例如 Cherry Studio），优先从市场安装：

```text
https://github.com/wayneace/deep-reach/blob/main/deep_reach/data/skill/SKILL.md
```

市场安装的目录名是 `skill`，显示名是 `deep-reach`，由市场负责更新。

没有市场时再用 CLI 安装：

```bash
deep-reach skill install --dest ~/.agents/skills --yes   # Codex
deep-reach skill install --dest ~/.claude/skills --yes   # Claude Code
deep-reach skill install --dest <skills-dir> --yes       # 其他客户端
```

CLI 安装目标是 `<skills-dir>/deep-reach/`。不要两种方式同时装。
