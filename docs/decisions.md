# 设计决议

本日志只追加，不改写历史条目；推翻旧决策时新增一条记录并说明理由。

## v0 (2026-10-07, 仓库骨架)

1. **仓库职责**：只维护面向 agent 的 SilverBullet 知识库 Skill 与其评测，不维护 SilverBullet 服务部署。
2. **用户模型**：个人使用，云端 SilverBullet 是事实存储；agent 通过官方 `sb` CLI、Runtime API 和 Silversearch 读写与检索。
3. **结构策略**：笔记目录和元数据约定暂不固定，Skill 应依赖可发现的页面、标签和正文检索能力，而不是预设一套不可变目录。
4. **维护形态**：沿用 `feynman-lecture` 的最小结构：根 README、Skill 入口、追加式决策日志和独立评测目录。
5. **当前范围**：本次只建立仓库和占位文件；Skill 的触发、工具协议、查询封装、写入并发策略和评测用例留到下一阶段设计。

## v1 (2026-10-09, agent-native workflow)

1. **消费者**：Skill 面向 agent；API 返回必须被解释为 `status + evidence + next`，空结果、索引不可用和命令失败不能混为一谈。
2. **检索边界**：默认只检索顶层扁平 `Knowledge/`；Silversearch 负责全文召回，SLIQ 负责严格标签/元数据过滤，Runtime 或插件不可用时退回有界 `fs` 扫描。
3. **写入动作**：显式 `capture` 只创建新页面并使用 `--create`；显式 `update` 读取 revision 后使用 `--if-match`，冲突时重读而不是覆盖。
4. **元数据**：文档保留首个 H1，写入一个 `source`、一个 `type` 和一至三个 `topic` 标签；source 取项目名并回退到 `unknown`，type 初始支持 `experience`/`research` 且允许用户声明扩展。
5. **验证**：Skill 以 RED/GREEN/REFACTOR eval 验证完整链路，覆盖真实 SilverBullet 返回形状和 Agent 下一步选择。
