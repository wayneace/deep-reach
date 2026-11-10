# P3 bsk UI Fallback 实现计划

- 日期：2026-11-10
- 设计：`docs/superpowers/specs/2026-11-10-p3-bsk-ui-fallback-design.md`
- 目标版本：v0.11.0
- 方法：TDD，先 RED 再 GREEN；每个任务单独提交

## 约束

- P1 只保留 OpenCLI 公开命令；删除 `requires: login` 的 OpenCLI backend。
- P3 不写站点 recipe；只返回 `NEED_UI` 引导。
- bsk 全能力可用，包括写操作；守卫只拦直接内部 API 调用和 `debug replay`。
- Deep-Reach 不再声明只读；移除 OpenCLI 全局写拦截。
- bsk 默认 main profile；高风险渠道默认开启但警告。
- 不新增 MCP；不加站点 recipe。

---

## Task 1：分层与访问模型

**目标**：`TIERS` 支持 p3；`BackendSpec` 支持 `supports_login` / `risk`；`Action` 支持 `ui_fallback` / `risk`。

**文件**

- `deep_reach/channels/base.py`
- `deep_reach/channels/registry.py`
- `tests/test_tiers.py`（新增或扩展）
- `tests/test_registry.py`

**RED**

1. `TIERS == ("p0","p1","p2","p3")`，排序正确。
2. `BackendSpec(supports_login=True)` 可构造。
3. `Action(ui_fallback=True)` 可构造。
4. 注册表排序仍为 p0 → p1 → p2；p3 backend 不允许（或允许但只用于展示，二选一并测试）。

**GREEN**

- 扩展 dataclass 字段。
- 更新 `TIER_LABELS` / `TIER_ACCESS`：
  - p0 官方接口
  - p1 公开网页
  - p2 第三方引擎
  - p3 bsk UI 回退
- 保持 `TIER_ORDER` 稳定。

**验证**

```bash
uv run pytest -q tests/test_tiers.py tests/test_registry.py
```

---

## Task 2：重新分类 channels.yaml

**目标**：P1 只保留公开 OpenCLI；`http-read` / Jina 归 P1；登录动作加 `ui_fallback: true`。

**文件**

- `deep_reach/data/channels.yaml`
- `deep_reach/channels/registry.py`（解析新字段）
- `tests/test_channels_registry.py`
- `tests/test_p2_registry.py`（如受影响）

**RED**

1. `web.read` backend 顺序：`http-read`(p1) → `jina`(p1) → Firecrawl/Tavily/BrightData(p2)。
2. `x` / `reddit` / `xiaohongshu` / `zhihu` / `douyin` 不再有 `opencli-*` backend，且 `ui_fallback: true`。
3. `weibo.search`、`bilibili.subtitle`、`xueqiu.hot` 等 `requires: login` 动作不再有 OpenCLI backend，且 `ui_fallback: true`。
4. `weibo.hot/read/comments`、`bilibili.search/read/comments` 等公开 OpenCLI backend 保留。
5. `opencli-*` backend 的 `tier` 只能是 p1。

**GREEN**

- 逐动作修改 YAML：
  - 删除 `requires: login` 的 `opencli-*`。
  - 给对应动作加 `ui_fallback: true`、`risk: high`。
  - `http-read` / `jina` 从 p0/p2 改为 p1。
  - 保留公开 OpenCLI。
- 更新 registry 解析：`ui_fallback`、`risk`、`supports_login`。

**验证**

```bash
uv run pytest -q tests/test_channels_registry.py tests/test_p2_registry.py
uv run deep-reach tiers
uv run deep-reach channels --all
```

---

## Task 3：NEED_UI 与调度

**目标**：自动后端全部失败或 access 不匹配时，返回 `NEED_UI`；不把 P3 伪装成 backend。

**文件**

- `deep_reach/runtime/result.py`
- `deep_reach/runtime/dispatch.py`
- `deep_reach/runtime/availability.py`
- `tests/test_envelope.py`
- `tests/test_dispatch.py`（新增或扩展）

**RED**

1. `NEED_UI` 在 `FINAL_CODES`，有默认 hint。
2. `requires: login` 且无 backend 支持登录 → 直接返回 `NEED_UI`，不尝试公开后端。
3. 所有 backend 失败 + `ui_fallback: true` → `NEED_UI`，`meta.attempts` 保留。
4. `ui_fallback: false` → 返回原错误优先级结果。
5. `NEED_UI` envelope 包含 `tier: p3`、`meta.fallback`、`meta.profile`、`meta.risk`、`meta.policy`。
6. `error.hint` 包含 `deep-reach bsk` 示例。

**GREEN**

- 新增 `NEED_UI` 常量、hint、优先级。
- dispatch 在最后判断 `ui_fallback`。
- availability 跳过 `supports_login=False` 的 login 动作 backend。
- `meta.policy` 按设计写入。

**验证**

```bash
uv run pytest -q tests/test_envelope.py tests/test_dispatch.py tests/test_availability.py
```

---

## Task 4：bsk 薄守卫

**目标**：新增 `deep-reach bsk <args...>`，透传 bsk 全能力，只拦截直接内部 API 调用和 `debug replay`。

**文件**

- `deep_reach/backends/bsk_guard.py`（新增）
- `deep_reach/cli.py`
- `tests/test_bsk_guard.py`（新增）
- `tests/test_cli_bsk.py`（新增或合并）

**RED**

1. `debug replay` → `POLICY_BLOCKED`。
2. `evaluate "fetch('/api/x')"` → `POLICY_BLOCKED`。
3. `evaluate "document.title"` → 透传。
4. `debug requests` → 透传。
5. `network` → 透传。
6. `click @e1` → 透传。
7. `post` / `comment` / `delete` → 透传（写操作允许），stderr 有 warning。
8. `debug rule_add` → 透传，stderr 有 warning。
9. 子进程失败时返回 bsk 原 exit code，stdout/stderr 透传。
10. 守卫拦截时输出我们的 JSON 错误，exit code 1。

**GREEN**

- 实现 argv 解析与策略检查。
- `POLICY_BLOCKED` 加入 result.py。
- CLI 用 `argparse.REMAINDER` 注册 `bsk` 子命令。
- stderr 警告：main profile、写操作副作用。
- 不做站点 recipe，不解析 bsk 结果。

**验证**

```bash
uv run pytest -q tests/test_bsk_guard.py tests/test_cli_bsk.py
uv run deep-reach bsk status
uv run deep-reach bsk doctor
```

---

## Task 5：移除只读产品边界

**目标**：Deep-Reach 可写；移除 OpenCLI 全局写拦截；`WRITE_BLOCKED` 仅保留给显式只读后端。

**文件**

- `deep_reach/backends/opencli.py`
- `deep_reach/runtime/result.py`
- `tests/test_opencli_backend.py`
- `tests/test_product_contract.py`（如存在）
- `README.md`
- `PRODUCT.md`
- `skill/SKILL.md`
- `skill/references/capabilities.md`

**RED**

1. OpenCLI `post` / `comment` 不再抛 `WRITE_BLOCKED`。
2. `WRITE_BLOCKED` 的默认 hint 不再说“Deep-Reach is read-only”。
3. README / PRODUCT 不再包含“只读”承诺。
4. `PRODUCT.md` 不再声称“写命令 100% 被拦截”。

**GREEN**

- 删除 `OpenCLIClient.run()` 的 `is_read` 检查。
- 保留 `read_commands` 作为元数据。
- 更新 `WRITE_BLOCKED` hint 为“该后端不支持这个写操作”。
- 更新产品文档：可读可写；写操作有副作用；P3 可写。
- 更新 skill 文档：写操作需确认用户意图。

**验证**

```bash
uv run pytest -q tests/test_opencli_backend.py tests/test_product_contract.py
rg -n "只读|read-only|不发帖|不评论|100% 被" README.md PRODUCT.md skill deep_reach
```

---

## Task 6：展示、配置与文档

**目标**：`tiers` / `channels` / `doctor` 显示 P3、risk、ui_fallback、profile；配置项可用。

**文件**

- `deep_reach/cli.py`
- `deep_reach/runtime/doctor.py`
- `deep_reach/runtime/availability.py`
- `deep_reach/data/keys.example.yaml`（或 config 示例）
- `tests/test_cli_tiers.py`
- `tests/test_cli_channels.py`
- `tests/test_doctor.py`

**RED**

1. `tiers` 输出 P0/P1/P2/P3；P3 标注“fallback / manual”。
2. `channels` 每行显示 risk；登录动作显示 `ui_fallback`。
3. `doctor` 显示 `profile: main` 和 warning。
4. `bsk` 未安装/未连接时，`NEED_UI` hint 仍可用，并提示安装。

**GREEN**

- 扩展输出结构。
- 增加配置读取：
  - `browser.bsk_profile` 默认 `main`
  - `browser.bsk_guard` 默认 `true`
  - `risk.allow_high` 默认 `true`
- 更新 `keys.example.yaml` 注释。
- 更新 README 分层表、PRODUCT、CHANGELOG。

**验证**

```bash
uv run pytest -q tests/test_cli_tiers.py tests/test_cli_channels.py tests/test_doctor.py
uv run deep-reach tiers
uv run deep-reach channels
uv run deep-reach doctor
```

---

## Task 7：全量验证与发布准备

**目标**：测试、lint、wheel、文档、手动 smoke 全部通过。

**验证**

```bash
uv run pytest -q
uv run ruff check .
uv run pytest -q --cov=deep_reach --cov-report=term-missing
uv build --wheel
uv run python scripts/check_wheel.py
```

**手动 smoke**

```bash
uv run deep-reach bsk status
uv run deep-reach bsk doctor
uv run deep-reach bsk session start --json
uv run deep-reach bsk navigate https://example.com --session <id>
uv run deep-reach bsk observe --session <id>
uv run deep-reach bsk session stop <id>
```

**守卫 smoke**

```bash
uv run deep-reach bsk debug replay --help      # 应被 POLICY_BLOCKED
uv run deep-reach bsk evaluate "fetch('/api')" # 应被 POLICY_BLOCKED
uv run deep-reach bsk evaluate "document.title" # 应透传
```

**文档检查**

```bash
rg -n "只读|read-only|不发帖|不评论|100% 被" README.md PRODUCT.md skill deep_reach
```

**发布**

- 版本号 `0.11.0`。
- CHANGELOG 记录：
  - P3 bsk fallback
  - P1 OpenCLI 公开化
  - 移除只读边界
  - bsk 守卫
  - 主 profile 与高风险警告
- 打 tag / release 前需用户确认。

---

## 明确不做

- 不写 bsk 站点 recipe。
- 不自动解析 bsk 结果成 `items`。
- 不新增 MCP。
- 不实现所有渠道的写动作；只移除边界。
- 不默认切换到专用 profile。
- 不做 bsk 的 CDP/daemon 二次封装。
