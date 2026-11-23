---
name: maa-gf2
description: 监督和核验少女前线 2 的 MuMu 日常、免费项与最高可扫荡突破材料。区分官服 Android ADB 和显式旧 Win32 路径；版本不符或状态不明时停止。
---

# 少女前线 2 日常

以本文件向上三级为仓库根目录。先读 [运行说明](../../../docs/RUNBOOK.md)、[恢复说明](../../../docs/RECOVERY.md) 与 [验证边界](../../../docs/VALIDATION.md)。保留完整仓库，授权不扩展到额外消费。

## 默认：MuMu 官服 ADB

先读 [MuMu 路由与固定清单](../../../docs/MUMU-DAILY.md) 和 [证据命令](../../../docs/MUMU-EVIDENCE.md)。使用预先核验的专用 MuMu 实例、精确 loopback serial、官服 `com.Sunborn.SnqxExilium` 和受监督 MaaGF2Exilium v2.8.6 ADB；比对相同账号、登录主页、实时客端画面，禁止并发。先 `python scripts/mumu_daily.py plan --game gf2` 及 `status`；该账本不点击。不复用 Win32 HWND、桌面坐标或旧 PC 资源。没有实际确认的可扫荡状态不批量消耗；老票据、活跃度或绿勾不能泛化为所有新项已完成。

按固定清单独立核对基础/真实领奖、最高可扫荡突破、烹调/茶/已栽花、精确免费日箱与周周乐周箱、班组要务与每日供给及要务补给·一、原队派遣与周档、委托→调度的储存情报拼图与生产收取、指定活动及已授权签到。未见额度或回执，不点击、不重派。已经监督实测 Android 输入，不声称 Windows 锁屏或无人值守；MuMu 阻塞不自动回退 PC。

## PC 旧路径：仅明确选择

### 版本边界

gf2_safe.py、gf2_supplemental.py、gf2_breakthrough.py 固定 MaaGF2Exilium v2.8.4。遇到 v2.8.6 等其他版本时，旧适配器必须拒绝执行。不能删版本保护、改 VERSION 或把旧版本成功当作新版本适配。固定旧 release 下载只建独立目录，不降级覆盖现有安装。

喝茶没有可复用的已验收自动入口；补充计划明确禁用喝茶。扫荡加号识别/数量选择仍有监督边界，breakthrough entry 不选择最高关卡。不要把这些缺口表述为无人值守完成。

### 旧 PC 固定流程

1. 只读检查 scripts/daily_pipeline.py status 和 scripts/daily_audit.py，核对当天基础/supplemental/breakthrough 三份 attempt；北京时间 04:00 切日。同日不要在两个工作副本执行。
2. 依 [README](../../../README.md) 准备配置和软件；python scripts/prepare_game.py --game gf2 --transport pc 预览，明确授权后才加 --execute。核对真实游戏进程、窗口句柄、1280×720 客户区和登录画面，用户处理登录/UAC。
3. 只有确为受审 v2.8.4 时，使用该 release 自带 python/python.exe 运行三个脚本的预览。实际执行需 --transport pc --execute --hwnd <新鲜句柄> --screen-reviewed --screen-evidence <五分钟内当前PNG>。
4. gf2_safe.py 负责基础日常；官方 agent 必须绑定 resource 并注册 scroll_end，base+resource_pc 均加载完成。
5. gf2_supplemental.py 仅免费烹调与已有花浇水等限定入口。没有花则返回，不播种/拔除/换种。喝茶由监督者核实免费次数后独立处理和记录。
6. 先现场确认最高已解锁可扫荡人形突破关卡并打开准备页，再使用 gf2_breakthrough.py。只用自然/升级赠体力；数量、奖励和体力变化都需确认。识别失败立即停止，不调用历史坐标脚本。
7. 检查所有要求、活跃目标和实际每日奖励；记录各项证据。返回 3 仅表示自动部分结束、等待验收，不能宣称全部完成。
8. 所有要求有证据后才用 scripts/finish-game.ps1 -Game gf2 -Transport pc 关闭精确对应游戏和 MAA，核验进程消失。

## 限制和恢复

禁体力药/付费补充/抽卡/拆解/不确定奖励箱和未授权购物。锁、STOP、失败回执和截图保留；已有 attempt、版本变化、未注册代理、错误 HWND 或未知结果均阻止继续。

不通过删除 ledger、整体重跑 daily 或修改成功标记补救。维护代码只运行离线测试；本技能不声称 v2.8.6 或喝茶全自动适配已经完成。

### v2.8.6 既有 PC 监督入口

先读 [商城、班组、调度室与本期活动](../../../docs/GF2-SUPERVISED-DAILY.md)。使用 scripts/gf2_daily_free_gift.py、gf2_squad_daily.py、gf2_dispatch_daily.py、gf2_heatdeath_supply.py，默认仅计划；--execute 拒绝，没有自动点击后端。每日先读 scripts/gf2_daily_additions_audit.py，分日/阶段/周档防重。

免费箱提交后可能切到同坐标收费礼包，禁止重试/双击/按卡位点击。班组补给与要务独立，禁尘烟前线及社交操作。调度只原队再次派遣，逐档核验本周派遣收益，该旧派遣入口本身不处理情报储备/资源生产；MuMu 的独立调度检查不能借用它的派遣记录。活动只本期热寂悖论物资模式 DF-1-5、当前专用准入密钥；战斗截止不能用兑换截止替代。上述画面语义均需监督审核，历史人工完成不是新入口自动化验收。
