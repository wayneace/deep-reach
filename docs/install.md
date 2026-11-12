# Deep-Reach 安装指南

把这份文档发给你的 agent：

```text
https://raw.githubusercontent.com/wayneace/deep-reach/main/docs/install.md
```

Deep-Reach = 一个 CLI + 一个 agent skill。先装 CLI，再按客户端装 skill；
P1（公开网页 / OpenCLI）还需要 OpenCLI 和 Chrome 扩展。

> `deep-reach` 目前不在 PyPI。不要从 PyPI 安装同名包，必须从 GitHub tag / Release 安装。

## 先选客户端

| 客户端 | CLI | Skill | OpenCLI |
|---|---|---|---|
| **Cherry Studio** | `cli_install`：`pipx:wayneace/deep-reach` | 技能市场安装 GitHub 上的 `SKILL.md` | `cli_install`：`npm:@jackwener/opencli` |
| **Codex** | GitHub tag 安装 | `~/.agents/skills` 或 `.agents/skills` | npm |
| **Claude Code** | GitHub tag 安装 | `~/.claude/skills` 或 `.claude/skills` | npm |
| **其他客户端** | GitHub tag 安装 | `deep-reach skill install --dest <skills-dir>` | npm |
| **源码开发** | `uv sync` | 仓库内 `deep_reach/data/skill/` | npm 或 `cli_install` |

通用要求：

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（CLI 安装和运行）
- Node.js / npm（OpenCLI 需要）
- Chrome（P1 使用专用 profile；首次需要安装 OpenCLI 扩展）

## Cherry Studio

### 1. 安装 Deep-Reach CLI

让 agent 调用 Cherry 的 CLI 管理器：

```text
cli_install(name="deep-reach", tool="pipx:wayneace/deep-reach", requestedVersion="v0.14.0")
```

没有 `cli_install` 工具时，用 Cherry 的 CLI 管理界面添加同一个 recipe 和版本。

### 2. 安装 skill

在 Cherry 的技能市场（marketplace）里搜索或粘贴：

```text
https://github.com/wayneace/deep-reach/blob/main/deep_reach/data/skill/SKILL.md
```

选择 `source_registry: github` 的结果安装。市场安装的目录名是 `skill`，
显示名是 `deep-reach`，后续由市场负责检查更新。

**不要再运行 `deep-reach skill install`**，否则会多装一份本地 skill。

### 3. 安装 OpenCLI

```text
cli_install(name="opencli", tool="npm:@jackwener/opencli", requestedVersion="2.0.3")
```

或在普通终端：

```bash
npm install -g @jackwener/opencli@2.0.3
```

### 4. 首次配置

```bash
deep-reach setup
deep-reach profile launch
# 在这个专用 Chrome 窗口安装/启用 OpenCLI 扩展：
# https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk
deep-reach profile status
deep-reach profile set <contextId>
deep-reach doctor
```

## Codex

### 1. 安装 CLI

```bash
uv tool install "git+https://github.com/wayneace/deep-reach@v0.14.0"
```

如果 `uv` 不存在，先安装 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 安装 skill

用户级（Codex 会扫描 `~/.agents/skills`）：

```bash
deep-reach skill install --dest ~/.agents/skills --yes
```

项目级：

```bash
deep-reach skill install --dest <repo>/.agents/skills --yes
```

安装目标是 `<skills-dir>/deep-reach/`。`~/.codex/skills` 也能用，但已弃用；
优先用 `~/.agents/skills`。

### 3. 安装 OpenCLI

```bash
npm install -g @jackwener/opencli@2.0.3
```

### 4. 首次配置

同 Cherry 的 `deep-reach setup` / `profile launch` / `profile set` 步骤。

## Claude Code

### 1. 安装 CLI

同 Codex：

```bash
uv tool install "git+https://github.com/wayneace/deep-reach@v0.14.0"
```

### 2. 安装 skill

用户级：

```bash
deep-reach skill install --dest ~/.claude/skills --yes
```

项目级：

```bash
deep-reach skill install --dest <repo>/.claude/skills --yes
```

### 3. 安装 OpenCLI

```bash
npm install -g @jackwener/opencli@2.0.3
```

### 4. 首次配置

同 Cherry 的 `deep-reach setup` / `profile launch` / `profile set` 步骤。

## 其他 agent 客户端

```bash
uv tool install "git+https://github.com/wayneace/deep-reach@v0.14.0"
deep-reach skill install --dest <client skills directory> --yes
```

`--dest` 是客户端扫描 skill 的目录；安装结果是 `<skills-dir>/deep-reach/`。
如果客户端支持 GitHub skill 市场，也可以直接安装：

```text
https://github.com/wayneace/deep-reach/blob/main/deep_reach/data/skill/SKILL.md
```

市场安装的目录名是 `skill`；CLI 安装的目录名是 `deep-reach`。两种方式选一种，不要同时装。

## 源码开发（只适用于仓库内）

```bash
git clone https://github.com/wayneace/deep-reach.git
cd deep-reach
uv sync
uv run deep-reach setup
```

`uv run deep-reach` 只是源码仓库的开发方式；安装版用户直接用 `deep-reach`。

## 首次配置（所有客户端）

```bash
deep-reach setup
deep-reach profile launch
```

在打开的专用 Chrome 窗口安装/启用 OpenCLI 扩展：

```text
https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk
```

然后：

```bash
deep-reach profile status
deep-reach profile set <contextId>
deep-reach doctor
```

- `deep-reach setup` 只创建 `~/.deep-reach/keys.yaml`，不会覆盖已有文件。
- P0/P2 不需要 OpenCLI；P1 需要专用 Chrome profile；P3 bsk 可选。
- 专用 profile 与主浏览器隔离，不会复用主浏览器登录态。

## 验证

```bash
deep-reach --version
deep-reach doctor --json
deep-reach skill status --dest ~/.agents/skills   # Codex；其他客户端换成对应目录
deep-reach weibo hot --limit 1 --text
```

`weibo hot` 是 P1：会自动启动专用 Chrome，成功后自动关闭。

## 更新

### Cherry Studio

- CLI：用 `cli_install` 更新 `pipx:wayneace/deep-reach` 到最新版本。
- Skill：在技能市场检查更新。

### Codex / Claude Code / 其他客户端

CLI 从最新 GitHub tag 重装：

```bash
uv tool install --force "git+https://github.com/wayneace/deep-reach@<latest>"
# 或
pipx install --force "git+https://github.com/wayneace/deep-reach@<latest>"
```

Skill 重新运行安装命令，CLI 会对比版本：

```bash
deep-reach skill install --dest <skills-dir> --yes
```

### 源码开发

```bash
cd deep-reach
git pull
uv sync
```

### OpenCLI

```bash
npm install -g @jackwener/opencli@2.0.3
deep-reach doctor   # 对比已安装版本与推荐版本
```

## 安全边界

- `~/.deep-reach/keys.yaml` 权限为 `0600`；不要把 key 贴在聊天里。
- P1 只使用显式绑定的专用 Chrome profile；不要把主浏览器登录态复制给它。
- P3 bsk 使用当前浏览器；写操作必须先得到用户明确确认。
- 不要把密码、Cookie 或 token 交给 agent。
