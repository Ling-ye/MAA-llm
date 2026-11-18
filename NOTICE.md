# 来源与许可

本仓库的脚本、技能、文档及组合配置以 GNU Affero General Public License version 3（AGPL-3.0-only）发布，完整条款见 [LICENSE](LICENSE)。本项目不是游戏发行商或下列上游项目的官方产品。

## 上游来源

| 来源 | 对应版本 | 在本项目中的关系 | 许可 |
| --- | --- | --- | --- |
| [MaaAssistantArknights](https://github.com/MaaAssistantArknights/MaaAssistantArknights) | v6.22.0 | 明日方舟运行依赖；任务名、参数及受限配置依据该版本接口 | [AGPL v3](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/v6.22.0/LICENSE) |
| [MaaGF2Exilium](https://github.com/DarkLingYun/MaaGF2Exilium) | v2.8.4 | 少前 2 运行依赖；适配器入口和 pipeline 覆盖基于该版本资源 | [MIT](LICENSES/MaaGF2Exilium-MIT.txt)，Copyright (c) 2024 MaaXYZ |
| [MaaEnd](https://github.com/MaaEnd/MaaEnd) | v3.1.0 | 终末地运行依赖；任务计划、节点和 pipeline 覆盖基于该版本资源 | [AGPL v3](https://github.com/MaaEnd/MaaEnd/blob/v3.1.0/LICENSE) |
| [MaaFramework](https://github.com/MaaXYZ/MaaFramework) | v5.16.1（终末地要求） | SDK/API 运行依赖；少前 2 使用其对应 release 自带环境 | [LGPL v3](https://github.com/MaaXYZ/MaaFramework/blob/v5.16.1/LICENSE.md) |

policies/ 中的任务计划、允许节点和完整性记录，以及 scripts/ 中构造的 pipeline_override，包含对上述接口和资源的引用或派生改动。主要改动为限制消费范围、拆分阶段、阻断危险回退、增加账本与人工证据核验；不代表上游认可这些修改。少前 2 派生部分保留 MIT 版权与许可全文；本项目其余发布条款不撤销第三方原有权利。

## 分发范围

仓库仅分发源代码、配置模板、文档和离线测试，不包含第三方 EXE/DLL、SDK 安装包、字体、模型、游戏素材、截图或账号数据。下载器从上游官方 release 获取独立软件包，不重新托管或修改下载包。下载后的依赖、其附带组件及素材仍受各自许可证约束，重新分发前应检查相应包内声明与源码提供义务。

AGPL v3 对修改、分发以及通过网络与用户交互的修改版本设有义务；请阅读完整条款。MaaFramework 的 LGPL 不自动授予其他组件的权利。游戏名称、商标、客户端及素材归各自权利人所有；开源许可不代表获得游戏运营方对自动化行为的许可。
