# DevMap

DevMap v1.3 是一个开发地图 Skill：任何时候调用 /devmap，都输出一张当前快照，告诉负责人进展结论、需要处理的事项、各 Task 状态、实际改动与验证结果。输入可以是 Issue 号、PR 号、分支、一段文本或当前会话，也可在另一个窗口单独运行。

DevMap 只读：不开发、不编排 Agent、不写 Issue / PR 评论或任何远端，不改写任务来源；只有用户给出路径时才保存。证据不足时写“未知”并说明原因，不用 0 代替，不给主观百分比。

## 分工

- 确定性事实交给脚本：`devmap/scripts/devmap_facts.py`（仅 Python 标准库）计算实际改动（新增 / 修改 / 删除 / 重命名，含未提交与未跟踪文件）、计划与实际的四个集合、≤30 行折叠目录树，以及可选的 PR 自动检查计数。
- 模型只做判断：读取或生成计划基准（Task 名称、预计文件、验证项），判断 Task 状态、阻塞与结论。

## 文件

- [devmap/SKILL.md](devmap/SKILL.md)：/devmap 唯一入口、计划基准、facts 脚本用法、Task 状态与输出规则。
- [devmap/templates/map.md](devmap/templates/map.md)：唯一快照模板：结论、需要你处理、Task、改动、验证。
- [devmap/scripts/devmap_facts.py](devmap/scripts/devmap_facts.py)：facts 脚本，JSON 输出到 stdout，出错时退出码非 0 且不输出结果。
- [devmap/fixtures/report-protocol.md](devmap/fixtures/report-protocol.md)：8 个需要模型判断的验收场景。
- [tests/test_devmap_facts.py](tests/test_devmap_facts.py)：facts 脚本单元测试（计数、集合、目录折叠、git 口径）。

## 计划基准

来源中有精确标题 `## Execution` 时照原样读取，只取 Task 名称、预计文件、验证项；没有时自行生成这三样作为最小基准，不写完整方案。

## 验证

```
python3 -m unittest discover -s tests -v
```

仓库自动检查 `devmap-docs` 运行上述单元测试，并检查 SKILL.md（≤4,000 字符）与 map.md（≤2,000 字符）的篇幅上限。
