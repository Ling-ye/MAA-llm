---
name: maa-arknights
description: 在 Windows 上准备、执行、核验或恢复明日方舟 MAA 日常。用于自然理智 TL-9、受限公招、基建、信用购买和领奖；优先使用本仓库脚本、当天账本和真实画面证据。
---

# 明日方舟日常

以本文件向上三级的目录为仓库根目录，保留完整仓库。先读 [运行说明](../../../docs/RUNBOOK.md) 与 [恢复说明](../../../docs/RECOVERY.md)。只在当前游戏和阶段已获授权时执行。

## 固定流程

1. 从仓库根运行 python scripts/daily_pipeline.py status、python scripts/daily_audit.py。北京时间 04:00 切日。核对旧工作副本与本副本账本；不能用新目录避开当天已执行记录。
2. 配置缺失时按 [README](../../../README.md) 初始化。下载只用 scripts/bootstrap.py 的 arknights 固定官方 release。默认预览，执行需显式 --execute；不覆盖原安装。
3. 准备启动用 python scripts/prepare_game.py --game arknights，获授权后加 --execute。核对官方服、MuMu 实例和 loopback ADB serial；检查真实进程、登录与当前画面。
4. 每次验证 TL-9 当期开放且可代理，保存五分钟内 PNG，再运行 scripts/runner.py --execute --stage-reviewed --stage-evidence <PNG>。不擅自换关；只使用自然理智。
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

不得为了测试技能启动游戏。该 v2 状态机和移植仅离线验证；不宣称三游戏全链路无人值守成功。
