---
name: maa-gf2
description: 在 Windows 上准备、监督和核验少女前线 2 日常、免费烹调、喝茶、已有花浇水和最高可扫荡人形突破材料。使用固定版本适配器和独立防重放账本；版本不符或画面不明时停止。
---

# 少女前线 2 日常

以本文件向上三级为仓库根目录。先读 [运行说明](../../../docs/RUNBOOK.md)、[恢复说明](../../../docs/RECOVERY.md) 与 [验证边界](../../../docs/VALIDATION.md)。保留完整仓库，授权不扩展到额外消费。

## 版本边界

gf2_safe.py、gf2_supplemental.py、gf2_breakthrough.py 固定 MaaGF2Exilium v2.8.4。遇到 v2.8.6 等其他版本时，旧适配器必须拒绝执行。不能删版本保护、改 VERSION 或把旧版本成功当作新版本适配。固定旧 release 下载只建独立目录，不降级覆盖现有安装。

喝茶没有可复用的已验收自动入口；补充计划明确禁用喝茶。扫荡加号识别/数量选择仍有监督边界，breakthrough entry 不选择最高关卡。不要把这些缺口表述为无人值守完成。

## 固定流程

1. 只读检查 scripts/daily_pipeline.py status 和 scripts/daily_audit.py，核对当天基础/supplemental/breakthrough 三份 attempt；北京时间 04:00 切日。同日不要在两个工作副本执行。
2. 依 [README](../../../README.md) 准备配置和软件；python scripts/prepare_game.py --game gf2 预览，明确授权后才加 --execute。核对真实游戏进程、窗口句柄、1280×720 客户区和登录画面，用户处理登录/UAC。
3. 只有确为受审 v2.8.4 时，使用该 release 自带 python/python.exe 运行三个脚本的预览。实际执行需 --execute --hwnd <新鲜句柄> --screen-reviewed --screen-evidence <五分钟内当前PNG>。
4. gf2_safe.py 负责基础日常；官方 agent 必须绑定 resource 并注册 scroll_end，base+resource_pc 均加载完成。
5. gf2_supplemental.py 仅免费烹调与已有花浇水等限定入口。没有花则返回，不播种/拔除/换种。喝茶由监督者核实免费次数后独立处理和记录。
6. 先现场确认最高已解锁可扫荡人形突破关卡并打开准备页，再使用 gf2_breakthrough.py。只用自然/升级赠体力；数量、奖励和体力变化都需确认。识别失败立即停止，不调用历史坐标脚本。
7. 检查所有要求、活跃目标和实际每日奖励；记录各项证据。返回 3 仅表示自动部分结束、等待验收，不能宣称全部完成。
8. 所有要求有证据后才用 scripts/finish-game.ps1 -Game gf2 关闭精确对应游戏和 MAA，核验进程消失。

## 限制和恢复

禁体力药/付费补充/抽卡/拆解/不确定奖励箱和未授权购物。锁、STOP、失败回执和截图保留；已有 attempt、版本变化、未注册代理、错误 HWND 或未知结果均阻止继续。

不通过删除 ledger、整体重跑 daily 或修改成功标记补救。维护代码只运行离线测试；本技能不声称 v2.8.6 或喝茶全自动适配已经完成。
