# Skill 目录与发布 tag 修复设计

日期：2026-11-13
状态：已确认（用户要求修复两处上游问题）

## 问题 1：市场安装占用通用目录名 `skill`

`deep_reach/data/skill/SKILL.md` 的父目录名是 `skill`。Cherry Studio 技能市场按
`SKILL.md` 所在目录名创建安装目录，因此 deep-reach 会安装到
`<skills-dir>/skill/`。bsk 自带的 skill 也固定使用 `<skills-dir>/skill/`，两者
冲突，导致 bsk skill 无法安装。

## 问题 2：CLI 列表显示 `vv0.14.1`

mise 的 pipx 后端把 GitHub release 的 tag 原样作为版本返回。当前 release tag 是
`v0.14.1`，所以 `cli_list` 返回 `v0.14.1`；Cherry 的 CLI 列表展示时再补一个
`v` 前缀，显示成 `vv0.14.1`。实际二进制版本是 `0.14.1`，不是重复安装。

## 决策

1. 包内 skill 目录改名为 `deep_reach/data/deep-reach/`，市场安装目录变为
   `<skills-dir>/deep-reach/`，与 CLI 的安装目录一致。
2. 从 `0.14.2` 起，GitHub release tag 使用裸 semver：`0.14.2`，不再使用
   `v0.14.2`。mise 返回 `0.14.2`，Cherry 补一个 `v` 后显示为 `v0.14.2`。
3. 旧的 `v0.14.1` 及更早 tag/release 保持不动；不重写历史。
4. 不修改 Cherry 应用、bsk 仓库或 PyPI 发布方式。

## 兼容性

- 旧市场安装（目录 `skill`）的 `sourceUrl` 指向旧路径；升级后该路径不再存在，
  需要用户卸载旧条目并从新 URL 重装。
- CLI 安装目标本来就是 `<skills-dir>/deep-reach/`，路径不变；仅 wheel 内的
  canonical skill 路径变化。
- 旧 `v*` tag 仍可用于 `uv tool install` / `pipx install`；新文档统一使用裸 tag。

## 验收

- 市场 URL 为 `.../deep_reach/data/deep-reach/SKILL.md`，安装目录为
  `<skills-dir>/deep-reach/`。
- wheel 包含 `deep_reach/data/deep-reach/SKILL.md` 和
  `deep_reach/data/deep-reach/references/capabilities.md`，不包含旧 `data/skill/`。
- `deep-reach skill path --json` 的路径末级为 `deep-reach`。
- 安装时已存在的兄弟目录 `skill/`（bsk）不被修改。
- `docs/install.md` 使用 `requestedVersion="0.14.2"` 和 `@0.14.2`，不出现
  `v0.14.2` 形式。
- 全量测试、ruff、wheel 检查通过。
