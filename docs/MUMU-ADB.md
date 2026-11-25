# 前台依赖审计与 MuMu ADB

只适用于仓库的三款游戏；不会自动化任意 PC 应用。Windows 登录、系统提示、锁屏、解锁、权限与系统截屏不由 ADB 代办，也不绕过它们。下表区分整个真实游戏链路和这个工具能覆盖的部分。

| 路线 | 可走 guest ADB | 仍需原路径或未覆盖 |
| --- | --- | --- |
| 明日方舟 MuMu | 现有固定 MAA/ADB 的启动、截图、原生代理/非战斗与对应包收尾照常；新 probe 仅作可选只读诊断 | 不用新 helper 替换经过验证的 MAA/临时活动、版本、自然理智或账本限制 |
| 少前2 MuMu | 用已配置的官方包、专属 VM 的直接 ADB 抓帧、审核后单步点击/滑动；锁屏时用同一 guest 证据记录日常；日常与主线可走监督流程 | 没有批处理攻略、画面理解、自动启动/登录、自动确认弹窗或已验收锁屏收尾。动画导致全帧变化时默认拒绝；纯导航可以绑定同一可见控制的精确像素区域，不用于领取或消耗。若已验证私有 ADB 工具不符合新证据要求，不能冒充通过 |
| 少前2 PC 旧路线 | 不混用 | Win32Controller Foreground/Seize、HWND、宿主截图和旧键鼠工具仍仅显式 PC，未解锁时不运行 |
| 终末地当前 PC 路线 | 无；不会从 MuMu 去操控宿主 PC 游戏 | 鹰角启动器、账户、UAC、原生窗口 MaaEnd/Win32、PC 窗口操作和收尾仍由现有显式 PC 路线处理。Android 安装与可登录可运行不是一回事，旧渲染/角色与工作流仍须独立验收。本更新不改个人 PC 偏好或暂停 |

## 验证状态

实机已在正常 Windows 会话用该 CLI 取得少前2 Android 原始帧，并通过审核锚点打开只读详情、复抓画面确认无消耗。首轮全帧变化曾正确拒绝并未发输入。真实 Windows 锁屏尚不等于此实测：锁屏整链路、领取/消耗、自动登录或批量任务仍未做此版本的实机验收。

## 从仓库根目录使用

在本地 config.local/mumu-supervised.json 设 guest_tools.mumu_cli 和 guest_tools.adb_path（已核对的厂商 MuMu CLI、ADB 路径），每款独立配置 vm_index、确切 127.0.0.1 端口和 enabled。只复用已经在线的进程，不会隐式 adb connect/reconnect、启动、更改网络、用宿主鼠标，或尝试邻近端口。已安装的 ADB 不在线时，按已授权的原启动流程核实后再 probe；安全/登录提示先停。官方包名与实例、回环地址不同皆拒绝。

~~~powershell
python scripts/mumu_guest.py probe --game gf2
python scripts/mumu_guest.py tap --game gf2 --probe-proof <probe.json> --reviewed-frame --navigation --xy <原始X> <原始Y>
python scripts/mumu_guest.py swipe --game gf2 --probe-proof <probe.json> --reviewed-frame --navigation --xy <原始起X> <原始起Y> <原始止X> <原始止Y> <毫秒>
~~~

probe 按当前 foreground+focus、guest boot 和 PID 在抓帧前后都复核，解码 RGB/RGBA 原始 PNG，拒绝缺失/空白/遮挡或被替换的图片。正常静止帧不能仅凭相同哈希判冻结；必须实际审阅可用内容。证据文件是本机记录，不上传。输出 game_action_performed=false 不等于角色登录，实际主页/场景和当前授权仍由监督者确认。

reviewed-frame 由当前获授权的监督者或代理看图后传入，**不是要求用户每一步再审批**。坐标使用 proof 输出的原始 guest 像素，不使用 1280×720 缩放图或宿主 HWND 坐标。工具在一条手势前重新抓取相同全帧并核对实例/包/PID/boot，60 秒内同一 proof 只能尝试一次；发生转场、动画、重启或失焦时拿新图评估，禁止用旧坐标/盲点。--navigation 仅用于明确无资源消耗、无游戏结果提交的导航。日常有副作用的点击应改用 --item <已预约日常ID>，必须有当前精确预约，并仍遵守实际价格、次数、路线和单次提交限制。已知不使用 Windows 前台并不等于锁屏环境必然成功；游戏画面到手、动作送达、效果已验证、完整链路运行分别说明。

只对非消耗导航可给 probe 增加 --anchor <X1> <Y1> <X2> <Y2>，从当前全尺寸图选出包围确定交互控件的非空矩形。下一次 --navigation 手势起止点都须在这个矩形内；区域实际像素及实例/包/PID/boot 必须一致，区域之外允许变化。锚点无法辨别文字语义，须确认明确是地图详情/返回等不提交动作。不能用 --anchor 来购买、领奖、扫荡、开战或代替预约。每次发下一步前重新审阅上一动作效果；探测标记只防止重放同一帧，不能代替逐项防重复。

日常审核 JSON 的 probe_proof 绑定当前 mumu_guest 输出的 probe；screens.primary 必须与该 PNG、SHA 和 captured_at 完全相同。Windows 锁屏或未知时少前2必须提供这份证据；其他事实或奖励侧证仍按 MUMU-EVIDENCE.md 并由操作者核对同一 guest 与时序（这些附帧未自动证明同一连接）；不能靠按钮回调填成完成。

交互结果 input_sent_effect_unverified 只代表发送并拿到后帧。若 unknown_after_submission，先看新帧与原预约，保留结果未知，禁止重新发送。核对已完成的日常可正常 verify，不明可 mark-unknown；之后仅可用 mumu_guest.py acknowledge --game gf2 --probe-proof <新探测> --reviewed-frame --reason <事实> 解除全局停滞；原提交和已消费 probe 不可重新执行。不因更换目录、锁状态、截图或运行方式绕过。
