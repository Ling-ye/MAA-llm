# MAA-llm

面向 **Windows、人工或 LLM 监督**的三游戏日常自动化工作流。它将 MAA、MaaGF2Exilium、MaaEnd 的准备、任务计划、运行账本、证据核验和恢复入口组织成可阅读的脚本与三个独立技能。

**当前定位：固定版本的实验性集成。默认只预览，新副本禁止直接执行游戏。尚未验证三款游戏从冷启动到完成退出的全程无人值守链路。**

本项目与游戏发行商及上游项目没有官方隶属关系；仓库不包含游戏、模拟器、第三方二进制、账号配置或运行数据。

[开始使用](docs/GETTING_STARTED.md) · [运行说明](docs/RUNBOOK.md) · [支持与验证边界](docs/VALIDATION.md) · [中断恢复](docs/RECOVERY.md) · [安全与隐私](SECURITY.md)

## 可以做什么

| 游戏 | 提供的入口 | 必须知道的限制 |
| --- | --- | --- |
| 明日方舟 | 基础日常、自然理智 TL-9；公招→基建→信用购买→领奖 | 只适配固定 MAA 版本；每次检查 TL-9 当期开放且可代理。不能直接把它当任意关卡刷图器 |
| 少女前线 2 | 基础日常与突破准备；新增每日免费箱、班组、调度室、本期热寂悖论物资模式的监督账本 | 旧执行适配器固定 v2.8.4；新增 v2.8.6 入口仅做计划、证据与防重，没有自动点击后端。喝茶与最高可扫荡关卡仍需人工核验 |
| 明日方舟：终末地 | 目标库存、单倍领取、核心奖励、环境监测、物资调度；谷地两折礼物、仓储装箱转交与尾款、信用与远程回收 | 固定 v3.1.0 / Framework v5.16.1、1280×720。谷地三仓使用独立监督转交账本，旧自动提交已停用。信用购买/刷新及其他新增封装仍待现场验收 |

具体范围以脚本、[运行说明](docs/RUNBOOK.md)和[终末地补充任务](docs/ENDFIELD-EXTRAS.md)为准。环境监测、物资调度、仓储转交分别记账；100 活跃不能替代所有阶段完成。

## 工作方式

~~~mermaid
flowchart LR
    A[只读状态与计划] --> B[当前用户授权与实时画面审核]
    B --> C[提交前写入独占账本]
    C --> D[执行受限任务]
    D --> E[核验回调、哈希与实际结果]
    E --> F[全部完成后关闭对应程序]
    D --> G[结果未知：停止并保留证据]
    E --> G
~~~

LLM 可以读取技能、解释状态并协助看图；执行仍经过确定性的版本、资源范围和防重门禁。仓库没有内置模型客户端，不要求提供模型 API Key，也不会自动选择模型或把截图上传到云端。使用外部助手时，请另行确认其文件和图像访问方式。

## 快速开始

需要 Git、Python 3.12 和 Windows PowerShell。预览、初始化和离线测试只用 Python 标准库，无需额外 pip 包。

~~~powershell
git clone https://github.com/Ling-ye/MAA-llm.git
cd MAA-llm

python --version
python -m unittest discover -s tests -v
python scripts/bootstrap.py init
python scripts/runner.py
python scripts/endfield_extras.py --status
~~~

以上命令只检查、预览或运行离线测试，不启动游戏。初始化本地配置：

~~~powershell
python scripts/bootstrap.py init --execute
~~~

它只创建缺失的 config.local 文件，不覆盖已有配置。随后按 [入门步骤](docs/GETTING_STARTED.md)配置自己的路径、固定版本和执行开关；先运行预览，再阅读对应游戏的执行前提。

下载器仅下载上游自动化软件，游戏本体、模拟器与官方启动器需自行通过各自官方渠道安装和登录。下载预览示例：

~~~powershell
python scripts/bootstrap.py download --game arknights
~~~

检查输出后加 --execute 才下载。固定资产名称、大小和 SHA-256 位于 [policies/releases.json](policies/releases.json)，下载前核对官方 release 元数据，落盘后再次校验文件并安全解压。该路径已做离线测试，尚未重新验收完整下载→安装→启动链路；自动更新、登录、验证码和 UAC 不在自动处理范围内。

## 使用三个技能

| 技能 | 文件 |
| --- | --- |
| maa-arknights | [明日方舟技能](.agents/skills/maa-arknights/SKILL.md) |
| maa-gf2 | [少女前线 2 技能](.agents/skills/maa-gf2/SKILL.md) |
| maa-endfield | [终末地技能](.agents/skills/maa-endfield/SKILL.md) |

让支持本地技能的助手读取对应 SKILL.md，或直接按文档使用命令行。技能通过相对路径引用本仓库脚本，需要保留完整目录；本仓库不保证所有助手都会自动发现或安装技能。发布这些技能不代表授权助手操作你的账号。

## 目录

| 路径 | 用途 |
| --- | --- |
| README.md | 项目入口与能力边界 |
| docs/ | 入门、运行、恢复、验证说明；[文档导航](docs/README.md) |
| .agents/skills/ | 三个独立技能 |
| config.example/ | 可分享的配置模板；执行默认关闭 |
| policies/ | 固定版本、任务策略及完整性哈希 |
| scripts/ | 启动、受限任务、账本、审计、下载和收尾入口 |
| tests/ | 不连接游戏的回归测试 |
| LICENSES/ | 第三方许可文本；来源见 [NOTICE.md](NOTICE.md) |

保留已有 scripts/ 路径及命令行参数，避免破坏现有调用。运行配置在 config.local/；本地账本、截图和日志位于 scripts/state、scripts/runs、scripts/evidence 等忽略目录。它们不能上传 Git，也不能为了重试而删除。

## 执行前请理解

- 游戏日按北京时间 04:00 切换；同一账号只使用一个运行副本。空账本不代表当天未执行。
- 版本、资源哈希或画面不符即停止；不能删版本检查来“适配”新版。
- PNG 格式、哈希和回调成功不能证明画面语义正确。实际奖励、材料和资源消耗仍需监督核验。
- 禁止付费货币补充、体力/理智药、双倍许可、抽卡、拆解及废弃基质；允许的公招加急、无人机、信用购物等另有明确范围。
- 任务可能误识别、超时或部分完成；不承诺账号安全、零损失或运营商允许自动化。使用前自行查阅适用服务条款。
- daily_pipeline 是串行状态协调器，并未自动串联所有补充步骤。部分失败不能当作完整成功。

详见 [安全与隐私](SECURITY.md)。贡献代码请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，保持离线测试和原有防重约束。

## 许可证

本仓库以 **GNU AGPL v3** 发布，见 [LICENSE](LICENSE)。第三方派生配置和运行依赖的来源、版本与许可单独列于 [NOTICE.md](NOTICE.md)；其中 MaaGF2Exilium 使用 MIT，MaaFramework 使用 LGPL v3。游戏资源、名称与商标的权利不因本项目开源而转移。

## 新增监督入口

少前2四组见 [商城、班组、调度室与本期活动](docs/GF2-SUPERVISED-DAILY.md)，谷地三仓见 [监督转交](docs/ENDFIELD-VALLEY-TRANSFER.md)。这些入口默认输出离线计划，--execute 明确拒绝；监督者实际操作前预约，之后凭新证据记账。不能把历史人工成功表述为脚本自动执行成功，也不能用空克隆重跑。

python scripts/gf2_daily_additions_audit.py 与 python scripts/endfield_valley_transfer.py --status 只读核验独立账本；旧综合审计不自动接纳新监督记录。
