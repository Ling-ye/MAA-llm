# 终末地：谷地三仓的监督转交

这里保留既有监督账本及报价规则，不是 MuMu 的自动输入入口。默认 MuMu 按 [固定清单](MUMU-DAILY.md) 和 [MuMu 证据命令](MUMU-EVIDENCE.md) 独立核验。


endfield_valley_transfer.py 管理源石研究园、矿脉源区、供能高地的独立计划、预约、防重与证据审计。**没有游戏输入或 MaaEnd 任务后端，--execute 一律拒绝。** 人工完成不等于脚本实机验收；不会再次发单、跑图或认领尾款。

从仓库根目录运行：

~~~powershell
python scripts/endfield_valley_transfer.py
python scripts/endfield_valley_transfer.py --status
python scripts/endfield_valley_transfer.py --node OriginLodespring --status
~~~

节点参数为 OriginiumSciencePark、OriginLodespring、PowerPlateau。现有 endfield_extras.py 的这三个谷地 delivery 执行分支已停止自动提交，旧计划保留用于审阅；物资调度 AutoSell/AutoStockpile、武陵、派遣和信用策略不变。

## 先辨认订单，再操作

审核 JSON 必须绑定当前区域、节点名称、可辨识的 order_reference 与实际页面；order_reference 是监督者记录的可复核订单标识，不冒称游戏服务端 ID。空账本不证明未操作，换目录不能避开旧记录。北京时间 04:00 切日。

材料必须通过物料格悬停确认名称，并把数量、该物料库存、单件体积和本仓容量绑定到同一订单；数量最多6000、容量最多100000，必须恰好装满。支持的名称仅为已审阅的精选养愈胶囊、蓝铁装备原件，不自动选材。合成模板见 config.example/endfield-valley-review.json，不能直接执行占位审核。

新装箱前 stock_basis=available_before_packing，库存须够用。已有报价用 remaining_after_packing，明确已经装箱的数量；不能将剩余库存再扣一次。没有当前库存或悬停证据就停止，不伪填字段。

## 分阶段监督命令

1. 没有报价且准备装箱：审核状态 ready_to_pack，明确“下一步”会生成报价。先 --reserve --review <当前审核.json> --base <MaaEnd目录> --game-exe <实际Endfield.exe> 落账，再由监督者在当前游戏页面操作一次。下一步绝不是无副作用预览。
2. 人工得到报价后，用 --record-quote --review <报价审核.json>。它要求节点、订单和材料不变、库存差额准确，并记录 quoted_unpublished。部分装箱、库存不符或断线不能重试。
3. 已有“有人报价/查看报价”的订单直接复用；须悬停复核实际货物并进入明确报价页面。首次对已有报价用 --reserve；从步骤2接续则用 --reserve-transfer。后者须新的报价画面与审核，不能重新装箱。
4. 预约会只读核验前台 HWND/PID、可执行路径、1280×720 客户区及 MaaEnd v3.1.0 安装版本，要求五分钟内截图和审核。它不会操作按钮，也不会加载 SDK 或访问游戏 API。监督者最后再次确认白色“快速转交”和当前订单，只操作明确的转交/转交委托确认；黄色“开始运送”、接单和导航全部禁止。
5. 在“我转交的委托”找到同一节点/订单的“已发布＋等待接单中”，用 --verify --review <发布审核.json>。保留实际到期提示；定金单独记录并绑定奖励图，尾款必须为未到账。没有最终页面证据不能认证。

每个写入命令须带 --node。准备、报价、转交预约和最终观察分别记状态；同日每节点独占账本，记录全过程，不能倒序、删账、重复提交或换节点复用证据。

## 已发布、低库存与中断

- 已经人工发布的订单：--observe --review <发布审核.json>。它只登记当前已发布待接单的事实，不要求虚构历史装箱前库存，也不声称执行过装箱。无法证明的历史材料数量只作为外部报告背景，不算本入口的核验字段。
- 低库存、部分装入或订单未知：--observe-blocked --review <现场审核.json>，保留 low_stock / partially_packed / unknown 与原因；不报告完成，不换材料填满。
- 预约后结果不明：--mark-unknown --reason <原因>。原订单、最近画面与阶段完整保留，不能恢复为可再次提交。查明后另存人工报告，不覆盖失败。
- 已有同日旧 delivery 节点/区域账或旧临时回执阻止新预约；不会改写原回执，也不会把旧失败自动迁成成功。

status 为只读哈希审计，不是实时画面检查。新增监督账本独立于旧 daily_audit；旧综合审计未接纳它时会保持未通过，不能伪造原生成功来绕过关闭门禁。操作前后须同时查旧账和本入口。

尾款后续仍按独立流程检查“已完成可领取”，待接单、待送达和定金不能写成尾款已到账。本入口没有尾款领取功能。截图可能含账号与他人昵称，只保存在本机，不提交 Git。

## 验证范围

离线测试覆盖已有报价不重装、下一步先预约、低库存、部分状态、材料/库存失配、窗口切换、同日防重、未知提交和待接单不等于到账。人工审核字段与文件哈希不能代替可靠视觉识别；新的脚本入口尚未完成实机自动执行验收，也未提供自动点击实现。
