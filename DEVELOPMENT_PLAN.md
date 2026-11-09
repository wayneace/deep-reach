# Deep-Reach 开发计划（v0.1 历史）

> 历史文档。当前 keys 模板路径为 `deep_reach/data/keys.example.yaml`；CLI 状态语义与 URL 边界以 README 为准。

> 注意：v0.2 已按产品思维重构。  
> 产品定义见 [PRODUCT.md](PRODUCT.md)，重构计划见 [REFACTOR_PLAN.md](REFACTOR_PLAN.md)。  
> 本文保留为 v0.1 的实施记录，部分命令和 registry 名称已过时。

> 版本：v0.1 草案  
> 日期：2026-11-07  
> 状态：设计确认中，尚未开始编码  
> 项目目录：`deep-reach`

---

## 1. 项目定位

### 1.1 一句话

仿照 Agent-Reach 的 Channel / Action / Backend 架构，以 **OpenCLI 2.x 作为浏览器引擎**，做一个个人轻量使用的产品调研编排器，覆盖国内外社媒、Amazon 选品、众筹、专利/版权。

### 1.2 目标

- 一个 CLI：`deep-reach <channel> <action> [参数]`。
- 统一结果信封和错误码，方便 agent 和脚本调用。
- 官方 API 优先，但**只用免费层**；没有 key 或额度用完时自动降级到 OpenCLI / Jina / Firecrawl / Bright Data。
- 没有 key 也能正常启动和运行，只是部分源降级。
- 模块化：新增源只改 registry/adapter，不改核心调度。
- 个人轻量：单机、SQLite、本地文件，不做分布式、多用户、队列服务。

### 1.3 非目标

- 不做写操作：不发帖、不评论、不点赞、不私信、不关注。
- 不做付费 API：X API、Keepa API、WIPO 付费服务、Lens.org 等不接。
- 不做独立发现层：发现交给 Cherry/Agent 自带搜索；需要时再接一个可选搜索后端。
- 不做 MCP 核心链路：MCP 只作为后续可选的交互层。
- 不做通用爬虫平台：只做产品调研需要的源。

### 1.4 与 Agent-Reach / OpenCLI 的关系

```text
Agent-Reach  = 参考架构（Channel / Action / Backend / dispatch / envelope / doctor）
OpenCLI 2.x  = 浏览器引擎（adapter + browser primitives + JSON 输出）
Deep-Reach = 新的编排层（registry + 免费层 policy + 统一 schema + 缓存/额度）
```

- **不 fork Agent-Reach，不修改 OpenCLI 源码。**
- 参考 Agent-Reach 的 MIT 代码时保留声明；复制少量代码需在 `NOTICE` 中注明。
- OpenCLI 作为 npm 依赖管理，固定版本 + 兼容层 + 升级测试。

---

## 2. 命名与目录

### 2.1 命名映射（仿 Agent-Reach）

| Agent-Reach | Deep-Reach |
|---|---|
| 仓库 `Agent-Reach` | `deep-reach` |
| Python 包 `agent_reach` | `deep_reach` |
| CLI `agent-reach` | `deep-reach` |
| 配置目录 `~/.agent-reach/` | `~/.deep-reach/` |
| `channels/` | `channels/` |
| `backends/` | `backends/` |
| `runtime/` | `runtime/` |
| `skill/SKILL.md` | `skill/SKILL.md` |
| `Channel / Action / Param` | 同名 |
| `run_action()` / `envelope()` / `make_item()` | 同名 |
| `doctor` / `add` / `remove` / `login` / `logout` | 同名 |
| 错误码 `NEED_LOGIN` 等 | 同名，另加 `KEY_MISSING` / `QUOTA_EXHAUSTED` / `SOURCE_DISABLED` / `CONFIG_ERROR` |

### 2.2 目录结构

```text
deep-reach\
  pyproject.toml
  README.md
  DEVELOPMENT_PLAN.md
  NOTICE
  .gitignore

  deep_reach/
    __init__.py
    __main__.py
    cli.py

    channels/
      __init__.py
      base.py
      social/
        youtube.py
        github.py
        v2ex.py
        x.py
        reddit.py
        xiaohongshu.py
        zhihu.py
        weibo.py
        douyin.py
        bilibili.py
        xueqiu.py
        tieba.py
        hupu.py
      commerce/
        amazon.py
        ebay.py
        etsy.py
        producthunt.py
        sellersprite.py
      crowdfunding/
        indiegogo.py
        kickstarter.py
      patent/
        uspto.py
        epo.py
        kipris.py
        euipo.py
        cnipa.py
        copyright.py
      web/
        web.py

    backends/
      __init__.py
      base.py
      official/
        youtube_api.py
        github_api.py
        v2ex_api.py
        ebay_api.py
        etsy_api.py
        producthunt_api.py
        indiegogo_api.py
        uspto_api.py
        epo_api.py
        kipris_api.py
        euipo_api.py
      opencli.py
      opencli_compat.py
      bilibili_public.py
      bili_cli.py
      xueqiu_public.py
      tencent_quote.py
      jina.py
      firecrawl.py
      brightdata.py

    runtime/
      __init__.py
      dispatch.py
      result.py
      keys.py
      config.py
      state.py
      health.py
      quota.py
      browser_binding.py
      sessions.py
      tools.py
      cache.py
      clock.py

    skill/
      SKILL.md
      references/
        capabilities.md
        keys.md
        troubleshooting.md

  config/
    keys.example.yaml
    sources.yaml

  tests/
    test_cli.py
    test_keys.py
    test_envelope.py
    test_dispatch.py
    test_opencli_compat.py
    test_channels_no_key.py
    test_official_api_mocked.py
    test_bilibili_xueqiu.py

  scripts/
    smoke.py
    install_opencli.ps1
```

### 2.3 命名约定

- Channel 名：小写平台名，如 `youtube`、`xiaohongshu`、`uspto`。
- Action 名：动词，如 `search`、`read`、`comments`、`hot`、`quote`、`product`。
- Backend 标签：短横线，如 `youtube-api`、`bilibili-public`、`bili-cli`、`opencli`、`jina`、`firecrawl`。
- 错误码：大写下划线，如 `NEED_LOGIN`、`KEY_MISSING`。
- key 文件：`~/.deep-reach/keys.yaml`；模板 `config/keys.example.yaml`。
- 源注册表：`config/sources.yaml`。

---

## 3. 核心架构

### 3.1 分层

```text
CLI / Agent
  → dispatch
      → Channel（平台）
          → Action（动作）
              → Backend（有序后端）
                  → 官方 API
                  → OpenCLI
                  → Jina / Firecrawl / Bright Data
  → result envelope
  → cache / quota / health
```

### 3.2 核心抽象

```python
@dataclass(frozen=True)
class Param:
    name: str
    required: bool = True
    type: type = str
    default: object = None

@dataclass(frozen=True)
class Action:
    name: str
    params: tuple[Param, ...]
    backends: tuple[tuple[str, str], ...]   # (backend label, method name)
    public_web: tuple[str, ...] = ()
    timeout: float = 30.0

class Channel:
    name: str
    category: str
    actions: tuple[Action, ...]
    key_path: str | None = None
    requires_key: bool = False
```

Channel 负责“平台语义”，Backend 负责“怎么抓”，dispatch 负责“按顺序试”。

### 3.3 调度流程

```text
1. 校验参数
2. 检查 channel 状态（key、quota、cooldown）
3. 按 Action.backends 顺序尝试
4. 每个 backend：
   - 成功 → normalize items → envelope
   - 可恢复错误（TIMEOUT / UPSTREAM_BROKEN / NEED_SETUP）→ 下一个
   - 终止错误（BAD_INPUT / NOT_FOUND / NEED_LOGIN /
     PLATFORM_BLOCKED / RATE_LIMITED / QUOTA_EXHAUSTED）→ 停止
5. 全部失败 → 返回结构化错误，不抛异常
```

### 3.4 结果信封

```json
{
  "schema_version": 1,
  "ok": true,
  "channel": "youtube",
  "action": "search",
  "backend": "youtube-api",
  "items": [
    {
      "source": "youtube",
      "category": "social",
      "platform": "youtube",
      "url": "https://...",
      "author": "...",
      "published_at": "2026-11-01T00:00:00Z",
      "text": "...",
      "parent_id": null,
      "metrics": {"likes": 0, "comments": 0, "shares": 0},
      "backend": "youtube-api",
      "fetched_at": "2026-11-07T00:00:00Z",
      "raw": {}
    }
  ],
  "meta": {
    "elapsed_ms": 1234,
    "attempts": [{"backend": "youtube-api", "result": "ok"}],
    "degraded": false
  },
  "error": null
}
```

### 3.5 错误码

```text
NEED_SETUP        后端未安装/未配置
NEED_LOGIN        需要登录
UPSTREAM_BROKEN   上游坏了，可尝试下一个后端
TIMEOUT           超时，可尝试下一个后端
RATE_LIMITED      平台限流，停止并冷却
PLATFORM_BLOCKED  平台风控/验证码，停止，不换后端
NOT_FOUND         内容不存在
BAD_INPUT         参数错误
KEY_MISSING       需要的 key 缺失，降级
QUOTA_EXHAUSTED   免费额度用完，降级
SOURCE_DISABLED   这个源没有可用后端
CONFIG_ERROR      配置文件错误，启动失败
```

---

## 4. Key 管理与免费层降级

### 4.1 文件位置

```text
真实文件（gitignore）: ~/.deep-reach/keys.yaml
仓库模板（提交）:      config\keys.example.yaml
覆盖路径:              DEEP_REACH_KEYS_FILE=...
```

### 4.2 keys.yaml 结构

```yaml
version: 1

official:
  youtube:
    api_key: ""          # 缺失 → 官方禁用，走 opencli youtube
  github:
    token: ""            # 缺失 → 60 req/h；有 token → 5,000 req/h
  v2ex:
    token: ""            # 可选
  ebay:
    client_id: ""
    client_secret: ""
    refresh_token: ""    # 缺失 → 官方禁用，走网页/Jina
  etsy:
    api_key: ""          # 缺失 → 官方禁用，走 Jina/Firecrawl
  producthunt:
    token: ""            # 缺失 → 官方禁用，走 opencli producthunt
  uspto:
    odp_api_key: ""
    tsdr_api_key: ""     # 缺失 → 走 bulk/网页
  epo:
    consumer_key: ""
    consumer_secret: ""  # 缺失 → 走 Espacenet/网页
  kipris:
    api_key: ""          # 缺失 → 走 Google Patents/网页
  euipo:
    client_id: ""
    client_secret: ""    # 缺失 → 走网页

search:
  exa:
    api_key: ""
  tavily:
    api_key: ""
  firecrawl:
    api_key: ""
  brightdata:
    api_token: ""
  brave:
    api_key: ""
  jina:
    api_key: ""          # 缺失 → 20 RPM/IP；有 key → 500 RPM

browser:
  opencli_profile: "auto"   # 自动读取已连接的 Chrome contextId
```

### 4.3 状态语义

```text
OK          所有后端可用
DEGRADED    官方 API 不可用，但有兜底
DISABLED    官方和兜底都不可用（只影响这个源）
CONFIG_ERROR YAML/格式错误（整体启动失败）
```

### 4.4 加载规则

- `keys.yaml` 不存在 → 视为全空，所有可选后端禁用；不报错。
- 空字符串 / `null` / `changeme` → 视为缺失。
- YAML 语法错误 → `CONFIG_ERROR`，明确报错。
- 环境变量优先于文件：`DEEP_REACH_YOUTUBE_API_KEY` 等。
- `doctor` 只显示 `set / missing`，绝不打印 key 值。
- `--strict-keys` 可选：CI 中缺 key 直接失败；默认关闭。

### 4.5 有 key / 无 key 行为

| 源 | 无 key | 有 key |
|---|---|---|
| YouTube | 官方禁用 → OpenCLI / yt-dlp | 10k units/天；搜索 100 次/天 |
| GitHub | 60 req/h | 5,000 req/h |
| V2EX | 公开 API | 无变化 |
| eBay | 官方禁用 → 网页/Jina | 5,000 calls/天 |
| Etsy | 官方禁用 → Jina/Firecrawl | 10 QPS / 10k QPD |
| Product Hunt | 官方禁用 → OpenCLI | 非商业免费 |
| Indiegogo | 公开 API | 无 |
| USPTO ODP | 禁用 → bulk/网页 | 5M 元数据/周 |
| USPTO TSDR | 禁用 → 网页 | 60 req/min |
| EPO OPS | 禁用 → Espacenet/网页 | 4GB/周 |
| KIPRIS | 禁用 → Google Patents/网页 | 免费 key |
| EUIPO | 禁用 → 网页 | 免费注册 |
| Jina | 20 RPM | 500 RPM |
| Exa/Tavily/Firecrawl/Bright Data/Brave | 禁用 | 各自额度 |
| B站 | 公开 API + bili-cli | 无需 key；登录解锁字幕 |
| 雪球 | 腾讯行情 + 公开 JSON | 无需 key；登录解锁热帖 |
| OpenCLI 社媒 | 无需 key；浏览器登录 | — |

---

## 5. 渠道与后端

### 5.1 社媒（国际）

| Channel | Backends（顺序） | Key |
|---|---|---|
| `youtube` | `youtube-api` → `opencli youtube` → `yt-dlp` | 需要（可降级） |
| `github` | `github-api` → `gh` | 可选 |
| `v2ex` | `v2ex-api` | 不需要 |
| `x` | `opencli x` | 不需要 |
| `reddit` | `opencli reddit` | 不需要 |
| `bluesky` | `bluesky-atproto` | 可选 app password |
| `hackernews` | `hn-algolia` | 不需要 |

### 5.2 社媒（国内）

| Channel | Backends（顺序） | 备注 |
|---|---|---|
| `bilibili` | `bilibili-public` → `bili-cli` → `opencli bilibili subtitle` | 字幕需登录 |
| `xueqiu` | `tencent-quote` → `xueqiu-public` → `opencli xueqiu` | 热帖需登录 |
| `xiaohongshu` | `opencli xiaohongshu search/note/comments` | 登录态 |
| `zhihu` | `opencli zhihu search/question/answer-comments` | 登录态 |
| `weibo` | `opencli weibo hot/search/user-posts/comments` | 登录态 |
| `douyin` | `opencli douyin profile/videos/hashtag` | 搜索命令以 `opencli list douyin` 为准 |
| `tieba` | `opencli tieba search/posts/read` | 公开+登录 |
| `hupu` | `opencli hupu search/detail` | 公开+登录 |

### 5.3 Amazon / 选品

| Channel | Backends（顺序） | Key |
|---|---|---|
| `amazon` | `opencli amazon bestsellers/search/product/offer` → Jina/Firecrawl | 不需要 |
| `ebay` | `ebay-api` → Jina/Firecrawl | 需要（可降级） |
| `etsy` | `etsy-api` → Jina/Firecrawl | 需要（可降级） |
| `producthunt` | `producthunt-api` → `opencli producthunt` | 需要（可降级） |
| `sellersprite` | 浏览器技能 / Jina | 不需要 API |
| `1688` | 1688 CLI | 不需要 |

### 5.4 众筹

| Channel | Backends（顺序） | Key |
|---|---|---|
| `indiegogo` | `indiegogo-api` | 不需要 |
| `kickstarter` | `opencli web` → Firecrawl → Bright Data | 不需要 |

### 5.5 专利 / 版权

| Channel | Backends（顺序） | Key |
|---|---|---|
| `uspto` | `uspto-odp` / `uspto-tsdr` → 网页 | 需要（可降级） |
| `epo` | `epo-ops` → Espacenet/网页 | 需要（可降级） |
| `kipris` | `kipris-api` → Google Patents/网页 | 需要（可降级） |
| `euipo` | `euipo-api` → 网页 | 需要（可降级） |
| `cnipa` | 浏览器 / 批量数据 | 不需要 |
| `copyright` | `copyright-bulk` / 未文档化 JSON → 网页 | 不需要 |

### 5.6 Web / Reader

| Channel | Backends（顺序） | Key |
|---|---|---|
| `web` | `jina-reader` → Firecrawl → Bright Data | Jina 可选 |

---

## 6. OpenCLI 集成

### 6.0 CLI 安装策略

- **本项目**：本地项目 CLI，不装全局。用 Cherry 自带的 `uv`：
  ```bash
  uv run deep-reach doctor
  ```
- **外部可复用 CLI**：OpenCLI 走 Cherry managed CLI 流程（`mcp__cherry-tools__cli_install`），不要 `npm install -g`。
- **不要**用 `pip install -g` / `npm install -g` / `pipx install` 绕过 Cherry 的 managed 环境。
- 如果以后把 `deep-reach` 发布到 PyPI 或 GitHub，再考虑用 `pipx:deep-reach` / `github:owner/repo` 安装为 Cherry managed CLI。

### 6.1 版本

- 目标：OpenCLI **2.0.2**（当前 latest）。
- 固定版本，升级前跑兼容测试。
- 兼容层同时识别 1.8.x 和 2.x 的 JSON envelope。

### 6.2 安装与发现

```bash
# Cherry managed CLI（需要审批）
# recipe: npm:@jackwener/opencli
# 或按 cli_search 返回的 recipe 安装
opencli --version
opencli list -f json
```

浏览器桥接需要手动安装一次 Browser Bridge 扩展：

1. Chrome Web Store 安装 `OpenCLI` 扩展，或从 GitHub Releases 加载未打包扩展。
2. `chrome://extensions` 确认启用。
3. `opencli doctor` 验证连接。

当前 `opencli_profile: auto` 会自动读取 `opencli doctor` 返回的已连接 Chrome `contextId`，因此会复用该 Chrome profile 的登录态；它还不是 Agent-Reach 那种 Reach-owned 专用浏览器 profile。若要隔离，需要新建专用 Chrome profile、在该 profile 安装 OpenCLI 扩展，再把 `contextId` 写进 keys；Phase 1.5 会增加 `deep-reach profile` 命令。不要和 bsk 绑同一个 tab。

- 启动时检测 `opencli --version`。
- 用 `opencli list -f json` 动态发现 adapter 和命令，不硬编码 162 个站点。
- 如果版本不兼容，`doctor` 报 `NEED_SETUP`，不崩溃。

### 6.3 通用 passthrough

```bash
deep-reach opencli <site> <command> [args] -f json
```

内部：

```python
argv = ["opencli", site, *args, "-f", "json"]
env = {
    # auto: 从 `opencli doctor` 读取已连接的 contextId
    # 或显式填入专用 Chrome profile 的 contextId
    "OPENCLI_PROFILE": "<contextId>",
    "OPENCLI_WINDOW": "background",
    "OPENCLI_CDP_ENDPOINT": "",
    "OPENCLI_CDP_TARGET": "",
}
```

### 6.4 只读白名单

OpenCLI 有写操作。只允许：

```text
search, read, note, comments, hot, feed, user, profile,
videos, subtitle, transcript, job*, product, offer,
bestsellers, new-releases, movers-shakers, rankings
```

拒绝：

```text
post, reply, comment, like, unlike, follow, unfollow,
publish, delete, send, invite, greet, save, subscribe
```

白名单放在 `runtime/tools.py`，新增命令必须显式加入。

### 6.5 浏览器隔离

当前状态：

- `opencli_profile: auto` → 使用已连接的 Chrome profile（contextId）。
- 后台窗口：`OPENCLI_WINDOW=background`。
- 同站 2 并发，全局 4 并发（待实现）。
- `search` / `jobs` 类动作同 channel 间隔 10 秒（待实现）。
- 登录窗口独占浏览器（待实现）。
- 跨进程文件锁，避免并发操作同一 profile（待实现）。

Phase 1.5 的专用 profile：

- 新建 Chrome profile `Deep-Reach`，安装 OpenCLI 扩展。
- `deep-reach profile status` 显示当前连接的 contextId。
- `deep-reach profile set <contextId>` 写入 `~/.deep-reach/keys.yaml`。
- `deep-reach profile launch` 用专用 `--user-data-dir` 启动 Chrome（扩展需先手动装一次）。
- 这样才接近 Agent-Reach 的 Reach-owned browser profile。

---

## 7. 官方 API 适配器

### 7.1 P0 清单

```text
YouTube Data API
GitHub REST
V2EX API
eBay Browse API
Etsy Open API v3
Product Hunt GraphQL
Indiegogo Public API
USPTO ODP + TSDR
EPO OPS
```

### 7.2 Adapter 接口

```python
class OfficialBackend:
    label: str
    def available(self, keys) -> bool: ...
    def search(self, query: str, limit: int, timeout: float) -> list[Document]: ...
    def read(self, url: str, timeout: float) -> list[Document]: ...
    def quota(self) -> QuotaState: ...
```

- 每个 backend 自己处理认证、分页、错误映射。
- 返回统一 `Document`，原始 JSON 放 `raw`。
- 失败抛 `ReachError`，由 dispatch 分类。

### 7.3 额度跟踪

- 每个源在 SQLite `quota` 表记录：日期、已用、上限、重置时间。
- 调用前检查；接近上限时降低优先级。
- `QUOTA_EXHAUSTED` 时自动降级，不调用付费接口。

### 7.4 Token 刷新

- OAuth 类（eBay、Etsy、EPO、Product Hunt）在 `~/.deep-reach/state/tokens.json` 缓存 access token。
- client_id/secret 放 keys.yaml；token 缓存单独存，gitignore。
- 刷新失败 → `NEED_SETUP`，降级。

---

## 8. 存储与缓存

### 8.1 SQLite

`~/.deep-reach/state.db`：

```sql
documents(
  id INTEGER PRIMARY KEY,
  source TEXT, category TEXT, platform TEXT,
  url TEXT UNIQUE, author TEXT, published_at TEXT,
  text TEXT, parent_id TEXT, metrics TEXT,
  backend TEXT, fetched_at TEXT, raw TEXT
);

quota(
  source TEXT, backend TEXT, window TEXT,
  used INTEGER, limit_value INTEGER, reset_at TEXT,
  PRIMARY KEY(source, backend, window)
);

health(
  channel TEXT, action TEXT, backend TEXT,
  code TEXT, at TEXT, fingerprint TEXT,
  PRIMARY KEY(channel, action, backend)
);

runs(
  id TEXT PRIMARY KEY, query TEXT, started_at TEXT,
  finished_at TEXT, meta TEXT
);
```

### 8.2 原始页面

```text
data/<run-id>/pages/<source>-<hash>.md
```

- 只存文本/Markdown，不存原始 HTML（除非调试）。
- `url` 唯一索引去重。
- 缓存命中时不重复调用后端。

---

## 9. CLI

```bash
deep-reach doctor
deep-reach channels
deep-reach keys check
deep-reach source list
deep-reach quota

deep-reach youtube search "standing desk" --limit 20
deep-reach bilibili search "收纳" --limit 20
deep-reach bilibili subtitle BV1xx
deep-reach xueqiu quote SH600519
deep-reach xiaohongshu search "露营灯"

deep-reach read https://example.com/article
deep-reach opencli amazon search "desk organizer" --limit 10
```

输出默认一行 JSON；`--format table|yaml|md` 可选。

`doctor` 示例：

```text
YouTube     key: missing   official: disabled    fallback: opencli
GitHub      key: missing   official: 60 req/h     fallback: gh
Bilibili    key: n/a       public: ok             fallback: opencli (subtitle needs login)
Xueqiu      key: n/a       public: ok             fallback: opencli
OpenCLI     2.0.2         browser: connected     profile: auto (contextId)
Exa         key: missing   search: disabled
Jina        key: missing   reader: 20 RPM
```

---

## 10. 测试

### 10.1 单元测试

- key 加载：缺文件、空值、非法 YAML、环境变量覆盖。
- envelope：成功、失败、attempts。
- dispatch：回退、终止错误、cooldown。
- OpenCLI compat：1.8/2.x envelope。
- 只读白名单：写命令必须被拒绝。

### 10.2 集成测试

- `doctor` 在空 keys 下正常运行。
- `channels` 列出所有渠道。
- 每个 channel 的 `backends` 顺序正确。
- 缺 key 时 `DEGRADED`，不抛异常。

### 10.3 Smoke

```bash
python scripts/smoke.py --no-keys
python scripts/smoke.py --with-keys
```

覆盖：

```text
OpenCLI: x, reddit, xiaohongshu, zhihu, weibo, douyin, bilibili, xueqiu
官方:   youtube, github, v2ex, ebay, etsy, producthunt, indiegogo, uspto, epo
Reader: jina
```

### 10.4 验收

- 空 keys 下全部测试通过。
- 有 keys 下官方后端优先。
- 写命令 100% 被白名单拒绝。
- OpenCLI 2.0.2 下 8 个社媒渠道 smoke 通过。

---

## 11. 开发阶段

### Phase 0 — 骨架（2–3 天）

- [ ] `pyproject.toml`、CLI 入口、包结构。
- [ ] `runtime/keys.py`、`runtime/config.py`。
- [ ] `runtime/result.py`、`runtime/dispatch.py`。
- [ ] `doctor`、`channels`、`keys check`。
- [ ] `config/keys.example.yaml`、`config/sources.yaml`。
- [ ] 空 key 测试。

**验收**：`deep-reach doctor` 无 key 可运行；`pytest` 通过。

### Phase 1 — OpenCLI 引擎（3–5 天）

- [ ] 安装/版本检测、`opencli list -f json`。
- [ ] `backends/opencli.py`、`opencli_compat.py`。
- [ ] 通用 passthrough channel。
- [ ] 只读白名单、浏览器 profile、并发槽、搜索间隔。
- [ ] X / Reddit / 小红书 / 知乎 / 微博 / 抖音 smoke。

**验收**：6 个社媒渠道 search/read 可用；写命令被拒绝。

### Phase 2 — 官方 API P0（5–7 天）

- [ ] YouTube、GitHub、V2EX。
- [ ] eBay、Etsy、Product Hunt、Indiegogo。
- [ ] USPTO ODP/TSDR、EPO OPS。
- [ ] 额度跟踪、token 刷新。

**验收**：有 key 走官方；无 key 降级不崩溃。

### Phase 3 — 国内 + 电商/众筹（3–5 天）

- [ ] B站：`bilibili-public` → `bili-cli` → OpenCLI 字幕。
- [ ] 雪球：`tencent-quote` → `xueqiu-public` → OpenCLI。
- [ ] Amazon、Kickstarter、1688、SellerSprite。
- [ ] 贴吧、虎扑。

**验收**：B站/雪球无 key 可用；Amazon/Kickstarter 通过 OpenCLI/浏览器可用。

### Phase 4 — Reader / 缓存 / 额度（3–4 天）

- [ ] Jina Reader、Firecrawl、Bright Data。
- [ ] 可选 Brave/Exa 发现（默认关闭）。
- [ ] SQLite 缓存、去重、quota、health。
- [ ] 失败降级和 cooldown。

**验收**：缓存命中不重复调用；额度耗尽自动降级。

### Phase 5 — Skill / 文档 / 打包（2–3 天）

- [ ] `skill/SKILL.md`、`capabilities.md`、`keys.md`。
- [ ] README、安装/升级说明。
- [ ] `scripts/smoke.py`、CI。
- [ ] 上手指南。

**验收**：新用户按 README 能装好；无 key 模式有明确说明。

---

## 12. 风险与对策

| 风险 | 对策 |
|---|---|
| OpenCLI 2.x 改 CLI/JSON | 固定版本 + compat 层 + 升级 smoke |
| 平台风控/验证码 | 专用 profile、小号、低频、2/4 并发、10 秒间隔 |
| 免费额度变化 | 额度写配置，不写死；`QUOTA_EXHAUSTED` 自动降级 |
| key 泄漏 | keys.yaml 不进 git；doctor 脱敏；错误信息 scrub |
| 平台 ToS | 只读；不存储禁止存储的内容；不重分发 |
| 上游 adapter 失效 | `doctor` + health + 可切换 backend |
| 维护负担 | 模块化 + registry + 测试；不 fork OpenCLI |

---

## 13. 开放问题

- [ ] 项目名是否用 `deep-reach`，还是换成更短的名字？
- [ ] 第一批要申请哪些 key：YouTube / GitHub / eBay / Etsy / Product Hunt / USPTO / EPO？
- [ ] Jina Reader 是否填免费 key（20 → 500 RPM）？
- [ ] 是否需要在 Phase 4 之后加一个可选的 `discover` 命令？
- [ ] 是否需要在 v0.2 把 orchestrator 暴露成一个 MCP server？
- [ ] Windows 专用 Chrome profile 路径是否固定在 `%LOCALAPPDATA%`？

---

## 14. v0.1 验收清单

- [ ] `deep-reach doctor` 无 key 正常运行。
- [ ] `deep-reach channels` 列出全部渠道。
- [ ] X / Reddit / 小红书 / 知乎 / 微博 / 抖音 / B站 search 可用。
- [ ] B站 / 雪球 公开接口优先链路可用。
- [ ] YouTube / GitHub / V2EX / eBay / Etsy / Product Hunt / Indiegogo / USPTO / EPO 适配器可用。
- [ ] 缺 key 时 `DEGRADED`，不崩溃。
- [ ] 写命令白名单 100% 拦截。
- [ ] SQLite 缓存 + quota + health 可查。
- [ ] 空 key / 有 key 两套测试通过。
- [ ] README + SKILL.md + keys.example.yaml 完整。
