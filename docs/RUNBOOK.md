# 运行说明

## 通用准备

在仓库根目录运行命令。新机先按 README 初始化 config.local 并确认软件路径、固定版本、执行授权起始游戏日。不要把 ready/enabled 当作一次性跳过现场核验的开关。三款游戏串行执行；不要同时启动两个工作副本。

1. python scripts/daily_pipeline.py status 和 python scripts/daily_audit.py 只读现有记录。
2. 核对当前游戏日与独立阶段 attempt。存在失败、未知或进行中的 attempt 时读恢复说明，不重新执行。
3. python scripts/prepare_game.py --game <游戏> 预览；经授权加 --execute 才启动。
4. 查看真实进程、窗口、登录和最新画面。没有首页、界面白屏、UAC 未完成都停止。新鲜截图保存在 scripts/evidence/，不提交。
5. 每阶段串行执行、检查回调和实际结果、记录资源前后差异；全部要求完成后才清理。

默认目录：配置 config.local/，软件 tools/<game>/<version>/，运行脚本/状态根 scripts/。相对路径均从仓库根目录解释。Win32 HWND 必须现场重新获取并核对进程，不能复用历史数字。

## 明日方舟

固定 MAA v6.22.0、官方服、明确的本地 MuMu 实例和 loopback ADB serial。自然理智只刷 TL-9；每次检查当期开放和代理可用，不自动换关。

~~~powershell
python scripts/runner.py
python scripts/runner.py --execute --stage-reviewed --stage-evidence scripts/evidence/<已核验TL-9页面>.png
python scripts/ark_operations_v2.py
python scripts/ark_operations_v2.py --execute --home-reviewed --home-evidence scripts/evidence/<五分钟内主页>.png
~~~

启动模拟器需要另外添加 --launch-emulator。runner 仅做基础任务、TL-9、允许的好友访问和奖励；公招/换班/信用购物只使用 v2。禁止把旧 operations、accelerated、补打战斗拼成另一次日常。

v2 固定顺序：Recruit → Infrast(mode=0 全设施集合) → Mall → Award。
公招至多 4 次新招募、3/4 星九小时、标签刷新和加急开启；保护高级资深、资深和支援机械，force_refresh=false。v6.22.0 的 expedite_times 不能作为硬上限：在无外部并发招募的前提下，原有最多 4 槽加最多 4 次新招募，最多 8 次成功加急；实际消耗由资源前后值确认。

无人机只用于 Money 贸易站，不补货、不加工/训练/换助手、不交换或赠送线索。信用购物优先招聘许可，排除碳、家具、加急许可，不启用满信用强制购物。奖励任务不抽卡、不采矿、不领取源石相关奖励。

基础账本 state/arknights-<day>.json 与 operations attempt 分开保存。v2 记录全部 planned 阶段，先持久化 submitting/running，再启动受控 worker。成功必须同时满足 taskid、uuid、完整回调链、任务/配置/结果/事件哈希和 worker 收据。结尾 automation_completed_unverified 仍需实际奖励页验收。

## 少女前线 2

三个适配器共享锁，但分别有基础、supplemental、breakthrough 防重放账本。它们固定 v2.8.4；安装为 v2.8.6，则只允许预览/审阅，不能通过改 VERSION 或重新下载覆盖安装来“适配”。

实际执行使用该 release 的 python/python.exe，以下命令中的 python 应替换为它：

~~~powershell
python scripts/gf2_safe.py
python scripts/gf2_supplemental.py
python scripts/gf2_breakthrough.py
~~~

仅在版本相符、已获执行授权且当前画面审核通过时，添加：
--execute --hwnd <新鲜句柄> --screen-reviewed --screen-evidence scripts/evidence/<五分钟内当前页面>.png

- 基础：PrepareDailyTasks / PublicAreaDailyTasks / ClaimRewardTasks；官方 agent 必须成功注册 scroll_end 并加载 base+resource_pc。旧版领奖分支可能失败，失败后保留原回执。
- 补充：免费烹调及已有花浇水；没有花时返回，不播种、不拔除、不换种。**该补充脚本主动禁用喝茶支路**；喝茶仍由监督者检查当日免费次数并另行完成和记录，不能说脚本已经覆盖。
- 突破：监督者先确认最高已解锁、可扫荡的人形突破关卡，并打开扫荡准备页。现有 entry 不选择最高等级。只用自然/升级赠体力；加号/数量识别异常时停止，不用一次性固定坐标补救。
- 不用体力药、付费体力，不抽卡、不拆解、不打开不确定奖励箱。返回 3 表示自动任务结束、视觉验收仍待完成；不是全部日常成功。

每日烹调、喝茶、浇花和最高突破材料扫荡分别核验，记录活跃/每日目标、最终奖励页和实际体力变化。不要用活动值替代这些独立要求。

## 终末地

固定 MaaEnd v3.1.0、MaaFramework v5.16.1、游戏客户端 1280×720 窗口。使用官方启动器；不直接执行游戏 EXE。Windows 安全桌面只由用户确认，之后检查 MaaEnd 实际进程及 /system/is-elevated 结果。

已有白屏问题未解决时不进行后续步骤。默认 preview 不访问 MaaEnd API；实际运行前需确认资源哈希与受审基线相符。

~~~powershell
python scripts/endfield_bootstrap.py --instance dot-safe-<本日标识>
python scripts/endfield_bootstrap.py --instance dot-safe-<本日标识> --hwnd <新鲜句柄> --execute
python scripts/endfield_safe.py --phase daily --instance dot-safe-<本日标识>
python scripts/endfield_safe.py --phase daily --instance dot-safe-<本日标识> --execute
python scripts/endfield_regional.py --phase environment-monitoring --instance dot-safe-<本日标识> --execute
python scripts/endfield_stock.py --phase sell --instance dot-safe-<本日标识> --execute
python scripts/endfield_stock.py --phase buy --instance dot-safe-<本日标识> --execute
~~~

逐条执行并确认上一阶段已结束，不能把上述多条命令作为无监督批处理。
bootstrap 只为已经运行的程序建立隔离 runtime；connected/resource_loaded 不表示已登录。必须看 bootstrap 截图和当前主页后才执行 daily。

daily 包含好友访问、限定快速收菜、ProtocolSpace 目标库存和奖励。目标库存使用受审预设，见 policies/endfield-target-inventory-request.json 的 options.SupplyPlanLimits；该数值并非适合所有账号的建议，启用前应核对自己的库存与需求，修改策略时重新审阅完整性基线。单倍领取、无体力药/双倍许可；不为凑活跃升级武器/干员或合成。受审策略不继承用户 GUI 的任意其他任务。

环境监测与物资调度各自验收。AutoSell/AutoStockpile 只使用原先两地区弹性物资策略；禁上传数据/UID、非礼物稳定购买和据点交易。新增 DeliveryJobs 装箱转交另用 endfield_extras.py，不能满足“物资调度”。动态购买没有独立硬预算保证，执行前后必须检查数量和调度券。

验证核心 100 活跃奖励可调用：

~~~powershell
python scripts/endfield_safe.py --record-verification scripts/runs/<本次>/summary.json --evidence scripts/evidence/<实际奖励页>.png --activity 100
~~~

这个命令记录监督者的视觉确认，不读取截图语义；只有完整 daily 阶段安全结束且当天版本匹配的运行可写 success；rewards 单独阶段不能认证目标库存已完成。环境/出售/购买仍单独记录 verified 与证据。

## 人工验收字段与协调记录

原始任务回调、请求、结果及 SHA 绑定不可修改。监督者在实际观察后才向 summary 追加 verified、verified_at、verification_evidence（PNG path + sha256）和资源前后值；不删除失败字段来伪造通过。保留修改前副本在同一运行目录内。

覆盖审计读取明确的链接：
- state/daily-<day>.json 的 games.arknights.receipt 引用基础 summary，operations_receipt 引用 v2 summary。基础需要已完成 Fight 和 verified_at；v2 需要 verified=true、daily_reward_verified=true 及全部绑定证明。
- games.gf2.receipt 引用已验证的基础/每日总结，包含 day、verified、daily_reward_verified、daily_activity、daily_goal 与 PNG。supplemental attempt 还需 cooking_completed、tea_completed、watering_completed、partial_verified 和当日证据；games.gf2.breakthrough_receipt 或突破 attempt 必须绑定最高突破扫荡 summary，包含 verified=true、highest_sweepable_breakthrough_verified=true、natural_or_levelup_stamina_only=true 与实际 PNG，不能重复扫荡。
- games.endfield.receipt 引用 daily summary；regional_supplement.environment_monitoring / stock_sell / stock_buy 的 receipt 指向对应阶段 summary，包含正确 phase、automation_succeeded=true、verified=true 和 PNG。

daily_pipeline prepared 对方舟还须 --stage-reviewed --stage-evidence <TL-9图>，run 会传递对应的阶段/画面证据；prepared/run/collect/verified/closed 只管理基础串行生命周期，补充阶段由监督者调用并补充明确链接；它不是自动串联所有步骤的全自动入口。不要为了推进状态而把未观察的值填成 true。

## 收尾

~~~powershell
# 先预览并核对精确进程
powershell -NoProfile -File scripts/finish-game.ps1 -Game arknights -Receipt scripts/runs/<v2运行>/summary.json -Python <本机Python路径>
# 确认后加 -Execute；少前 2 使用 -Game gf2 与实际日常总结
~~~

终末地先经完整范围审计，再用 endfield_close.py --receipt <summary> --execute 提交原生关闭任务，确认 Endfield 进程已退出后，用 finish-game.ps1 -Game endfield 关闭对应 MaaEnd。

清理回执写在 scripts/cleanup-<game>.json，供协调器链接。全过程保持 partial/unknown 与实际未完成项；关闭动作不等于日常完成。模拟器不由这个脚本自动关闭。

新增礼物、仓储转交/尾款、信用与回收按 [ENDFIELD-EXTRAS.md](ENDFIELD-EXTRAS.md) 执行。2026-11-19 游戏日起统一审计纳入其独立账本；原物资调度阈值不变。

## 新增监督账本

少前2新增四组按 [监督入口](GF2-SUPERVISED-DAILY.md) 分别处理：每日免费补给箱、班组补给/要务、调度领取/原队重派/逐周档、本期活动专用密钥物资模式。v2.8.6 的新入口没有自动点击后端，旧 v2.8.4 版本保护和禁购项不变。

谷地三仓按 [监督转交](ENDFIELD-VALLEY-TRANSFER.md) 处理，旧 endfield_extras.py --phase delivery --region valleyiv 的自动提交已拒绝；已有报价复用，下一步先预约，待接单与尾款到账分开。武陵、物资调度及信用范围不变。收尾额外检查两个新增审计，不伪造旧综合审计成功。

## 锁屏与分游戏就绪检查

Windows 锁屏不作为明日方舟的统一否决条件。仅官方服 MuMu 的受审本地实例通过 ADB guest 通道操作，不依赖宿主截图、鼠标或键盘；不解锁 Windows、不改安全设置、不切换 SYSTEM/session 0、不绕过 UAC。保持固定版本和现有账本/互斥锁/阶段证据门槛。

- 冷启动命令返回 0 仅表示请求已接受，不是 Android 或游戏就绪。已有实例必须复用，启动后有界等待真实 Android 状态。
- 核对实例实际 ADB host/port 与配置的 loopback serial 完全一致，再检查 get-state=device、官方包存在、通过二进制 exec-out screencap -p 得到新鲜可解码 guest PNG。不得改选其他在线设备。
- 监督者须实际看到已登录主页；标题页、加载页、黑白屏、卡死、缺失/过期画面或身份不明都不能开始消费型日常。静态主页可能正常，不能仅因两个 PNG 哈希相同就断言卡死；结合加载进展、响应及观察时间判断，无法判断则停止。
- 锁屏时 TL-9 审核与 v2 主页证据也必须来自 guest；PNG 格式、窗口/进程存在或 MAA 回调不代替视觉验收。
- 少前 2 与终末地仍必须有可交互且确认未锁定的桌面；锁屏或桌面状态未知时拒绝启动前台任务，不尝试后台点击。

`scripts/session_readiness.py` 是无 I/O 的监督决策函数，调用方传入独立实时观察；不是系统探针，不会启动、点击、截图或自动验收，也没有替代现有执行入口的门禁。它按游戏返回缺少的条件，仅所有条件通过后才能继续原阶段审核。离线测试不证明锁屏下整套日常已实测成功。
