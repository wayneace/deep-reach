# Deep-Reach Skill 入口与触发优化设计

日期：2026-11-12  
状态：待批准  
范围：A + B（改 skill 内容与触发规则；新增 `deep-reach skill` 安装/状态入口）

## 1. 背景

对比 OpenCLI、Agent-Reach 和 Deep-Reach 的 skill 入口后，发现三个具体问题：

1. **Cherry 里装的是旧版 skill。**  
   当前安装路径是 `~/Library/Application Support/CherryStudio/Data/Skills/skill/`，
   时间是 2026-11-11 01:20；repo 里的 `skill/SKILL.md` 已是 12:58 的版本。
   旧版仍写着 `roadmap`，没有 `setup`、专用 Chrome profile、P1 自动生命周期。
   用户现在用 `/skill` 触发的是旧内容。

2. **入口名不对。**  
   Cherry 把 skill 列成 `skill`（目录名），不是 frontmatter 里的 `deep-reach`。
   这和 Agent-Reach 的 `agent-reach`、OpenCLI 的 `opencli-*` 不一致。

3. **触发条件太宽、没有路由规则。**  
   现在的 description 包含“或读取公开网页时使用”，普通公开网页也会触发，
   和内置 web search/read 重叠。skill 内也没有明确说“什么时候先用内置工具、
   什么时候用 Deep-Reach、什么时候直接走 bsk”。

另外，skill 里的命令表是静态长列表，P3-only 渠道和自动渠道混在一起；
错误表缺少 `UPSTREAM_BROKEN`、`QUOTA_EXHAUSTED`、`CONFIG_ERROR`。

## 2. 目标

- 让 agent 在正确的时机调用 Deep-Reach，而不是所有网页都调用。
- 让 P0/P1/P2 自动路径、P3 bsk 回退、内置 web 工具三者的边界可直接执行。
- 让 skill 可安装、可检查、可更新；安装后的目录名是 `deep-reach`。
- 让已安装 skill 的版本与 CLI 版本保持一致，避免再次出现旧版。
- 保持现有 CLI 行为和 channel/backend 语义不变。

## 3. 非目标

- 不做 `deep-reach read <url>` 的 URL 自动路由（这是方案 C，后续单独做）。
- 不自动探测 Cherry/Claude/Cursor 等客户端的 skills 目录；`--dest` 显式传入。
- 不自动删除旧的 `<dest>/skill/` 目录。
- 不改 keys/profile/OpenCLI 的安装逻辑。
- 不做 skill 的远程市场或在线更新。

## 4. 方案选择

考虑过三种范围：

- **A：只改 skill 文案和路由。**  
  改动最小，但无法解决“装的是旧版”“目录名是 skill”的根因；下次仍会手工复制。
- **A+B：改 skill + 增加 `deep-reach skill` 入口。**  
  既解决触发和路由，又让安装/检查/更新有统一入口；推荐。
- **A+B+C：再加 `deep-reach read <url>`。**  
  更像 Agent-Reach 的单 URL 入口，但需要 URL→channel 映射、动作选择和测试，
  范围明显更大，适合后续单独做。

本次选择 **A+B**。

## 5. 设计

### 5.1 Skill 触发描述

`skill/SKILL.md` 的 frontmatter description 改为：

```yaml
description: |
  给 agent 的结构化上网入口：按 P0 官方接口 → P1 公开网页 → P2 第三方引擎 →
  P3 bsk UI 回退降级。重点覆盖产品调研：国内外社媒、Amazon 选品、众筹、专利/版权。
  当用户点名支持的平台、粘贴这些平台的链接、需要评论/字幕/榜单/商品/专利等结构化数据，
  或内置 web search/read 不可用、失败、拿不到正文时使用。
  普通公开网页优先用内置工具；Deep-Reach 补齐结构化数据和登录/反爬场景。
  写操作仅在用户明确要求时执行；付费 API、Amazon 关键词量/流量数据不在范围内。
```

关键变化：

- 明确“普通公开网页优先用内置工具”。
- 明确触发条件：点名平台、粘贴平台链接、需要结构化数据、内置失败/缺正文。
- 明确写操作只由用户明确要求触发。
- 保留产品调研范围和负向边界。

增加 `metadata`：

```yaml
metadata:
  homepage: https://github.com/wayneace/deep-reach
  version: "0.14.0"
```

版本由测试保证与 `deep_reach.__version__` 一致。

### 5.2 Skill 内的路由规则

在 SKILL.md 开头增加“选择路由”小节：

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
- 调用前用一句话说明 channel/action；P3 或写操作必须说明并确认。
- 不要假设渠道存在；以 `channels --json` 的当前环境结果为准。
- 不要一次输出全部 capabilities；需要时查单个渠道。

### 5.3 命令示例分组

把“常用命令”从 40 条静态列表改成三组，并指向 references：

1. **自动路径（P0/P1/P2）**：bilibili、youtube、weibo、xueqiu、amazon、github、v2ex、web read。
2. **P3 回退**：x、reddit、xiaohongshu、zhihu、douyin。  
   明确写“这些 channel 命令在无自动后端时返回 `NEED_UI`；直接走 `deep-reach bsk ...` 更快”。
3. **需要 key**：ebay、etsy、uspto、epo、web search。  
   指向 `doctor --json` 和 keys 文件。

完整动作目录不再写进 SKILL.md；保留 `references/capabilities.md`，
并在 SKILL.md 说明“完整矩阵见 references/capabilities.md；
实际可用性以 `deep-reach channels --json` 为准”。

### 5.4 错误表补全

在现有表上增加：

| code | 含义 | 行动 |
|---|---|---|
| `UPSTREAM_BROKEN` | 平台临时不可用 | 自动尝试下一层；全失败时按平台名告诉用户，不循环重试 |
| `QUOTA_EXHAUSTED` | 免费额度用完 | 自动降层；全耗尽时告诉用户；不要换账号 |
| `CONFIG_ERROR` | keys.yaml 等配置错误 | 让用户修配置；不要回显文件内容或 key |

并把 `NEED_SETUP` 改成可执行步骤：

1. 运行 `deep-reach doctor --json`，读 `opencli.missing`、`profile.configured`、`keys_file`。
2. OpenCLI 缺失：Cherry 用 `cli_install`（recipe `npm:@jackwener/opencli`）；
   其他客户端用 `npm install -g @jackwener/opencli@2.0.3`。
3. 然后 `deep-reach profile launch`，在专用窗口安装/启用扩展，
   `deep-reach profile status`，`deep-reach profile set <contextId>`。

`NEED_LOGIN` 区分：

- P1：登录发生在 Deep-Reach 专用 Chrome profile；不要让用户登录主浏览器。
- P3：bsk 使用当前浏览器；用户在该浏览器登录。
- 任何时候都不索要密码、Cookie 或 token。

### 5.5 命令风格

- SKILL.md 里的示例统一用安装版 `deep-reach`。
- 增加一句：“源码仓库内开发时通过 uv 运行同一 CLI（`uv run` + 命令名）；安装版直接用 `deep-reach`。”
  这里刻意不写成一个完整的 `uv run deep-reach` 字面量，避免和 5.9 的
  `assertNotIn("uv run deep-reach", text)` 冲突。
- 去掉 skill 中所有 `uv run deep-reach` 示例，避免用户环境找不到项目。

### 5.6 Skill 打包位置

把 canonical skill 从仓库根 `skill/` 移到：

```text
deep_reach/data/skill/SKILL.md
deep_reach/data/skill/references/capabilities.md
```

理由：

- `deep_reach/data/` 已经是随 wheel 打包的数据目录（channels.yaml、keys.example.yaml）。
- `deep-reach skill install` 可以用 `importlib.resources` 定位，不依赖当前工作目录。
- 单一来源，避免根目录和包内两份副本漂移。

需要同步修改：

- `pyproject.toml` 的 `package-data`：加入 `skill/*.md`、`skill/references/*.md`。
- `MANIFEST.in`：把 `recursive-include skill *.md` 改为 `recursive-include deep_reach/data/skill *.md`。
- `tests/test_docs_contract.py` 的路径。
- `README.md` 的目录树。
- `scripts/check_wheel.py` 增加 skill 文件存在性检查。

### 5.7 `deep-reach skill` 命令

新增 `deep_reach/runtime/skill.py`，提供：

```text
deep-reach skill path [--json]
deep-reach skill show [--json]
deep-reach skill status --dest <skills-dir> [--json]
deep-reach skill install --dest <skills-dir> [--dry-run] [--yes] [--json]
```

输出约定与现有 CLI 一致：默认文本，`--json` 输出机器可读对象。
`status` 只读，任何可读状态都返回 0（它和 `doctor` 一样是诊断命令，不是门禁）；
参数错误或 `ReachError` 返回 2。`install` 成功/无需更新返回 0，
用户拒绝或非交互缺少 `--yes` 返回 2。

`status --dest <dir>`：

- 目标固定为 `<dir>/deep-reach`。
- 状态定义与优先级（从高到低）：
  1. `missing`：目标路径不存在。
  2. `invalid`：目标存在但不是目录（例如普通文件）。
  3. `symlink`：目标是符号链接。
  4. `incomplete`：目标目录存在，但没有 `SKILL.md`，或缺少包内应有关键文件。
  5. `ahead`：安装版本高于当前包版本（不降级）。
  6. `outdated`：安装版本低于当前包版本。
  7. `modified`：版本相同，但文件树内容（含多余文件）与包内不一致；
     或 `SKILL.md` 存在但版本无法解析。
  8. `current`：版本相同且文件树完全一致。
- 版本比较用 `X.Y.Z` 数字元组；无法解析时归入 `modified`。
- 文件树哈希覆盖“包内文件 + 安装目录中多出来的文件”；多出来的文件也算
  `modified`，覆盖前需要确认，避免误删用户自定义内容。
- 返回 `installed_version`、`packaged_version`、`legacy`（是否存在 `<dir>/skill`）、
  `diff`（最多 20 个差异文件路径）。
- `ahead` 只报告，不降级；`install` 遇到 `ahead` 直接 no-op，提示用户
  “installed skill is newer than this CLI; not downgrading”。

`install --dest <dir>`：

- 目标固定为 `<dir>/deep-reach`；不会写到 `<dir>/skill`。
- 先跑 status，打印计划：
  - `missing` → 创建。
  - `current` / `ahead` → no-op。
  - `outdated` / `modified` / `incomplete` → 需要覆盖确认。
  - `invalid` / `symlink` → 拒绝（`BAD_INPUT`），不写。
- `--dry-run` 只打印计划，不写。
- `--yes` 非交互应用；非交互环境没有 `--yes` 时不做修改，返回 2（与 `setup` 一致）。
- 交互环境提示 `Overwrite existing skill at ...? [y/N]`，默认否。
- 写入使用临时目录 + 原子替换；失败时恢复旧目录。
- 目标如果是 symlink，拒绝安装（`BAD_INPUT`），避免写到目录外。
- 如果检测到 `<dir>/skill`，在输出里提示 legacy，但**不删除**；由用户确认后手动处理。

### 5.8 `setup` 集成

`deep-reach setup` 的 summary 增加一行：

```text
Skill:
  install: deep-reach skill install --dest <your client's skills directory>
  check:   deep-reach skill status --dest <your client's skills directory>
```

`setup` 不自动探测或写入客户端 skills 目录；保持客户端中立。
不自动删除旧 `skill/` 目录。

### 5.9 版本与测试

- 版本升到 `0.14.0`：`pyproject.toml`、`deep_reach/__init__.py`、`uv.lock`、
  `PRODUCT.md`、`README.md`、`CHANGELOG.md`、skill metadata。
- 新增 `tests/test_skill.py`，覆盖：
  - 包内 skill 存在且包含 SKILL.md + references。
  - `status` 的 missing/invalid/symlink/incomplete/ahead/outdated/modified/current。
  - `status` 默认文本、`--json` 输出；可读状态都返回 0。
  - `install` 创建 `<dest>/deep-reach`，不创建 `<dest>/skill`。
  - `ahead` 时 no-op，不降级。
  - 非交互无 `--yes` 不覆盖，返回 2。
  - `--yes` 覆盖并保留 `<dest>` 其他目录。
  - symlink / 普通文件目标拒绝，返回 2。
  - `--dry-run` 不写。
  - legacy `<dest>/skill` 只提示、不删除。
  - 安装目录中多出的文件使状态变为 `modified`，覆盖会先确认。
- `tests/test_docs_contract.py` 增加：
  - skill 版本与 `deep_reach.__version__` 一致。
  - skill 包含“选择路由”、`UPSTREAM_BROKEN`、`QUOTA_EXHAUSTED`、`CONFIG_ERROR`、
    `deep-reach skill install`。
  - skill 不再包含 `uv run deep-reach`。
  - skill 不再包含 `roadmap`。
- `scripts/check_wheel.py` 检查 wheel 内含
  `deep_reach/data/skill/SKILL.md` 和 `deep_reach/data/skill/references/capabilities.md`。

## 6. 文件清单

新增：

- `deep_reach/runtime/skill.py`
- `tests/test_skill.py`
- `deep_reach/data/skill/SKILL.md`（从 `skill/SKILL.md` 移入）
- `deep_reach/data/skill/references/capabilities.md`（从 `skill/references/` 移入）

修改：

- `deep_reach/cli.py`（注册 `skill` 子命令）
- `deep_reach/runtime/setup.py`（summary 增加 skill 行）
- `pyproject.toml` / `MANIFEST.in`
- `scripts/check_wheel.py`
- `tests/test_docs_contract.py`
- `README.md` / `PRODUCT.md` / `CHANGELOG.md`
- `deep_reach/__init__.py` / `uv.lock`

## 7. 验证

```bash
uv run pytest -q
uv run ruff check .
uv build
uv run python scripts/check_wheel.py
```

真实验证：

```bash
deep-reach skill path
deep-reach skill status --dest "$HOME/Library/Application Support/CherryStudio/Data/Skills"
deep-reach skill install --dest "$HOME/Library/Application Support/CherryStudio/Data/Skills"
deep-reach skill status --dest "$HOME/Library/Application Support/CherryStudio/Data/Skills"
```

期望：

- 安装后目标是 `.../Skills/deep-reach/`，不是 `.../Skills/skill/`。
- `status` 显示 `current`。
- Cherry 技能列表出现 `deep-reach`；旧的 `skill` 仍在，直到用户手动确认删除。
- `deep-reach doctor` 和现有 P1 行为不受影响。

## 8. 风险与边界

- **旧目录残留**：安装不会删除 `<dest>/skill`；用户需要确认后手动删除。设计上避免“未经同意删除”。
- **客户端目录差异**：不自动探测路径；`--dest` 由用户/agent 传入。
- **skill 内容与 CLI 行为漂移**：版本测试 + wheel 检查 + `skill status` 三重保证。
- **原子替换在 Windows 上的目录 rename**：实现时用“旧目录改名 → 新目录 rename → 删旧目录”的顺序，
  失败时恢复；测试覆盖 POSIX，Windows 走同一套逻辑但只在 CI 允许时跑。
- **不改变现有 channel/action 注册**：`skill` 是新的顶层命令，不影响现有 parser 顺序。

## 9. 已定的实现细节

- `status` 的 `diff` 字段列出最多 20 个差异文件路径；完整数量放在 `diff_count`。
- `show` 默认输出 SKILL.md 原文，`--json` 包装为 `{ok, path, content}`。
- 版本号直接写进 SKILL.md metadata，测试保证与 `deep_reach.__version__` 一致。
- 所有 `skill` 子命令默认文本输出，`--json` 输出机器可读对象，与现有 CLI 一致。
- 移动而非复制 skill 源文件；仓库根不再保留 `skill/`，避免两份副本漂移。
