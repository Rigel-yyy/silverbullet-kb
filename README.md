# silverbullet-kb

一个面向个人 SilverBullet 知识库的 agent skill 仓库。目标是让 agent 能稳定地写入、读取、结构化查询和全文检索个人 Markdown 知识，同时把 API 反馈转换成下一步动作。

当前仓库只完成维护骨架；Skill 的触发条件、读写协议、查询封装和评测标准将在后续设计阶段确定。

## 仓库结构

- `skill/SKILL.md`: Skill 入口，包含 inspect、capture、search、update 和结果解释协议。
- `skill/references/`: SilverBullet CLI、检索路由、文档和标签契约。
- `skill/evals/evals.json`: RED/GREEN 行为评测集；`baseline.md` 保存无 skill 时的压力行为。
- `docs/decisions.md`: 只追加的设计决策日志。

## 设计边界

SilverBullet 是 Markdown 文件的云端知识库；本仓库维护 agent 使用它的工作流，不维护 SilverBullet 服务本身。正式知识文档默认存放在 Space 顶层的扁平 `Knowledge/` 目录，系统内容不进入默认检索。

## 集成契约（dotfiles 委托接口）

本仓库是 dotfiles 的 delegated second-party，部署走两动词线协议（dotfiles ADR 0009/0010）：

- `python3 install.py verify` — 只读探测。0 = 双链接收敛；10 = 可调和（链接缺失，install 可建）；20 = 冲突（链接路径被他属内容占用或指向别处，需人工移除）。原因写 stderr。
- `python3 install.py install` — 建链并以 verify 复验收尾。0 = 收敛；20 = 冲突 fail-closed（零 mutation）；1 = 环境错误；2 = 用法错误。幂等，可重复执行。
- 目标：`~/.claude/skills/silverbullet-kb` 与 `~/.agents/skills/silverbullet-kb` 两个 symlink，均指向本 checkout 的 `skill/`——checkout 内的文本编辑对两个 harness 即时生效，无需重装。Windows 上 symlink 需要开发者模式或管理员权限，失败时报错退出（1），不降级为 copy。

## 状态

Skill 已完成 day-one 实现，仍需在目标运行时安装并通过实际调用持续补充 eval。使用时先加载 `skill/SKILL.md`，再按操作读取对应 reference。
