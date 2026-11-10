# P3 bsk UI Fallback 设计

> 2026-11-11 更新：v0.11.1 移除了未生效的 `browser.bsk_profile`。bsk 使用当前已连接的浏览器 profile；需要指定实例时直接传 `--browser <id|label>` 给 `bsk session start`。

- 日期：2026-11-10
- 状态：设计已确认，待写计划
- 目标版本：v0.11.0
- 关联：P0/P1/P2 分层、OpenCLI、bsk（Tencent BrowserSkill）

## 1. 背景

当前分层是 P0 官方接口 → P1 OpenCLI → P2 第三方阅读/采集。

问题：

- P1 的 OpenCLI 登录态后端会直接调用站点内部 API，已有小红书封号/账号违规、BOSS 强制下线的公开报告。
- 用户决定：P1 只保留 OpenCLI 公开命令；登录态页面改走 bsk UI 回退。
- 用户决定：P3 不写站点 recipe，只做回退引导；具体操作交给调用方 agent 用 bsk 随机应变。
- 用户决定：bsk 可以使用自己的全部能力，不做 UI-only 限制；唯一硬约束是**不直接 fetch 站点内部接口**。
- 用户决定：Deep-Reach 不再设只读产品边界，允许写操作。
- 用户决定：bsk 默认使用当前已连接的浏览器 profile；高风险渠道默认开启但警告。
- 用户决定：增加一个薄守卫（方案 B），只拦截直接内部 API 调用，不限制 bsk 其他能力。

## 2. 目标与非目标

### 目标

1. 把分层扩展为 P0/P1/P2/P3，其中 P3 = bsk UI fallback。
2. P1 只保留 OpenCLI 公开命令；登录态 OpenCLI backend 全部移除。
3. P3 不是自动 backend，不写 recipe，不返回 `items`；所有自动路径失败后返回 `NEED_UI` 引导。
4. bsk 全能力可用，包括写操作；守卫只拦截：
   - `debug replay`
   - `evaluate` 里的直接网络调用（fetch/XHR/sendBeacon/WebSocket/EventSource 等）
5. 新增 `deep-reach bsk ...` 薄守卫命令，透传 bsk 命令并在调用前做策略检查。
6. 移除全局只读产品边界；`WRITE_BLOCKED` 不再是默认行为。
7. 当前浏览器 profile、写操作、高风险渠道都给出明确警告，但不阻塞。
8. 更新 `tiers` / `channels` / `doctor` / envelope，使 P3、risk、ui_fallback 可见。

### 非目标

- 不为 bsk 写 `xiaohongshu` / `x` / `reddit` 等站点 recipe。
- 不自动从 bsk 提取结构化 `items`；P3 是 handoff，不是数据后端。
- 不实现所有渠道的写动作；本次只移除只读边界，写动作按需后续声明。
- 不默认切换到专用 profile；本次默认 main，保留未来 `dedicated` 配置。
- 不做 bsk MCP 集成；只用 CLI + 守卫。

## 3. 四层模型

| 层 | 名称 | 自动执行 | 内容 | access | risk |
|---|---|---|---|---|---|
| P0 | 官方接口 | 是 | 官方免费 API、公开 JSON、官方 CLI | none / key / oauth | low |
| P1 | 公开网页 | 是 | `http-read`、Jina、OpenCLI 公开命令 | none / optional key | low–medium |
| P2 | 第三方引擎 | 是 | Tavily、Brave、Firecrawl、Bright Data | key / quota | medium |
| P3 | bsk UI 回退 | 否，返回引导 | bsk 全能力，agent 驱动 | public / login | high（登录态/写操作） |

规则：

- 注册表仍按 P0 → P1 → P2 排序；P3 不参与自动 backend 链。
- `tier` 只表示偏好顺序，不表示结果质量。
- 登录需求由 `Action.requires` 和 `BackendSpec.supports_login` 决定；不满足的后端直接跳过。
- 所有自动后端失败，或动作需要登录但没有自动后端支持时，若 `Action.ui_fallback` 为真，返回 `NEED_UI`。

## 4. 数据模型

### BackendSpec

新增：

```python
supports_login: bool = False
risk: str = "low"  # low | medium | high
```

- P0 官方 backend 默认 `supports_login=False`（除未来 OAuth backend 外）。
- P1 `http-read` / Jina / OpenCLI 公开：`supports_login=False`。
- P2 Tavily/Brave/Firecrawl/Bright Data：`supports_login=False`。
- P3 不是 backend；不添加 `tier: p3` 的 backend。

### Action

新增：

```python
ui_fallback: bool = False
risk: str = ""  # 空表示从 backend 推导
```

- `requires: login` 且没有自动 backend 支持登录的动作，必须 `ui_fallback: true`。
- `requires: none/key` 的动作可以选择性开启 `ui_fallback`。

### TIERS

```python
TIERS = ("p0", "p1", "p2", "p3")
```

`p3` 仅用于展示和排序，不用于真实 backend。

## 5. 渠道映射

| 渠道/动作 | P0 | P1 | P2 | P3 |
|---|---|---|---|---|
| github / v2ex / xueqiu quote / ebay / etsy / uspto / epo | 官方 API | — | — | — |
| web read | — | http-read → Jina | Firecrawl / Tavily / Bright Data | 失败时引导 |
| web search | — | — | Tavily → Brave → Firecrawl → Bright Data | 失败时引导 |
| bilibili search/read/comments | bilibili-public | OpenCLI 公开 | — | 失败时引导 |
| bilibili subtitle | — | — | — | ui_fallback |
| weibo hot/read/comments | — | OpenCLI 公开 | — | 失败时引导 |
| weibo search | — | — | — | ui_fallback |
| x / reddit / xiaohongshu / zhihu / douyin | — | — | — | ui_fallback |
| xueqiu hot/hot_stocks/comments | — | — | — | ui_fallback |
| amazon 公开动作 | — | OpenCLI 公开 | — | 失败时引导 |
| producthunt | 官方 API | OpenCLI 公开 | — | 失败时引导 |
| kickstarter / cnipa / copyright read | — | http-read → Jina | Firecrawl / Tavily / Bright Data | 失败时引导 |

实现时按 `channels.yaml` 的 `requires` 字段逐动作判断，不按渠道一刀切。

## 6. NEED_UI 契约

当自动路径无法完成动作且 `ui_fallback` 为真：

```json
{
  "schema_version": 1,
  "ok": false,
  "channel": "xiaohongshu",
  "action": "search",
  "backend": null,
  "tier": "p3",
  "items": [],
  "meta": {
    "attempts": [],
    "fallback": "bsk-ui",
    "profile": "current",
    "risk": "high",
    "policy": {
      "bsk": "all capabilities, including writes",
      "forbid": [
        "direct fetch/XHR to site internal APIs",
        "debug replay",
        "network calls inside evaluate"
      ],
      "warn": [
        "debug rule_add",
        "destructive write actions"
      ]
    }
  },
  "error": {
    "code": "NEED_UI",
    "message": "没有自动后端能完成这个动作，请用 bsk UI 回退。",
    "hint": "使用 deep-reach bsk ...（守卫版）；bsk 全能力可用；不要直接 fetch 站点内部接口；写操作有副作用，请确认用户意图。"
  }
}
```

`NEED_UI` 是终止码，不再尝试其他后端。

`error.hint` 至少包含：

```bash
deep-reach bsk session start --json
deep-reach bsk navigate <url> --session <id>
deep-reach bsk observe --session <id>
deep-reach bsk click @eN --session <id>
deep-reach bsk session stop <id>
```

## 7. bsk 守卫

新增顶层命令：

```bash
deep-reach bsk <bsk-args...>
```

职责：

- 透传 bsk 的所有命令和参数，返回 bsk 的 stdout/stderr/exit code。
- 在调用前做策略检查。
- 在 stderr 打印当前浏览器 profile 和写操作警告。
- 不做站点 recipe，不解析 bsk 结果，不自动重试。

### 硬拦截

1. `debug replay` → `POLICY_BLOCKED`
2. `evaluate` 参数中出现以下任一网络原语 → `POLICY_BLOCKED`
   - `fetch(`
   - `XMLHttpRequest`
   - `sendBeacon`
   - `WebSocket`
   - `EventSource`
   - `axios(`
   - `$.ajax`

### 警告但不拦截

- `debug rule_add`：可能改变页面请求。
- `upload`：写操作。
- 任何 `click` / `fill` / `press`：可能是写操作，无法从命令本身判断意图。
- `delete` / `post` / `comment` / `purchase` 等语义明显的写操作：允许，但提示“写操作会真实改变站点状态”。

### 允许

- `status` / `doctor` / `session` / `browsers` / `tab` / `window`
- `navigate` / `observe` / `snapshot` / `screenshot`
- `click` / `hover` / `scroll-to` / `wheel` / `fill` / `press` / `select`
- `extract` / `get-html`
- `network` / `console`（只读）
- `debug`（捕获/读取；`replay` 除外）
- `request-help` / `cooperate`
- `record` / `video` / `emulate`
- 写操作（`post` / `comment` / `like` / `follow` / `delete` / `purchase` / `upload` 等）

### 守卫实现

- 文件：`deep_reach/backends/bsk_guard.py`
- CLI：`deep_reach/cli.py` 增加 `bsk` 子命令，使用 `argparse.REMAINDER` 透传。
- 解析 argv：
  - 第一个非选项 token 为 bsk 子命令。
  - `debug` 后跟 `replay` → block。
  - `evaluate` → 扫描其后的所有参数，命中网络原语 → block。
  - `debug` + `rule_add` → warn。
- 失败时返回 `POLICY_BLOCKED`，退出码 1，打印我们的错误 JSON（而不是 bsk 输出）。
- 成功时原样输出 bsk 的 stdout；stderr 追加警告。

## 8. 调度与错误策略

### 跳过规则

- `Action.requires == "login"` 且 `BackendSpec.supports_login == False` → 跳过。
- `Action.requires == "key"` 且 backend 缺 key → 跳过。
- `Action.requires == "none"` → 不因 access 跳过。

### 自动后端失败后

- 若 `Action.ui_fallback` 为真 → 返回 `NEED_UI`，`meta.attempts` 保留之前的尝试。
- 若为假 → 返回现有错误优先级最高的错误。

### 错误码

新增：

- `NEED_UI`：终止码，引导 bsk。
- `POLICY_BLOCKED`：终止码，守卫拦截。

调整：

- `WRITE_BLOCKED` 不再是全局只读行为；保留给明确不支持写操作的后端。
- `DEFAULT_HINTS[WRITE_BLOCKED]` 改为“该后端不支持这个写操作”，不再说 Deep-Reach 只读。
- `FINAL_CODES` 加入 `NEED_UI`、`POLICY_BLOCKED`。
- `ERROR_PRIORITY` 加入 `POLICY_BLOCKED`（高）和 `NEED_UI`（在 NEED_LOGIN 之后、RATE_LIMITED 之前或按实际语义排列）。

建议优先级：

```text
PLATFORM_BLOCKED > POLICY_BLOCKED > NEED_LOGIN > NEED_UI > RATE_LIMITED > ...
```

## 9. 产品边界变化

### 移除

- README 标题中的“只读”。
- “不发帖、不评论、不点赞、不私信”的产品承诺。
- `OpenCLIClient.run()` 的 `is_read` 拦截。
- `PRODUCT.md` 中“写命令 100% 被只读白名单拦截”的成功标准。

### 新增

- “可读可写；写操作由动作声明决定。”
- “P3 bsk 可执行写操作，写操作真实改变站点状态，调用方必须确认用户意图。”
- “不直接 fetch 站点内部接口；P3 守卫只拦这一类行为。”

### 保留

- `WRITE_BLOCKED` 错误码：用于明确不支持写操作的后端。
- 只读相关的安全测试可以保留，但改为“显式声明只读的后端”。

## 10. 配置

```yaml
browser:
  bsk_guard: true          # false 仅用于调试，不推荐
risk:
  allow_high: true         # 默认开启；每次调用仍警告
```

- bsk 使用当前已连接的浏览器 profile；需要指定实例时直接传 `--browser <id|label>` 给 `bsk session start`。
- `bsk_guard` 默认 `true`。
- `allow_high` 默认 `true`；若为 false，高风险动作返回 `PLATFORM_BLOCKED` 或 `BAD_INPUT` 提示（未来可选）。

## 11. 测试

### 单元测试

- `TIERS` 包含 p3，排序正确。
- `BackendSpec.supports_login` 过滤：login 动作跳过公开后端。
- `Action.ui_fallback` 在全部失败后返回 `NEED_UI`。
- `NEED_UI` envelope 形状、`meta.policy`、`error.hint`。
- `POLICY_BLOCKED` 进入 `FINAL_CODES`。
- bsk guard：
  - `debug replay` blocked。
  - `evaluate "fetch('/api')"` blocked。
  - `evaluate "document.title"` allowed。
  - `debug requests` allowed。
  - `network` allowed。
  - `click @e1` allowed。
  - `post` / `comment` allowed（写操作不再被全局拦截）。
- OpenCLI 写命令不再被 `is_read` 拦截（如果保留 read_commands，仅用于元数据）。

### 集成/契约测试

- `tiers` 输出 P0/P1/P2/P3，P3 标注为 fallback。
- `channels` 输出 `ui_fallback` 和 `risk`。
- `doctor` 显示 `profile: current` 和高风险 warning。
- 文档不再出现“只读”承诺。

### 手动 smoke

- `deep-reach bsk status`
- `deep-reach bsk session start --json`
- `deep-reach bsk navigate https://example.com --session <id>`
- `deep-reach bsk observe --session <id>`
- `deep-reach bsk session stop <id>`
- 验证守卫拦截 `debug replay` 和 `evaluate fetch`。

## 12. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 当前浏览器 profile 被误操作/封号 | 每次 P3 警告；文档建议小号；需要时用 `bsk --browser` 选择实例 |
| 写操作不可逆 | 允许写，但 stderr/meta 警告；未来可加 `--confirm-write` |
| bsk 守卫被绕过（字符串拼接、动态 eval） | 说明这是“薄守卫”，不是安全沙箱；高风险场景仍建议人工监督 |
| P3 非确定性 | 明确 P3 只做 handoff，不承诺 `items`；agent 自行验证结果 |
| 无 recipe 导致低效 | 接受；后续可按需加 recipe，但不属于本次范围 |
| OpenCLI 登录态移除导致覆盖下降 | 先保留公开 OpenCLI；登录态由 bsk 接手；后续补 recipe |
| bsk 版本/daemon 兼容 | 使用 `deep-reach bsk doctor`；文档要求 bsk 0.4.x |

## 13. 验收标准

- P0/P1/P2 现有测试全部通过。
- `pytest -q` 与 `ruff check .` 通过。
- `deep-reach tiers` 显示四层，P3 不伪装成自动 backend。
- `deep-reach channels` 显示 risk 和 ui_fallback。
- `deep-reach bsk` 守卫测试通过。
- README / PRODUCT / skill 文档不再宣称只读。
- `NEED_UI` 和 `POLICY_BLOCKED` 有默认 hint。
- 手动 bsk smoke 成功（example.com）。

## 14. 迁移与兼容

- 现有 P0/P1/P2 backend 不变；仅重新分类 `http-read`/Jina 到 P1。
- 删除 `requires: login` 的 OpenCLI backend；对应动作改为 `ui_fallback: true`。
- 现有 `WRITE_BLOCKED` 测试改为“显式只读后端”或删除。
- 旧 envelope 字段保持兼容；新增 `tier: p3`、`meta.fallback`、`meta.policy`。
- 版本号建议 v0.11.0。
