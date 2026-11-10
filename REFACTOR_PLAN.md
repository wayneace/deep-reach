# Deep-Reach v0.2 重构计划

> 目标：从“能跑的框架”变成“有产品承诺的工具”。  
> 参考：Agent-Reach 的 Channel / Action / Backend、只读安全、doctor、能力契约、精选渠道。

## 1. 当前问题

1. 24 个渠道里有大量未实现项，`channels` 看起来很强，实际不可用。
2. CLI 是 `run <channel> <action> --param`，像框架，不像产品。
3. `doctor` 只列 key 状态，不告诉用户下一步。
4. 没有能力契约，用户不知道每个渠道能做什么、不能做什么。
5. 没有专用浏览器 profile，和主 Chrome 共用登录态。
6. 没有 `setup` / `update` / `uninstall` 生命周期。
7. 没有 SKILL.md，agent 不知道怎么用。
8. 没有 live smoke，release 前不知道哪些渠道真的能用。

## 2. 目标架构

```text
deep_reach/
  product.py              # 产品名、承诺、版本
  cli.py                  # 动态 channel/action 子命令
  channels/
    base.py               # Channel / Action / BackendSpec / Param
    registry.py           # 读取 deep_reach/data/channels.yaml，分 level/status
  backends/
    public.py             # P0 公开 JSON / 官方免费 API
    http.py               # P0 直连 HTTP 阅读
    opencli.py            # P1 OpenCLI client + compat + read-only whitelist
    jina.py               # P2 第三方阅读器
    official/             # P0 产品调研垂直 API（R5）
  runtime/
    dispatch.py           # 有序回退 + FINAL_CODES
    result.py             # envelope + error codes
    keys.py               # 可选 key + 降级
    doctor.py             # 产品级状态与下一步
    profile.py            # 专用 Chrome profile
    setup.py              # 环境检查与安装提示
    state.py              # health / quota
  skill/
    SKILL.md              # agent 使用说明
    references/
      capabilities.md     # 能力契约
```

## 3. CLI 表面

```bash
deep-reach doctor
deep-reach tiers
deep-reach channels [--all]
deep-reach capabilities [channel]
deep-reach setup
deep-reach profile status|set|launch
deep-reach update
deep-reach uninstall --dry-run

deep-reach bilibili search "收纳" --limit 5
deep-reach youtube search "desk organizer" --limit 5
deep-reach weibo hot --limit 10
deep-reach xueqiu quote SH600519
deep-reach amazon product B0C9ZHWC9K
deep-reach web read https://example.com/article
deep-reach x search "AI" --limit 5
```

原则：

- 主路径是 `deep-reach <channel> <action>`，不是 `run --param`。
- 参数固定：`query` / `target` 是位置参数，`limit` 是 `--limit`。
- 默认一行 JSON；`--text` 给人看；`--pretty` 格式化。
- 未知 channel/action 给出有效选项，不抛栈。

## 4. 渠道分级

- `default`：装好就能跑（B站、YouTube、微博 hot、雪球、Amazon、web）。
- `optional`：需要登录或免费 key（X、Reddit、小红书、知乎、抖音）。
- `experimental`：可能不稳定（Product Hunt、Kickstarter、CNIPA、版权）。


## 5. Doctor

`deep-reach doctor` 必须回答：

1. 我是谁、版本多少。
2. keys 文件在哪、哪些 key 缺失。
3. OpenCLI 版本、浏览器是否连接、当前 profile contextId。
4. 每个渠道：level、status、actions、next action。
5. 如果缺登录/缺 key，明确告诉用户下一步，而不是只给错误码。

## 6. Profile

- `profile status`：显示已连接 contextId 和当前设置。
- `profile set <contextId>`：写入 `~/.deep-reach/keys.yaml`。
- `profile launch`：用 `%LOCALAPPDATA%\deep-reach\chrome-profile` 启动专用 Chrome。
- 专用 profile 需要手动安装一次 OpenCLI 扩展。
- 默认 `auto`，但文档明确：auto 会复用当前连接的 Chrome profile，不是隔离。

## 7. 能力契约

`skill/references/capabilities.md` 和 `deep-reach capabilities` 必须写清楚：

- 每个渠道的 level、actions、requires。
- 能拿到什么，不能拿到什么。
- 不承诺完整评论树、不承诺图片/视频理解。
- 哪些动作需要登录、哪些需要 key。

## 8. 测试与发布

- 单元测试：registry、CLI parser、doctor、profile、opencli compat、dispatch。
- 产品契约测试：每个 visible channel 至少一个 action；每个 visible channel 有 capability。
- Live smoke：`scripts/smoke.py`，覆盖 default 渠道；optional 渠道按登录状态跳过并标注。
- Release：版本号、CHANGELOG、`deep-reach doctor` 自检。

## 9. 分阶段

### R0 — 产品文档与精选 registry

- [x] `PRODUCT.md`
- [x] `REFACTOR_PLAN.md`
- [x] `deep_reach/data/channels.yaml` 分级
- [x] `channels/registry.py`

### R1 — CLI 产品化

- [x] 动态 `<channel> <action>` 子命令
- [x] `channels` / `capabilities`
- [x] 一行 JSON + `--text`

### R2 — Doctor / Profile / Setup

- [x] `doctor` 下一步提示
- [x] `profile status/set/launch`
- [x] `setup` / `update` / `uninstall --dry-run`

### R3 — 可靠性

- [x] 并发槽（同站 2 / 全局 4，跨进程文件锁）
- [x] 搜索间隔（同渠道 10s）
- [x] 同站请求上限（40 次/分钟滑动窗口，跨进程共享）
- [x] cooldown（RATE_LIMITED 1h）
- [x] health（后端暂停 60–120s，成功即恢复）
- [x] 动作级 deadline（HTTP 线程截止，浏览器进程树超时）
- [x] quota 计数（YouTube / eBay / Etsy 每日额度，v0.7）
- [x] live smoke（default 8 渠道通过）

### R4 — Skill 与能力契约

- [x] `SKILL.md`
- [x] `capabilities.md`
- [x] 产品契约测试

### R5 — 产品调研垂直的 P0 官方 API

- [x] YouTube Data API（有 key 时 P0）
- [x] GitHub / V2EX 公开 API（非垂直，按用户要求接入）
- [x] eBay Browse / Etsy Open API / Product Hunt GraphQL
- [x] USPTO ODP / EPO OPS
- [x] Indiegogo：不做（官方 private API 被 Cloudflare 拦截）
- [x] 免费层 quota 计数与降级（YouTube / eBay / Etsy）

其他站点不写专属适配器：只走 P1 OpenCLI 或 P2 第三方采集。

### R6 — P0/P1/P2 分层

- [x] `BackendSpec.tier`，默认 `p1`
- [x] 注册表强制按 `p0 → p1 → p2` 稳定排序
- [x] backend 级 `key`，同一渠道不同层可用不同 key
- [x] 配额/限流/未登录自动降层；错误按可行动性排序
- [x] `deep-reach tiers`
- [x] doctor 显示每渠道 tier 覆盖 + OpenCLI 推荐版本
- [x] P0 后端：`bilibili-public`、`tencent-quote`、`http-read`、`youtube-api`、`github-api`、`v2ex-public`

### R7 — 雪球编排（对齐 Agent-Reach）

- [x] `tencent-quote` → `xueqiu-api` → OpenCLI
- [x] `tencent-search`（smartbox）→ `xueqiu-api` → OpenCLI
- [x] `hot` / `hot_stocks` 走雪球 API，可选 `xueqiu.cookie`
- [x] 美股 ticker（`AAPL`、`BRK.B`）
- [x] 雪球 API 失败时按 `NEED_LOGIN` 降层


## 10. 验收

- `deep-reach channels` 不再出现未实现渠道。
- `deep-reach bilibili search "收纳"`、`youtube search`、`weibo hot`、`xueqiu quote`、`amazon search`、`web read` 可用。
- 缺 key / 缺登录时 `doctor` 给出明确下一步。
- 写命令 100% 拦截。
- 40+ 单元测试通过。
- `SKILL.md` 和 `capabilities.md` 完整。
