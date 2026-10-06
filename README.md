# silverbullet-kb

一个面向个人 SilverBullet 知识库的 agent skill 仓库。目标是让 agent 能稳定地写入、读取、结构化查询和全文检索个人 Markdown 知识，而不把笔记目录结构提前焊死。

当前仓库只完成维护骨架；Skill 的触发条件、读写协议、查询封装和评测标准将在后续设计阶段确定。

## 仓库结构

- `skill/SKILL.md`: Skill 入口，目前是明确标记的 draft 占位。
- `skill/evals/evals.json`: Skill 评测集，占位为空，待行为设计后补齐。
- `docs/decisions.md`: 只追加的设计决策日志。

## 设计边界

SilverBullet 是 Markdown 文件的云端知识库；本仓库维护 agent 使用它的工作流，不维护 SilverBullet 服务本身，也不规定永久的笔记目录结构。

## 状态

Skill 设计尚未开始。不要把当前 draft 当作可直接安装的生产 Skill。
