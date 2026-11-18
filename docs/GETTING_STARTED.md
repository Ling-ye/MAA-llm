# 开始使用

## 1. 确认适用范围

本项目目前针对 Windows 本机流程。需要 Python 3.12、PowerShell、Git，以及自行安装并登录的游戏客户端。明日方舟流程依赖明确的本地 MuMu 实例和 loopback ADB；少前 2、终末地使用受审的桌面窗口条件。不同语言、服务器、分辨率、资源版本和模拟器布局均可能需要重新适配。

| 游戏 | 固定上游版本 | 执行方式 |
| --- | --- | --- |
| 明日方舟 | MAA v6.22.0 | 本机 MAA DLL / ADB |
| 少女前线 2 | MaaGF2Exilium v2.8.4 | release 自带 Python / SDK；其他版本禁止直接执行 |
| 终末地 | MaaEnd v3.1.0、MaaFramework v5.16.1 | 本机 MaaEnd API；1280×720 窗口 |

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
- paths.gf2_game：少前 2 游戏可执行文件。
- paths.endfield_launcher / endfield_game：终末地官方启动器与实际游戏可执行文件，用于启动和精确进程核验。
- execution.<游戏>.enabled：初始为 false。
- execution.<游戏>.not_before_game_day：允许开始的游戏日 YYYY-MM-DD。

路径由你填写，可以使用相对仓库根目录的路径。明日方舟还需在两个配置中填写 maa_dir、adb_path、mumu_cli、serial、vm_index；不要复制别人的 ADB serial 或进程信息。只有首页和配置已经核验时才能设置 ready=true。

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
python scripts/daily_pipeline.py status
python scripts/daily_audit.py
python scripts/prepare_game.py --game arknights
python scripts/ark_operations_v2.py
python scripts/gf2_safe.py
python scripts/endfield_safe.py --phase daily
python scripts/endfield_extras.py --status
~~~

初次使用没有记录，审计显示待检查属于正常状态；它不会自动把任务标成成功。运行开关仍保持关闭，直到你已核对旧目录记录、选择一个尚未执行的游戏日，并明确授权具体阶段。

需要执行时，仅启用相应游戏，设置真实起始游戏日，遵循 [RUNBOOK.md](RUNBOOK.md) 的版本、主页/关卡、截图和 --execute 前提。不要把文档中多条执行命令合成无监督批处理。

技能位于 .agents/skills/。可让支持本地文件的助手读取对应 SKILL.md；助手的权限、模型配置和截图隐私由你单独管理。无需将配置或运行证据上传至此 GitHub 仓库。

## 6. 核验、恢复与关闭

每次只运行一个阶段。回调结束后检查实际奖励和资源差异，再记录真实证据。全部所需阶段完成后，按运行说明关闭精确对应的游戏/MAA，不结束无关程序。

提交超时、部分失败、未知订单、证据缺失或版本变化时，先阅读 [RECOVERY.md](RECOVERY.md)。不要删除账本、改名或换一个空 clone 重试。完整冷启动无人值守链路尚未验收。
