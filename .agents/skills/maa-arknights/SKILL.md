---
name: maa-arknights
description: 在 Windows 的指定 MuMu 实例中准备、监督和核验官服明日方舟 ADB 日常。用于显式授权战斗、公招、基建、信用与领奖；保护当日账本并核验真实 guest 画面。
---

# 明日方舟日常

以本文件向上三级的目录为仓库根目录，保留完整仓库。先读 [运行说明](../../../docs/RUNBOOK.md) 与 [恢复说明](../../../docs/RECOVERY.md)。只在当前游戏和阶段已获授权时执行。

默认只走 MuMu；先读 [MuMu 路由与固定清单](../../../docs/MUMU-DAILY.md) 和 [证据命令](../../../docs/MUMU-EVIDENCE.md)。用 `python scripts/mumu_daily.py plan --game arknights` 及 `status` 检查计划、同账号旧账和当前状态。此入口不接管游戏输入，也不会替代受限 MAA 任务的现有门禁。

## 固定流程

1. 从仓库根运行 python scripts/daily_pipeline.py status、python scripts/daily_audit.py。北京时间 04:00 切日。核对旧工作副本与本副本账本；不能用新目录避开当天已执行记录。
2. 配置缺失时按 [README](../../../README.md) 初始化。下载只用 scripts/bootstrap.py 的 arknights 固定官方 release。默认预览，执行需显式 --execute；不覆盖原安装。
3. 准备启动用 python scripts/prepare_game.py --game arknights，获授权后加 --execute。核对官方服、MuMu 实例和 loopback ADB serial；检查真实进程、登录与当前画面。
4. TL-9 已关闭。没有用户新增的精确关卡授权、适配和当前可代理证据时跳过战斗，不运行曾指定 TL-9 的基础战斗命令，不耗理智；非战斗阶段独立核验。不自动换关。
5. 公招、全部基建、信用购买、领奖只用 scripts/ark_operations_v2.py。先无参数预览，再 --execute --home-reviewed --home-evidence <五分钟内主页PNG>。不串联旧 operations、accelerated 或补打脚本。
6. 按任务/配置/版本、taskid+uuid 完整回调、SHA 和 worker 状态核验。随后看实际奖励页，诚实记录资源前后值及未完成项；PNG 格式或回调完成不等于视觉验收。
7. 全部要求通过后用 scripts/finish-game.ps1 预览并关闭精确对应游戏/MAA，验证进程消失。仅在另有授权且无其他游戏/下载时处理模拟器。

## 资源范围

- 禁止源石、付费货币、理智药、抽卡和额外循环。
- 公招允许刷新及加急；保护高级资深、资深、支援机械，force_refresh=false。
- times=4 是新招募上限，不是四张加急许可硬上限。v6.22.0 忽略 expedite_times；无外部并发招募时最多原有四槽加新四次。实际消耗需从资源差值确认。
- Normal 全设施换班收菜；无人机只加速 Money 贸易站；不补货、不加工/训练/更换助手、不赠送/交换线索。
- 信用优先招聘许可，排除碳、家具、加急许可，不越过黑名单强制购买。

## 中断

--status 只读。--resume <summary> 只接受当天绑定、已验证完成前缀后的纯 planned 后缀，同时要求 --execute 和新鲜主页证据。submitting/running/unknown、哈希变化或已存在执行产物一律停止，不删账解锁。STOP/超时只停止本次受控 worker，不泛杀 Python。

不得为了测试技能启动游戏。v2 的防重与审计有离线测试，也有监督锁屏 ADB 会话中完成非战斗阶段的实测；不代表下次冷启、战斗或三游戏无人值守全链均已验收。

锁屏时按 RUNBOOK 的“锁屏与分游戏就绪检查”执行：只用精确实例 ADB guest 证据，主页与阶段审核通过后才做日常。冷启动成功或标题画面不算就绪；不因宿主锁屏停止已可用的 ADB 路径，但不绕过任何其他门槛。不自动回退原生 PC，也不把其他游戏同样视为锁屏可用。
