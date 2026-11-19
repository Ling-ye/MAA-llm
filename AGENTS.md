# Repository instructions

默认执行离线工作。读取对应 .agents/skills/<游戏>/SKILL.md 和 docs/RUNBOOK.md 后再处理游戏任务。

- 修改源代码或测试不授权启动游戏。测试不得载入游戏 DLL、点击桌面、调用真实 ADB 或 MaaEnd API。
- python -m unittest discover -s tests -v 是回归入口；python scripts/check_repository.py 是提交前文件检查。
- 默认不使用 --execute。实际操作必须有该游戏、该阶段的授权及实时证据。
- 不删除/移动/清空运行账本来绕过防重复；不把回调成功标为视觉验收成功。
- 保留 unknown、partial、失败和 STOP，先确定受控进程及提交结果。禁止盲重试。
- 方舟仅 ark_operations_v2.py 做公招/基建/信用购买；runner.py 只负责基础日常和 TL-9。
- 少前 2 保持 v2.8.4 版本门禁；v2.8.6 必须独立适配和验证，不能只改版本号。
- 终末地物资调度是 AutoSell/AutoStockpile，不是 DeliveryJobs。不要启用未授权稳定购买或基质销毁；精确 -80% 谷地礼物按新增入口执行。
- 不提交 config.local、凭据、个人路径、运行记录、截图、下载二进制或游戏数据。
- 不改系统安全/显示/网络设置，不绕过 UAC，不结束无关进程。

- 终末地新增用 endfield_extras.py；转交必须由当前操作者授权，保留各节点防重与尾款待收语义。仅提供精确 -80% 谷地礼物的独立稳定物资购买范围，其余策略不变。
- 公开源码和技能不携带其他用户的执行授权。公开文档不得包含个人余额、真实订单、截图、账号或本机路径。

- 新增监督入口没有自动游戏输入后端；--execute 必须拒绝。谷地三仓旧 delivery 自动提交已禁用。新账本需独立审计，不能伪造原生成功补全旧审计。
