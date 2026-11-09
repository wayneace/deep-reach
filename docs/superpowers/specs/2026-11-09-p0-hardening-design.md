# P0 加固设计（2026-11-09）

## 意图与为什么

盘点发现三处会直接影响 agent 判断或安全的 P0 问题：

1. `doctor` / `channels` 的 `status` 是注册表里的静态值，不反映当前环境。本机没有 opencli、没有任何 key，`doctor` 仍报 `8 ready`，而 `amazon search` 实际返回 `NEED_SETUP`。
2. `web read` / `http-read` 接受 `file://`、localhost、内网地址，agent 可被诱导读取本机文件或访问内网服务。
3. `config/keys.example.yaml` 没有打进 wheel，`deep-reach setup` 却提示用户复制它。

EPO 的 `Range` 原以为是 header，核对 EPO 官方 FAQ 后确认官方写法是 URL 参数 `&Range=xx-xx`，当前代码正确；本次不改行为，只加回归测试锁定。

## 目标

- `doctor` / `channels` 的 `status` 改为**环境实测值**；保留 `declared_status` 便于追溯。
- `web read` / `http-read` 只允许 `http/https`，默认拒绝 localhost、回环、私有/链路本地/保留地址；提供显式环境变量放行。
- `keys.example.yaml` 随 wheel 打包，`setup` 打印真实路径，wheel 检查断言。
- EPO 请求参数形状有测试锁定。
- 全部新增/修改行为有离线测试；不访问网络。

## 非目标

- 不做 P1 项：tag/release、PRODUCT.md 文案、Phase R5 文案、keys.yaml 权限、POSIX 进程树清理。
- 不做 EPO/eBay/Etsy/USPTO/Product Hunt 的 live key 验证。
- 不新增渠道，不改 dispatch 的降级语义。

## 方案与取舍

### 1. 状态口径（用户选择：直接改 status）

- 保留 `status` 字段名，值改为环境实测状态；新增 `declared_status` 保存注册表原值。
- 新增 `runnable`、`available_actions`、`unavailable_actions`（含原因）。
- 状态集合：`ready` / `degraded` / `needs_setup` / `needs_login` / `needs_key` / `experimental` / `planned`。
- 判定规则：
  - 每个 action：至少一个 backend 当前可用才算可用。
  - backend 可用：`requires_key` 的 key 存在；`opencli-*` 的 OpenCLI 可用。
  - `declared=needs_key`：全部 action 可用 → `ready`，否则 `needs_key`。
  - `declared=needs_login`：OpenCLI 不可用 → `needs_setup`；否则保持 `needs_login`（无法探测站点登录态）。
  - `declared=experimental`：全可用 → `experimental`；部分 → `degraded`；全不可用 → `needs_setup`。
  - `declared=ready`：全可用 → `ready`；部分 → `degraded`；全不可用 → `needs_setup`。
- OpenCLI 可用性：
  - `doctor`：用 `profile_status().connected` 精确判断。
  - `channels`：只检查是否安装（`shutil.which` / `DEEP_REACH_OPENCLI_BIN`），不启动子进程；已安装但浏览器未连接时乐观视为可用，并在文档中说明 `doctor` 才是精确检查。
- `capabilities` / `roadmap` 保持注册表语义，不做环境探测。

### 2. URL 防护（用户选择：scheme + 私有地址）

- 在 `deep_reach/backends/http.py` 增加 `validate_url()`，`fetch()` 入口调用。
- 只允许 `http` / `https`。
- host 为 IP 时用 `ipaddress.ip_address(...).is_global` 判断；为域名时 `socket.getaddrinfo` 解析后逐个检查；`localhost` / `*.localhost` 直接拒绝。
- DNS 解析失败不拦截，让后续请求以 `UPSTREAM_BROKEN` 自然失败。
- `DEEP_REACH_ALLOW_PRIVATE_URLS=1` 放行私有地址，但 scheme 仍必须是 http/https。
- `jina._target_url()` 复用同一校验，避免把内网 URL 发给第三方 reader。
- 解析结果按 host 缓存（`lru_cache`），避免一次动作内重复 DNS。

### 3. keys 模板（实现选择：移入包内）

- `git mv config/keys.example.yaml deep_reach/data/keys.example.yaml`。
- `pyproject.toml` 的 `deep_reach.data` 已匹配 `*.yaml`，无需改。
- `MANIFEST.in` 改为 `recursive-include deep_reach/data *.yaml`。
- `cli.cmd_setup` 用 `importlib.resources.files("deep_reach.data")` 打印模板真实路径。
- `scripts/check_wheel.py` 断言 wheel 中有 `deep_reach/data/keys.example.yaml`。
- README 中两处 `config/keys.example.yaml` 更新为包内路径。

### 4. EPO（研究结论：不改行为）

- `deep_reach/backends/epo.py` 加注释，引用 EPO 官方 FAQ：`Range` 是 URL 参数。
- `tests/test_wave2.py` 增加请求形状测试：`params["Range"] == "1-N"`，headers 中无 `Range`。

## 兼容性

- `status` 语义改变是**有意破坏**：从“注册表声明”变为“当前环境实测”。
- 新增 `declared_status` 供需要原值的调用方使用。
- `channels --json` 新增字段，不删除旧字段。
- CHANGELOG 增加 `Unreleased` 条目说明。

## 测试计划

- `tests/test_availability.py`：状态映射（ready/degraded/needs_setup/needs_key/needs_login/experimental）。
- `tests/test_doctor.py`：opencli 未连接时 youtube=needs_setup、amazon=degraded、weibo=needs_setup、x=needs_setup；连接时 x=needs_login。
- `tests/test_url_guard.py`：file/ftp、127.0.0.1、localhost、10.x、169.254.169.254、[::1] 被拒；https 公网通过；环境变量放行私有地址；file 仍被拒。
- `tests/test_keys.py` 或新测试：包内模板存在且包含关键 key。
- `tests/test_wave2.py`：EPO Range 是 query 参数。
- `scripts/check_wheel.py`：wheel 含 keys 模板。
- 全量 `uv run pytest -q` 必须保持通过；`uv build --wheel && uv run python scripts/check_wheel.py` 必须通过。

## 风险

- `channels` 在 opencli 已安装但浏览器未连接时会乐观显示可用；这是刻意的速度取舍，`doctor` 提供精确结果，README 会写明。
- 域名解析增加少量延迟；按 host 缓存，且与 urllib 自身的 DNS 解析重复一次。对本地 CLI 可接受。
- DNS rebinding 仍可能绕过解析时检查；本工具是本地只读 CLI，风险面有限，文档注明不承诺对抗恶意 DNS。
