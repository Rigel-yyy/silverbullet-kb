---
name: kb-nightly-distill
description: Operating workflow for the dedicated SilverBullet KB nightly maintainer bot (ADR 0002). Incrementally fetches new Hindsight conversation:* documents, clusters multi-turn reflections and action sequences through four strict admission gates, deduplicates and additively merges or creates pages in SilverBullet Knowledge/ with --create/--if-match and readback verification, advances the local watermark only after clean completion, and emits a concise post-hoc diff report (or stays silent on NO_OP).
---

# SilverBullet KB Nightly Distill Workflow

仅由经主人显式配置的专职 SilverBullet KB 夜间维护 bot 调用 (ADR 0002)。交互式 coding agent 不得调用本 skill 进行自动写入。全部 SilverBullet 读写与检索遵循 `silverbullet-kb` 技能契约 (`skill/SKILL.md`、`skill/references/document-contract.md`、`skill/references/search.md`、`skill/references/sb-cli.md`)。

## 路径与前置定位

- 抓取脚本: 先解析本 skill 目录符号链接的真实路径，相对定位 `../../scripts/fetch_hindsight_docs.py` (即 `silverbullet-kb` 仓库内的 `bot/scripts/fetch_hindsight_docs.py`)。
- 运行态目录: 使用当前 bot 主目录下的 `memory/`，例如 `~/.orca/bots/<bot-name>/memory/`，存放：
  - 水位文件: `hindsight-watermark.json` (仅由 `--advance` 原子更新)
  - 待推进快照: `pending-watermark.json` (每次 `--fetch` 覆写)
  - 当次抓包产物: `fetch-bundle.json` (供本轮读取)
- 绝不在任何步骤中修改 `AGENTS.md`、`CLAUDE.md`、`bot.json` 或硬编码模型 ID。

## Step 1: 增量拉取 Hindsight 会话文档 (只读，不推进水位)

执行增量拉取，确保本次抓取不会提前修改正式水位文件：

```bash
SCRIPT_PATH="$(python3 -c 'from pathlib import Path; print((Path("skills/kb-nightly-distill").resolve().parents[1] / "scripts" / "fetch_hindsight_docs.py"))')"
python3 "$SCRIPT_PATH" --fetch \
  --bot-name "<bot-name>" \
  --state-file "memory/hindsight-watermark.json" \
  --pending-file "memory/pending-watermark.json" \
  --output "memory/fetch-bundle.json"
```

若主人配置了排除列表 (如 `--exclude-banks coding-agent::personal,coding-agent::baic-pm`)，与定时任务 `--precheck` 保持一致传入。检查退出码与 `memory/fetch-bundle.json`：

- 若脚本非零退出 (exit 2): 不推进水位，直接记录运行错误并在 Step 4 向主人汇报错误摘要 (绝不泄露 `apiToken`)。
- 若 `doc_count == 0`: 不调用 SilverBullet，直接进入 Step 4 判定为 `NO_OP` (定时运行保持静默，交互触发则显式回报 `NO_OP`)。

## Step 2: 单会话聚类与严苛四门控提炼

逐篇审阅 `memory/fetch-bundle.json` 中的 `documents` 列表 (每篇包含 `bank_id`、`source_repo`、`doc_id`、`reflections` 与有界 `turns`)。目标是从中识别真正可跨仓库复用的两类资产：

1. **第一性原理 / 工程心智模型**: 揭示系统底层因果机制，能指导面对同类问题时怎么思考与推导。
2. **已验证的能力与破局杠杆**: 证明 agent 可以借助某类 bash 技巧、外部 CLI、源码/二进制探查、控制面 API 或消费端解析器工具解决看似棘手的障碍。

提炼与聚类规则：

- 先将同一会话内围绕同一故障连续推进的多轮 `<ears_reflection>` 块及其紧邻的 `action` 工具调用序列 (例如: 假说 -> 反证 -> 根因定位 -> 终验) 聚合成一条完整因果链，不要拆成碎片。
- 对每条候选逐项过审 **严格准入四门控** (任一不满足立即丢弃，宁缺毋滥；若全部文档均无合格条目，本轮直接判定为 `NO_OP`)：
  1. `[去仓库绑定]` 把具体产品名、业务模型、内部模块名抽离后，核心机制在其他语言或项目里依然成立。单仓库业务逻辑、专有数据结构、一次性重构决策一律留在 Hindsight，禁止提取。
  2. `[有机制有正向做法]` 必须是正面生成式指导 ("遇到 X 现象时，因为 Y 机制，应采用 Z 手段验证/解决")。严禁提取任务进度/PR/CI/阻塞汇报，严禁提取没有解释因果机制的孤立 "不要 X" 禁令。
  3. `[证据已闭环]` 必须有本会话中真实执行的命令、源码读取、对照实验或输出验证支撑；未验证猜测、因环境阻塞未跑通的假说一律剔除。
  4. `[严格脱敏]` 绝对剥离 Token、密码、Cookie、真实公网 IP、个人邮箱/账户交易细节及客户私密数据；具体例证仅保留技术载体与脱敏方法。

每条通过四门控的候选，严格按以下紧凑骨架组织 (使用中文，仅用 ASCII 标记 `->`、`-`、`[ok]`、`[x]`、`[!]`，禁用 emoji 与 Unicode 符号，正文段落保持单行不硬折行)：

- 建议路径与 H1: `Knowledge/<kebab-slug>--<4hex>.md` 与 `# <清晰正向标题>`
- 建议 tags: `source/<origin-repo>`、`type/experience`、1-3 个通用小写 kebab-case `topic/<subject>` (禁止使用仓库专有名或临时查询词作 topic)
- `## 核心心智模型 / 能力杠杆`: 1-2 句正向陈述
- `## 底层机制`: 为什么成立
- `## 触发场景与正向做法`: 可直接复用的最小命令模式或操作步骤
- `## 适用边界与失效条件`: 反例与注意点全部收敛于此
- `## 来源与验证证据`: `bank_id` + `doc_id` + 脱敏后的实测事实

## Step 3: 检索去重、条件写入与读回校验 (`silverbullet-kb`)

仅当 Step 2 产出至少 1 条合格候选时才访问 SilverBullet：

1. **探测实时标签与类型库存**: 通过 SLIQ 查询 `Knowledge/` 下的现有页面与 `tags` (`sb query 'from p = index.pages() where p.name:startsWith("Knowledge/") select p.name, p.tags, p.lastModified' --json`)，若 Runtime 不可用则按 `skill/references/search.md` 退回有界 `sb fs ls Knowledge --recursive --glob '*.md' --json` + `sb fs read`。优先复用已存在的 `topic/` 拼写；若候选似乎需要未在实时索引出现的新 `type/`，不得自行发明，跳过该候选并在汇报中记为 `needs_type_confirmation`。
2. **逐条检索去重**: 对每条候选先用 `silverbullet-kb` 检索 `Knowledge/` (Silversearch 词法召回 + SLIQ 精确标签过滤，遵守单次受控放宽规则；必须先 `sb fs read` 读完候选页面正文再做判断)。
3. **命中已有主题 -> 追加式合并 (`--if-match`)**:
   - 先执行 `sb fs stat '<path>' --json` 取得精确带引号的 opaque revision，并用 `sb fs read '<path>'` 读取最新全文。
   - 仅做追加式合并: 在对应章节补充新触发场景、命令模式、适用边界或验证来源，保留全部无关 frontmatter 键与人类已写内容；严禁整页重写、严禁删除或改写人类精修文字、严禁改路径。
   - 将合并后的内容写入临时文件，执行 `sb fs write '<path>' --if-match '<exact-quoted-revision>' --file <tmp>`。
   - 若返回 exit 5 (revision conflict) 或重读后的页面结构不支持无歧义追加，立即中止该页写入并记录 `revision_conflict`，继续处理其余候选；严禁盲目重试，严禁使用 `--overwrite`。
   - 写入成功后立即执行 `sb fs read '<path>'` 与 `sb fs stat '<path>' --json` 核验路径、首个 H1、tags 与新 revision。
4. **全新主题 -> 创建新页 (`--create`)**:
   - 生成扁平路径 `Knowledge/<kebab-slug>--<4hex>.md`，将符合契约的完整页面写入临时文件，执行 `sb fs write '<path>' --create --file <tmp>`。
   - 若 `--create` 报告路径冲突，更换新的 4 位十六进制短后缀重试 `--create` (基于路径的碰撞循环；绝不使用 `--overwrite`)。
   - 写入成功后立即执行 `sb fs read '<path>'` 与 `sb fs stat '<path>' --json` 核验路径、首个 H1、tags 与 revision。
5. 若 SilverBullet 不可达或返回运行故障 (如 exit 4/8)，中止剩余写入并标记本轮存在致命运行错误，不得推进水位。

## Step 4: 推进水位与事后汇报

1. **条件推进水位**: 仅当 Step 1-3 全流程完成且未发生致命/瞬态运行错误 (含 `NO_OP` 正常完成，以及单页 `revision_conflict` / `needs_type_confirmation` 已按契约跳过并纳入汇报) 时，执行原子单调水位推进：

```bash
python3 "$SCRIPT_PATH" --advance \
  --bot-name "<bot-name>" \
  --state-file "memory/hindsight-watermark.json" \
  --pending-file "memory/pending-watermark.json"
```

若本轮因 Hindsight 抓取失败或 SilverBullet 服务故障中止，严禁执行 `--advance`，确保下次运行自动重试。

2. **事后汇报 (Human-on-the-loop)**:
   - **有变更、冲突、待确认类型或错误时**: 向聊天输出简明事后 diff 汇报，逐项包含：
     - 动作 (`created` / `merged` / `revision_conflict` / `needs_type_confirmation` / `error`)
     - 标题 (`H1`) 与路径 (`Knowledge/...`)
     - revision (新建为新 revision；合并为 `old_rev -> new_rev`)
     - 1 句话核心摘要 (合并项附 1-3 条简明追加 diff 要点；冲突/错误项附原因)
     - 末尾一行附本轮统计 (`banks_scanned`、`docs_fetched`、`remaining_docs_capped`、水位推进状态)
   - **纯 `NO_OP` 时** (0 新建、0 合并、0 冲突、0 待确认类型、0 错误):
     - 定时自动化运行: 保持静默 (`[NO_REPLY]`)，不向主人发噪音消息。
     - 主人在对话中手动触发: 回复单行 `NO_OP` 摘要 (扫描 bank 数、检查文档数、通过四门控数 = 0、水位已推进状态)。
