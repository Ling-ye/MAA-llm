# 终末地新增日常

> 谷地三仓请先读 [独立监督转交](ENDFIELD-VALLEY-TRANSFER.md)。旧 valleyiv delivery 自动提交已拒绝；原生填满不能绑定审核 item_name，已有报价不得重新装箱。以下旧谷地计划仅供审阅，其他地区与阶段不变。

本页适用于 MaaEnd v3.1.0 / MaaFramework v5.16.1。提供的受限范围包括谷地两折礼物、仓储装箱后转交、信用领取与抽卡资源优先购物/刷新、两区远程回收；实际操作仍需当前操作者明确授权。`DeliveryJobs` 是新增仓储阶段，不替代 AutoSell / AutoStockpile；原物资调度价格、库存和弹性购买阈值保持不变。

## 执行顺序与入口

先审计原核心、环境监测、物资调度及新增账本。北京时间 04:00 切日。新增入口默认离线预览。从仓库根目录运行以下命令：

~~~powershell
python scripts/endfield_extras.py --status
python scripts/endfield_extras.py --phase tail --region valleyiv
python scripts/endfield_extras.py --phase tail --region wuling
python scripts/endfield_extras.py --phase gifts --region valleyiv --unit breeze_of_kjersch
python scripts/endfield_extras.py --phase delivery --region valleyiv --unit OriginLodespring
python scripts/endfield_extras.py --phase recycle --region valleyiv
python scripts/endfield_extras.py --phase recycle --region wuling
python scripts/endfield_extras.py --phase credit-claim
python scripts/endfield_extras.py --phase credit-buy --unit Oroberyl --cycle 0
python scripts/endfield_extras.py --phase credit-buy --unit ArsenalTicket --cycle 0
python scripts/endfield_extras.py --phase credit-refresh --cycle 0
~~~

每次执行需要 `--review <本地审核JSON> --execute`，且可移植仓库原有 runtime 执行开关必须开启。审核 JSON 的 game_day、phase、region、unit、cycle 必须与命令一致；supervised 必须为 true，reviewed_at 必须带时区且在五分钟内，evidence 必须指向运行根目录内五分钟内的 1280×720 PNG 并含 SHA-256。JSON 只能记录实际看到的界面；格式校验不理解画面，不把哈希当成自动识别。

示例见 [endfield-extra-review.json](../config.example/endfield-extra-review.json)。不要直接执行占位示例。review 文件放本地配置目录，图片放运行根的 evidence；不提交它们。

回调成功只产生 awaiting_visual_verification。检查任务最终画面和实际数量后：

~~~powershell
python scripts/endfield_extras.py --verify <本次summary.json> --outcome <下表结果> --evidence <新鲜PNG>
~~~

遇到售罄、没有精确折扣、已有转交/冷却、无可收取项目等，审核 JSON 填真实 outcome，以相同阶段命令加 `--observe --review <JSON>` 记录只读观察，不调用游戏接口。observe 不允许伪造 purchased/refreshed/collected/claimed。提交结果不明、运行失败或存在未验收尝试时，会阻止后续新增操作；不能用 observe 掩盖失败，也不能改名、删账、换目录重跑。

| 阶段 | 单位及结果 | 限制 |
| --- | --- | --- |
| gifts | 谷地 7 个商品分别记账；purchased / sold_out / no_exact_discount | 仅精确 -80%（两折）；每件商品一次确认，审核每种 10 件、单价 6000，日上限 420000 谷地调度券；其他稳定物资全部禁用 |
| delivery | 五个仓储节点分别记账；transferred_pending / already_transferred / cooldown / insufficient_stock | 只快速转交或已有任务直接转交；禁止自动送货、导航和先接单再走路的回退；每节点一次尝试 |
| tail | valleyiv / wuling；claimed / pending_acceptance / pending_delivery / nothing_claimable | 每日先检查“我转交的委托”，只领取已完成尾款；等待接单不等于到账 |
| recycle | valleyiv / wuling；collected / nothing_collectible | 两地区分别远程收取和核验，不推断未显示数量 |
| credit-claim | 每日一次；claimed / nothing_claimable | 领取后停止，不自动进入购买 |
| credit-buy | Oroberyl 或 ArsenalTicket，cycle 0–4；purchased / sold_out / unaffordable / budget_limit | 只指定嵌晶玉/武库配额；每货架每目标一次；买不起就停止，无任意商品回退 |
| credit-refresh | cycle 0–3；refreshed | 先领取信用、核验两个目标，再刷新一次；成本依次 80/120/160/200，随后重新看货架 |
| credit-review | 最终只读观察；daily_limit_used_up / budget_limit | 必须已有领取记录、最后货架两个目标的独立记录、无未验收步骤，targets_reviewed_first=true；完成购物后用 observe 记录刷新耗尽或额度限制 |

礼物 unit：breeze_of_kjersch、tidestone_specimen、simonch_shawl、frontiers_watch、aurylene_camera、cosmic_gate_puzzle、surfing_festival_ticket。
仓储 unit：谷地 OriginiumSciencePark、OriginLodespring、PowerPlateau；武陵 WulingCity、TestArea。

仓储 review 必须逐节点填写实际 item_name、quantity（最多 6000）、stock_quantity、cargo_capacity、item_volume、cargo_checked=true、transfer_available=true，以及可辨认该仓库/货箱的 order_reference、order_state。order_state 执行只接受 ready_to_pack 或 packed_untransferred；已转交、冷却、低库存只能记录对应观察，未知/正在运输不能重新装箱。材料库存必须不少于审核数量，数量乘单件体积必须足以装满当前货箱。先完成该地区 tail 检查，才能提交新装箱。脚本复用原生填满逻辑；item_name 没有绑定为原生选材硬约束，必须在最终确认前监督核对实际材料。这里的数量上限是执行前人工审核门禁，不是独立 OCR 校验的实际消耗硬计数。礼物亦需核对实际货架库存和价格；库存不是 10 或单价不是 6000 时停止、重新审阅策略，不随意改数继续。新脚本分商品/节点的封装尚未实机验收，首次运行保持全程监督。

信用 review 填 price、balance、currency=Credits。购买确认前原生识别必须与审核价格和余额一致；单价上限 400，总信用消费每日上限 2000（含最多 560 刷新费用），每次预算先预留再提交。未知消费不释放预留额度。审核目标后刷新还须 targets_reviewed_first=true。如果目标超出剩余日额度，在 credit-buy 记录 budget_limit（脚本核验实际账本额度），不能误填售罄或余额不足。最终 budget_limit 和仓储 insufficient_stock 在总审计中为 recorded_limited，不计全部完成，不自动通过关闭门禁。最后货架的两个目标仍需分别记录，禁止仅“已领取+额度有限”收口。任何阈值变更需重新审阅策略，不能直接绕过门禁。

## 验证边界与恢复

新封装目前只通过离线回归。礼物逐件购买、仓储逐节点装箱和原生填满逻辑仍需现场监督；没有独立计数证据时不得推断材料总消耗。转交状态与尾款到账分别记录，后续每天先检查待收订单，在游戏显示的到期时间前领取。

信用购买、刷新及回退分支尚未现场验收。上游 [issue #6300](https://github.com/MaaEnd/MaaEnd/issues/6300) 报告了刷新用尽后购买非目标商品的行为；本封装禁止黑名单购买、稳健刷新购买、刷新耗尽购买及额外领取信用回路，将购买/刷新拆成单步。离线测试不证明图标或 OCR 现场准确，首次仍须监督。

本封装不支持自动导航送货。转交按钮不可用时直接停下，不自动接单或启动路线。已接取的异常运输需先人工检查，当前封装可能安全停止，不能宣称全部旧运输可自动恢复。

已有 endfield-extra-* 历史回执会阻止同日新增执行；历史回执不随源码分发，也不自动改写为新状态。统一 daily_audit 保留从 2026-11-19 游戏日起要求新增 18 个独立范围及全部信用中间步骤的兼容切换点；不得倒追执行历史日期。旧目录和新仓库只选一个执行，同日禁止使用空副本重跑。

共享 pipeline.lock、STOP、提交前独占账本、任务 ID 映射、请求/审核/总结哈希及前后截图均保留。资源版本/哈希变化即停。结果未知只停止本 runtime，不重试，不杀无关进程。完成全部所需阶段后才走原有关闭流程。代码维护只运行离线测试，不授权启动游戏或消耗资源。


低库存与中断：上游 [issue #4773 的分析](https://github.com/MaaEnd/MaaEnd/issues/4773#issuecomment-5187148728) 记录 v2.22.0 指定低库存货物未满箱而超时；它不证明当前 v3.1.0 仍有相同问题。执行前拦截不足量，保留原生填满/已满检测，不自动换材料。提交后失败/超时仍保留区域、仓库、订单标识、上次订单状态、最终 API 状态、失败截图和日志；订单记为 interrupted_unknown，不误报转交。先人工查看对应仓库是部分填入、已装箱、已转交还是仍未知，记录现场后报告；当前版本不提供清账重试或自动恢复装箱入口。即使后来在游戏内完成转交，也不能把原失败回执改成原生成功。

尾款按每天每地区防重，当前没有同日再次领取入口。tail 的审核 JSON 必须逐单保留 orders（order_reference、state、expiry_text）；state 可为 pending_acceptance、pending_delivery、claimable、claimed、unknown，未显示到期时间时明确写“未显示”。确实无订单才可 orders=[] 且 no_orders_visible=true。地区 claimed 仅证明本次观察到的可领款已领取，不代表所有转交单结清；pending_acceptance 检查后当天才完成的订单，下一日继续检查，并关注实际到期提示。未知订单必须在报告中保留，不能推断到账。

订单 state=unknown 只允许保留为待查信息；执行和 observe 验收均会阻止，不能把 unknown 填成 nothing_claimable 来解锁装箱。先核对实际仓库/订单，再准备真实的新审核记录。
