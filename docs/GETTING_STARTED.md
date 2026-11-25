# 开始使用

## 1. 确认适用范围

本项目面向 Windows 本机、MuMu 优先的监督工作流。需要 Python 3.12、PowerShell、Git；游戏及对应官方 Android 客户端由用户自行安装并完成登录。为各游戏配置独立的 MuMu 实例及精确 loopback ADB，串行运行。MuMu 阻塞就停止对应游戏；不要自动回退 PC。

| 游戏 | 上游版本与方式 | 验证范围 |
| --- | --- | --- |
| 明日方舟 | MAA v6.22.0 / MuMu ADB | 已有监督锁屏实测，后续必须逐次核验 |
| 少女前线 2 | MaaGF2Exilium v2.8.6 / 官服 MuMu ADB | ADB 监督路径，锁屏需证明当前 guest；旧 PC 为独立 v2.8.4 |
| 终末地 | MuMu 默认，MaaEnd v3.1.0 / Framework v5.16.1 的 Win32 为独立旧路径 | MuMu 目前仅能证明安装与启动，不证明登录后日常 |

这些是已审阅的固定版本，不是“当前最新版”推荐。不要将最新版资源混入固定版本目录。先查看 [验证边界](VALIDATION.md)。

## 2. 获取并检查源码

~~~powershell
git clone https://github.com/Ling-ye/MAA-llm.git
cd MAA-llm
python -m unittest discover -s tests -v
python scripts/check_repository.py
~~~

预览、下载器和测试使用标准库；requirements.txt 是依赖说明，不要求安装额外 pip 包。少前 2 的实际执行须使用它自己的运行环境，不能混装另一版 MaaFramework。

## 3. 初始化配置

~~~powershell
python scripts/bootstrap.py init
python scripts/bootstrap.py init --execute
~~~

第二条命令只创建 config.local/ 下缺失的 JSON，不启动游戏。模板来自 config.example/，已有设置保留。

config.local/runtime.json 中：

- installations.arknights / gf2 / endfield：已有上游安装目录；留空时使用仓库 tools/<game>/<固定版本>。
- paths.gf2_game：仅给明确选择了旧 PC 路径的人填写少前 2 游戏可执行文件。
- paths.endfield_launcher / endfield_game：仅给明确选择了旧 PC 路径的人填写终末地官方启动器与游戏可执行文件。
- execution.<游戏>.enabled：初始为 false。
- execution.<游戏>.not_before_game_day：允许开始的游戏日 YYYY-MM-DD。

`config.local/mumu-supervised.json` 要逐游戏核对并填写专用实例的 `vm_index`、`serial`，完成当前绑定审核后才将对应 `enabled` 设为 `true`。样例默认关闭，不包含可直接使用的设备地址。此开关不替代 `runtime.json` 的执行授权。

路径由你填写，可以使用相对仓库根目录的路径。明日方舟旧执行脚本还需在两个配置中填写 maa_dir、adb_path、mumu_cli、serial、vm_index；不要复制别人的 ADB serial 或进程信息。只有首页和配置已经核验时才能设置 ready=true。

## 4. 准备上游软件

可以指向已有的匹配版本，也可使用下载器。例如：

~~~powershell
python scripts/bootstrap.py download --game arknights
# 先审阅版本、URL、大小、SHA-256，再执行：
python scripts/bootstrap.py download --game arknights --execute
~~~

游戏标识为 arknights / gf2 / endfield。下载器从对应官方上游 GitHub release 获取固定资产，校验元数据与实际 SHA-256，检查 ZIP 路径、链接、设备名及解压量后安装到 tools/。不覆盖已有版本、不运行 EXE。

游戏客户端、模拟器、运行库和官方启动器请自行从各自官方渠道准备。本工具不提供账号、代理服务或第三方分发包，也不自动处理协议、登录、验证码、UAC。

## 5. 先预览，再逐阶段运行

~~~powershell
python scripts/mumu_daily.py plan --game arknights
python scripts/mumu_daily.py plan --game gf2
python scripts/mumu_daily.py plan --game endfield
python scripts/mumu_daily.py status --game gf2
~~~

初次使用没有记录，审计显示待检查属于正常状态；它不会自动把任务标成成功。运行开关仍保持关闭，直到你已核对旧目录记录、选择一个尚未执行的游戏日，并明确授权具体阶段。

需要执行时，仅启用相应游戏，设置真实起始游戏日，遵循 [MuMu 固定清单](MUMU-DAILY.md) 和 [证据命令](MUMU-EVIDENCE.md) 的版本、账号、主页、阶段、截图和账本门槛。既有 PC 命令另见 [RUNBOOK.md](RUNBOOK.md)，仅显式旧版兼容，不可当作 MuMu 回退。不要把多条命令合成无监督批处理。

技能位于 .agents/skills/。可让支持本地文件的助手读取对应 SKILL.md；助手的权限、模型配置和截图隐私由你单独管理。无需将配置或运行证据上传至此 GitHub 仓库。

## 6. 核验、恢复与关闭

每次只运行一个阶段。回调结束后检查实际奖励和资源差异，再记录真实证据。全部所需阶段完成后，按运行说明关闭精确对应的游戏/MAA，不结束无关程序。

提交超时、部分失败、未知订单、证据缺失或版本变化时，先阅读 [RECOVERY.md](RECOVERY.md)。不要删除账本、改名或换一个空 clone 重试。完整冷启动无人值守链路尚未验收。
