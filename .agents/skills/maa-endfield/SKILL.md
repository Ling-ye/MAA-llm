---
name: maa-endfield
description: 监督和审计明日方舟终末地 MuMu 日常与显式旧 PC 路径。区分核心、环境监测、物资调度、礼物、转交尾款、信用购物和回收的真实证据。
---

# 终末地日常

以本文件向上三级为仓库根目录，保留完整仓库。先读 [运行说明](../../../docs/RUNBOOK.md)、[恢复说明](../../../docs/RECOVERY.md) 和 [验证边界](../../../docs/VALIDATION.md)。

## 默认：MuMu 官服 Android

先读 [MuMu 路由与固定清单](../../../docs/MUMU-DAILY.md) 和 [证据命令](../../../docs/MUMU-EVIDENCE.md)。用专用实例与精确 loopback serial，核对官方游戏包、渠道、相同账号和新鲜 guest 主页。安装、标题与官方协议界面均不证明已登入或日常适配。现未验收完整 Android 游戏日常、真锁屏或无人值守；版本不合、未登录或证据欠缺就停，不回退 PC 或搬用 Win32 入口。

先 `python scripts/mumu_daily.py plan --game endfield` 及 `status`；工具只管理证据和账本不操作游戏。核心/单倍领奖、两处监测、两区卖/弹性买、谷地 -80% 礼物、装箱快速转交、先查两区旧尾款、信用领取/购物/按规则刷新、两区远程回收均分开验收。已有报价先看状态，待接单、定金和尾款不混算，不盲装重试。

## PC 旧路径：仅明确选择

### 启动与前提

1. 只读检查 scripts/daily_pipeline.py status、scripts/daily_audit.py 与 core/regional/stock 独立 attempt；北京时间 04:00 切日。同日不能换空工作副本重放。
2. 按 [README](../../../README.md) 预览固定 MaaEnd v3.1.0 release 下载/初始化；MaaFramework 必须为 v5.16.1，关键资源哈希变化即停，不能盲更新安全基线。
3. python scripts/prepare_game.py --game endfield --transport pc 默认预览，授权后加 --execute。通过官方启动器启动游戏，不直接运行 Endfield.exe。
4. UAC 请求不等于启动成功。用户处理安全桌面后，核对真实 MaaEnd/游戏进程、可执行路径、权限和画面。不得代点 UAC、改系统安全/显示/网络设置或干扰其他程序。
5. 本仓库不保证启动器在所有环境正常工作。遇到白屏时记录阻塞并核对进程；没有登录主页证据不得继续，不擅自更改系统设置排障。
6. 实际客户端须为 1280×720 窗口；使用新鲜 HWND 和唯一 dot-safe- 前缀 runtime 调用 scripts/endfield_bootstrap.py。bootstrap 只连接已运行程序；connected/resource_loaded 仍须人工核验登录主页。

### 分阶段执行

- scripts/endfield_safe.py --phase daily：先预览，再显式 --transport pc --execute；目标库存保留受审数值，单倍领取，无体力药/双倍许可，不升级或合成来凑活跃。
- scripts/endfield_regional.py --phase environment-monitoring：独立 attempt，查看实际路线结果，部分路线完成不能算全成功。
- scripts/endfield_stock.py --phase sell 和 --phase buy：分别预览/执行/验收，使用 AutoSell / AutoStockpile 的两地区弹性物资策略。
- 物资调度仍只用 AutoSell/AutoStockpile，阈值不变。仓储阶段经当前操作者授权后独立处理：谷地三仓用 endfield_valley_transfer.py 监督账本，武陵沿用 endfield_extras.py；禁止把它充作物资调度。仅谷地精确 -80% 礼物允许独立购物，其他稳定购买、据点交易、UID/数据上传及基质销毁保持禁止。
- 动态购买没有独立验证的硬支出上限；检查实际数量和调度券。额度耗尽时记录 no-op，不反复执行购买。
- 核心奖励、环境监测、卖、买各自有真实证据；100 活跃和 coordinator closed 不能替代它们。

禁止源石/付费货币、体力药、双倍许可、抽卡、拆解、废弃基质及未授权资源操作。

### 新增每日范围

先读 [新增任务操作与边界](../../../docs/ENDFIELD-EXTRAS.md)，运行 scripts/endfield_extras.py --status。每日先检查两区已完成转交尾款，再逐商品购买谷地 7 种精确 -80% 礼物、逐节点装箱转交、两区远程回收；信用先领取，再优先嵌晶玉/武库配额，单次刷新后重新审阅货架。
只用新增入口；旧 regional delivery 入口不用于该流程。每次 --transport pc --execute 需五分钟内画面和审核 JSON，默认预览。空账本不能覆盖旧目录同日历史。
信用黑名单/稳健刷新/刷新耗尽任意购买分支均禁用；每天最多 2000 信用、4 次刷新共 560，每次只处理一个目标或一次刷新。信用购买/刷新和新封装尚未实机验收，保持监督，不说已全自动验证。
每商品/节点/地区/货架有独立防重账。回调成功后仍需 --verify；无可处理项用 --observe 留真实证据。原生填满与礼物数量上限依赖逐项画面审核，不宣称独立 OCR 硬计数。
转交仅代表委托已发出，待接单/待送达不是尾款已到账；以后每日先领取已完成尾款。该入口不支持自动导航送货，禁止自动导航/接单回退和盲重试。
统一审计从 2026-11-19 游戏日起要求新增 18 个范围及全部信用中间步骤。已有同日旧回执必须阻断重跑，保留原始失败和人工恢复记录。

### 中断与收尾

提交超时或回执不明时停止本 runtime、保留 attempt，不重复 tasks/start。原有严格限定的 pretrade parse recovery 只在全部原始证据证明尚未交易时可用，不能泛化为重试开关。详情读恢复说明。

全部所需阶段完成并有奖励证据后，使用 scripts/endfield_close.py 的原生 CloseGamePC，核验游戏进程消失，再用 scripts/finish-game.ps1 -Game endfield -Transport pc 关闭对应 MaaEnd。不得结束无关进程。

维护时仅运行离线测试。本仓库尚未验证从全关闭状态启动、三游戏全完成并退出的无人值守链路。

低库存/未知订单必须停下，保留仓库、订单标识及失败截图；地区尾款检查不等于全部订单到账，按 orders 记录待接单/待送达及到期提示。资源受限是 recorded_limited，不计全完成。

### 谷地三仓既有监督入口

[谷地三仓监督转交](../../../docs/ENDFIELD-VALLEY-TRANSFER.md) 替代旧谷地 delivery 自动提交，使用 scripts/endfield_valley_transfer.py。只提供计划、预约、记录与审计，没有游戏输入后端；--execute 拒绝。武陵与其他阶段不变。

下一步会生成报价，必须先预约；已有报价只复用，不重新装箱。材料悬停名称、数量、实际库存和仓容须绑定当前节点/订单。只白色快速转交，禁黄色开始运送及导航；已发布待接单与定金、尾款到账分开。低库存/部分装入/未知提交保存原状态，不重试，不伪造原生材料绑定或旧综合审计成功。
