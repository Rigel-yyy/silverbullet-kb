# SilverBullet KB Nightly Maintainer Bot

本目录存放符合 [ADR 0002](../docs/adr/0002-scheduled-maintainer-boundary.md) 的专职夜间维护 bot 资产，用于定时从 Hindsight 增量拉取近期会话文档、按四门控筛选跨仓库通用心智模型与能力破局手法、并经 `silverbullet-kb` 条件写入 SilverBullet `Knowledge/`。

## 目录结构与文件所有权

- `bot/SOUL.md`: 维护者人设、ADR 0002 硬边界与事后汇报规则 (仓库拥有，由 `install.py bot` 符号链接到 bot 主目录)。
- `bot/skills/kb-nightly-distill/SKILL.md`: 校准后的夜间四步提炼工作流 skill (仓库拥有，符号链接到 bot 的 `skills/`、`.claude/skills/` 与 `.agents/skills/`)。
- `bot/scripts/fetch_hindsight_docs.py`: 零第三方依赖的 Python 3 增量抓取脚本，通过 `curl` 子进程访问 Hindsight REST API，支持 `--precheck`、`--fetch` 与 `--advance`。
- Orca 托管文件: `AGENTS.md`、`CLAUDE.md`、`bot.json` 由 Orca 自动生成并覆写，`install.py bot` 绝不触碰这些文件。
- 运行态状态: `~/.orca/bots/<bot-name>/memory/` 存放本地水位游标 (`hindsight-watermark.json`) 与临时抓包文件，绝不提交到 Git。

## 前置条件

- 已在当前机器安装 `silverbullet-kb` 技能 (`python3 install.py verify` 返回 0) 且 `sb` CLI 可访问个人 SilverBullet Space。
- 本机存在 `~/.hindsight/coding-agent.json` (含 `apiUrl`，可选 `apiToken`)，且 `curl` 可连通该接口。
- 已安装 Orca CLI (`orca`)。

## 步骤 1: 创建 Orca Bot

在 Orca bot 对话中发起创建卡片 (由主人点击确认后在 `~/.orca/bots/silverbullet-kb-nightly` 生成 bot 目录)，或在 Orca UI 中新建同名 bot：

```bash
orca bot create --offer \
  --name silverbullet-kb-nightly \
  --purpose "Incrementally distill cross-repo engineering mental models and verified capability levers from Hindsight conversations into SilverBullet Knowledge/ per ADR 0002." \
  --watches "Newly updated Hindsight coding-agent::* conversation documents" \
  --does "Filter sessions through 4 strict gates, deduplicate against SilverBullet Knowledge/, additively merge with --if-match or create with --create, and verify via readback" \
  --reports "Concise post-hoc diff summary to chat on any create, merge, revision_conflict, or error; stay silent on NO_OP"
```

## 步骤 2: 链接仓库内的 SOUL 与 Skill

`orca bot create` 首次创建 bot 时会在 `~/.orca/bots/silverbullet-kb-nightly/SOUL.md` 写入一行初始占位文件。确认其中无需要保留的手工改动后将其移除，再运行 fail-closed 安装与校验：

```bash
rm -f ~/.orca/bots/silverbullet-kb-nightly/SOUL.md
python3 install.py bot install --bot-name silverbullet-kb-nightly
python3 install.py bot verify --bot-name silverbullet-kb-nightly
```

`install.py bot` 仅创建以下四个符号链接，绝不修改 `AGENTS.md`、`CLAUDE.md`、`bot.json`、`MEMORY.md` 或 `memory/`：

- `~/.orca/bots/<bot-name>/SOUL.md` -> `<repo>/bot/SOUL.md`
- `~/.orca/bots/<bot-name>/skills/kb-nightly-distill` -> `<repo>/bot/skills/kb-nightly-distill`
- `~/.orca/bots/<bot-name>/.claude/skills/kb-nightly-distill` -> `<repo>/bot/skills/kb-nightly-distill`
- `~/.orca/bots/<bot-name>/.agents/skills/kb-nightly-distill` -> `<repo>/bot/skills/kb-nightly-distill`

若路径已被非本仓库文件占用，`install.py bot install` 将以退出码 20 失败并保持零改动。测试或非标准目录可使用 `--bot-home /path/to/bot-home`。

## 步骤 3: 注册每日定时自动化 (无硬编码模型 ID)

将 `/path/to/silverbullet-kb` 替换为本仓库实际绝对路径，按需通过 `--exclude-banks` 排除个人或非工程 bank (例如 `coding-agent::personal,coding-agent::baic-pm`)：

```bash
orca automations create \
  --name "SilverBullet KB Nightly Distill" \
  --bot silverbullet-kb-nightly \
  --trigger daily --time 03:30 \
  --precheck "python3 /path/to/silverbullet-kb/bot/scripts/fetch_hindsight_docs.py --precheck --bot-name silverbullet-kb-nightly --exclude-banks coding-agent::personal" \
  --results-to chat \
  --prompt "Run the kb-nightly-distill skill to distill newly updated Hindsight conversation documents into SilverBullet Knowledge/ following ADR 0002. Pass --exclude-banks coding-agent::personal to fetch_hindsight_docs.py. Advance the watermark only after clean completion, emit a concise post-hoc diff summary on any change or conflict, and stay silent on NO_OP."
```

命令中刻意不写 `--model` 参数：定时任务默认继承 `silverbullet-kb-nightly` bot 自身配置的 agent 与模型，避免在仓库文档中写死很快过期的模型 ID；如需为该任务单独指定模型，请在创建后通过 Orca UI 的渐进式模型选择器或 `orca automations edit` 在本机配置。

## 手动干跑与水位排查

在不推进水位的情况下验证连通性与增量检测 (只读操作，不会修改 SilverBullet 或正式水位文件)：

```bash
# 1. 检测是否存在新 conversation:* 文档 (0=有新文档, 1=无新文档, 2=运行错误)
python3 bot/scripts/fetch_hindsight_docs.py --precheck --bot-name silverbullet-kb-nightly

# 2. 导出待提炼包到临时路径，不推进正式水位
python3 bot/scripts/fetch_hindsight_docs.py --fetch \
  --bot-name silverbullet-kb-nightly \
  --pending-file /tmp/kb-pending-watermark.json \
  --output /tmp/kb-fetch-bundle.json

# 3. 仅在确认处理完毕后才推进水位 (原子单调合并，不会回退)
python3 bot/scripts/fetch_hindsight_docs.py --advance \
  --bot-name silverbullet-kb-nightly \
  --pending-file /tmp/kb-pending-watermark.json
```

当某次夜间运行在提炼或 SilverBullet 写入阶段失败时，正式水位文件保持原状，次日会自动重试；当主人在 SilverBullet 中手动删除或改写了 bot 生成的页面时，由于已处理会话的水位已经单调推进，旧会话不会被重复捞回。
