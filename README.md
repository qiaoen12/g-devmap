# DevMap

DevMap v1.2 是一个零代码开发地图 Skill。用户只需显式调用 /devmap；Skill 生成或复用结构化 Execution Plan，并由计划与实时状态投影 Task，结合实际文件变化、验证与仓库自动检查事实，生成面向负责人和非技术人员的简洁中文看板。开工前输出一张“负责人数据看板 + 四列 Task 地图”；开发过程中仅在 Task 完成、确认阻塞或重新打开时输出该 Task 地图；所有 Task 与最终 L3 验收完成、阻塞清零后输出计划与实际摘要。

DevMap 是独立 Skill，可由开发 Harness 显式调用；它不属于任何特定开发 Harness，也不开发代码、编排 Agent 或监督流程。产品由文本规则、三个模板和验收样例组成，不含运行代码、外部模型接口、仓库配置或自有持久状态。需要保存时，仅在用户明确指定路径后保存。

## Product files

- [devmap/SKILL.md](devmap/SKILL.md)：/devmap 唯一入口、Task 状态、事件触发、路径树 / 目录折叠、中文用户可见规则和统一测试摘要。
- [devmap/templates/prd.md](devmap/templates/prd.md)：可选的 Background + Execution 推荐示例；没有这些标题也能规划。
- [devmap/templates/execution-plan.md](devmap/templates/execution-plan.md)：`## Execution` 区块内部的静态计划结构，包括依据、方案、Task、全局验证和停止条件。
- [devmap/templates/map.md](devmap/templates/map.md)：开工总地图、最终总地图和三类 Task 事件地图的固定呈现模板。
- [devmap/fixtures/report-protocol.md](devmap/fixtures/report-protocol.md)：20 项原有地图验收、12 项 Execution Plan 验收、5 项来源识别与输出边界验收，以及五类地图的固定 Mock 实际渲染样例。

地图默认只显示负责人需要的信息。Plan Basis、Approach、Task 目的、具体改动、依赖和完整验证保留在专业规划数据中，不铺成用户可见明细表。小文件集合优先显示目录树；大文件集合按目录折叠，同时保留真实文件总数。

## 计划复用

已有可复用执行计划只以精确二级标题 `## Execution` 识别。该标题前面的内容是普通素材，不要求固定结构；没有 `## Background` 也可以复用。匹配则只核对与方案相关的当前 HEAD、文件、ownership 和验证入口，然后直接复用；小范围漂移只修正受影响 Task；核心前提失效才重规划相关部分。计划中的新增文件尚不存在不算漂移。没有 `## Execution` 时，从现有素材和当前仓库相关内容自行形成一次方案。

静态计划保存可交接的实施选择，Runtime 在当前上下文保存状态、实际文件、测试结果、阻塞与报告事件。换 Agent 或机器时提供完整计划或可访问引用，并重新核对现场与 Runtime 证据；不从计划推测完成进度。计划不会扩大任务来源已经给出的范围，发现新需求仅作为建议。地图默认只输出到当前 Harness 对话。保存仍须用户明确指定路径，不自动写 GitHub Issue comment 或 PR comment，不自动改写任务来源，不建立运行状态服务。
