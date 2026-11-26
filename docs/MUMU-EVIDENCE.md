# MuMu 监督证据命令

这里的命令不会安装、启动、登录、截图、点击、购买或关闭游戏。它们记录操作员已经看到的事实。不要把合成测试、预约、计划、无报错截图或原生回调记录成现场完成。

## 配置与只读输出

`config.example/mumu-supervised.json` 是禁用示例。复制到本地 `config.local/mumu-supervised.json`，只填已核对的专属实例 `vm_index` 与精确回环 `serial`，再按现有 runtime 规则启用具体游戏和允许游戏日。每款只能用自己的实例；PC 旧路径不是回退。终末地 Android 尚未验收登录和工作流，不允许写入。少前 2 使用 v2.8.6 的监督路径，不共用 PC 自动适配版本门禁。锁屏/未知时必须用 [guest ADB 探测](MUMU-ADB.md) 的当前 probe_proof，并绑定 screens.primary；尚未覆盖锁屏收尾。方舟已建立的 MAA ADB 路径保留当前版本和所有实际画面门禁。

- `python scripts/mumu_daily.py plan --game gf2`：项目、检查字段、允许跳过原因。
- `python scripts/mumu_daily.py status --game gf2`：每项当前周期的记录，状态为 unreviewed、reserved、verified、observed_already_done、observed_ineligible、unknown 或 blocked_invalid_receipt。达到活跃度目标不能代替其他项目。
- `python scripts/mumu_daily.py reserve --game gf2 --item <ID> --review <本地审核JSON>`
- 操作者再次核对当前画面，一次提交，结果核验用同样参数将 `reserve` 换为 `verify`。核验必须使用操作后的新截图。
- `observe` 加 `--review`：已完成填 observation=already_done。当前界面证据不足则停；仅确实不符合资格且命中 plan 中允许原因时，填 observation=ineligible 与 reason。该观察保留历史、不是授权、不会占提交名额。
- `mark-unknown --game gf2 --item <ID> --reason <原因>`：只用于已预约且提交/结果不明；保留原预约，禁止再预约或猜测成功。
- 使用真实 game day（北京时间 04:00 换日）；红枣茶的独立账本按菜品档案显示的北京时间 05:00 重置归档，顶层 day 仍填游戏日。04:00–05:00 不把同一次茶饮当两天领取，现场发现重置时间变化则停止。周项填 reviewed_period=YYYY-Www，并实际核对游戏周期和限购/领取状态。日历跨周不等于游戏重置。核对所有同日或同周的旧账以及 PC 实际状态；空账、换目录或换后端不授权重做。

## 审核 JSON

顶层字段：

- game、item、day、transport=mumu、package、maa_version、serial、vm_index、desktop_state（locked/unlocked/unknown）。
- 下列字段必须为 JSON true，且确曾独立现场核验：supervised、exact_mumu_instance_reviewed、adb_device、official_package_reviewed、decoded_fresh_guest_frame、no_unhandled_prompt、cross_transport_history_reviewed、correct_account_home_reviewed、expected_foreground_package_reviewed。
- 收尾核验已关闭应用时，用 correct_guest_after_close_reviewed 代替“应用在前台”两字段。
- 周项另需 reviewed_period、actual_weekly_cycle_reviewed=true，完成证据分别绑定具体周档或商品。
- screens 是角色→证据对象，必须含 primary，可另加 log、reward、deployment 等。各对象含 path（运行脚本目录内 evidence/ 的真实 PNG）、sha256、captured_at（带时区 ISO8601）。画面须五分钟内、可解码且 16:9；强制核验后置帧在预约之后、哈希不同。禁止用相同图片冒充两个证据角色。哈希只验证字节，不验证像素或语义。
- facts 放 plan 列出的精确布尔字段和所需实测值。预约须 current_exact_item_eligible；已完成观察须 prior_completion_visually_confirmed；不适用观察须 exact_ineligibility_visually_confirmed。保留所有前后值和相关截图，别编造未知费用、人力或奖励。关闭不是“各项均完成”。

少前 2 补充字段：

| 项目 | 现场事实 |
|---|---|
| daily-free-box | location=[商城,品质甄选,周期礼包,每日礼包]、product=每日补给箱、price_text=免费、price=0、paid_balance；预约限购日限购1/1、购买，核验日限购0/1、已售罄和 reward 帧，付费余额不变 |
| squad-duty-supply | location=[班组,补给,分配中]、product=要务补给·一、source=委托触发、独立 item_reference、claim_all=false。预约确认 selected_claim_available；验收另附 log 帧和同条绿勾 |
| dispatch-stored-puzzle | location=[委托,每日订单,调度室]、selected_method=快速取出调度室储存情报拼图；记录 stored、stamina、stamina_capacity、paid_balance。仅第一选项；非零储量且不会超上限。验收仓储归零、体力等量增加、付费余额不变 |
| dispatch-production | 同入口，selected_method=资源生产、price=0、记录 stored，并另附 reward 帧。先核对拼图和生产，再做突破扫荡；不是领取派遣/重派或周档 |
| weekly-free-box | location=[商城,品质甄选,臻品礼包,主题精选]、product=周周乐补给箱、price_text=免费、price=0、paid_balance。预约核对 limit=周限购1/1、control=购买、progress=goal；提交一次；验收同一周货项剩余0、付费余额不变及 reward 帧。相邻商品换位不是重试理由 |
| dispatch-weekly-* | facts.tier 必须精确匹配档位；实际周重置需复核，观察未解锁档不等于已领 |
| cooking | 预约：`recipe=芝士烤土豆`、`menu=常规菜品`、`recipe_control=下一步`、`final_control=确认邀请`、`first_serving_free_visible=true`、`fee_or_premium_prompt=false`、`cooking_task_progress=0/1`，另附 `recipe` 帧；主画面证据为最终邀请页。验收：同菜品/菜单、`cooking_task_progress=1/1`、`active_meal_effect_reviewed=true` 和 `meal_effect` 帧。不适用只接受实际「常规菜品」`regular` 帧，任务 0/1 及 `reviewed_menu=常规菜品`、`regular_first_free_unavailable_verified=true`、`standard_recipe_next_absent_verified=true`。档案「前往升级」或其他模式无材料不能证明。 |
| tea | 预约：recipe=红枣茶、recipe_level=4、confirmation_recipe=红枣茶、cost_reviewed_free=true、fee_or_premium_prompt=false、free_uses_remaining=1；另附 confirm 帧。验收：tea_task_progress=1/1、cup_active_reviewed=true、effect_type=饮品加成、effect_text=每消耗10情报拼图，可获取2~3数据链路，另附 drink_effect 帧。菜品加成、单独任务计数或制作后弹窗均不能替代。 |
| event-material | event=热寂悖论、stage=DF-1-5 于乱流中 V、material_mode=true；已知战斗截止后只观察，不替换活动 |

## 少前 2：仅当次授权的零体力活动

这是监督证据机制，不是活动发现器或通关机器人。先在游戏里确认真实可进入的单关，禁止为了填字段捏造关卡、费用、周期或票数。主线、定时任务和旧热寂悖论入口不走此分支。已核验的「直播重连世界海 → 物资模式 → KF-1-5 打榜任务V」有单独有限批次适配，活动挑战未开放和剧情模式不能冒充该关。完成或未核实均不会自动转下一关。

1. 写独立的本地范围 JSON：`mode` 取 `event-stage` / `permanent-challenge`，`activity`、`stage`、`difficulty`、`cycle` 填当前画面精确名称或周期标识，`attempt` 从 1 顺序，`quota_type` 为 `first-clear`、`free-attempt`，另外授权用现有单张票才选 `existing-ticket`。同周期同关范围不要改名来重试；不同额度类型共用同一尝试标识，日常重置也不会解除已提交记录。
2. `python scripts/mumu_daily.py activity-key --game gf2 --review <scope.json>` 返回该尝试的 `item`。按正常 MuMu 核验格式填写 reserve，`facts.activity_scope` 放该范围对象；`facts.window_start`、`window_end` 为带时区已核实开放前后界限，需 `stamina_cost=0`、`stamina`、`quota_remaining`、`purchase_or_refill_prompt=false`、`explicitly_selected_current_attempt=true`。首通标为 `first_clear_pending=true`，额度 1；其他免费路径 `ticket_per_attempt=0`；票路径再填 `ticket`、`ticket_per_attempt=1`、`use_existing_ticket_authorized=true`。相应 attestations：`exact_activity_and_stage_authorized actual_game_cost_reviewed one_attempt_only no_auto_repeat no_refill no_purchase current_exact_item_eligible`。
3. `screens.primary` 是精确选择好、已核实一次点击提交的当前画面，也是 `probe_proof` 对应的全帧（无论宿主机锁屏与否）；另给当前 `screens.quota`。与该键匹配的受监督 `mumu_guest.py tap --item` 才放行，且只接受预约使用的全帧、当前周期，以及事前核到确认按钮内的原图整数坐标 `facts.entry_tap_xy=[x,y]`。禁止换帧重放；如果选关还需要其他步骤，先在无消耗导航里走到就绪状态。
4. Verify 必须同范围、同费用、同窗口与同 guest，提供更新的全帧和独立额度证据；普通单关 `result=clear`（下述自律单独使用 `sweep-complete`）、`no_stamina_use_verified=true`、体力不减少（允许自然恢复），额度恰降 1，首通标记变 false，并明确核对 `same_activity_and_stage_result clear_and_reward_verified debit_and_quota_reviewed`。不明应 mark-unknown，不能跳过旧提交去下一次同关；下一次必须衔接旧核验余额并重新预约。结果不是客户端截图自动识别，到账判断由监督者负责。

### 直播重连世界海：确认现有券及终止时间

当前只接受范围 `{"mode":"event-material-sweep","activity":"直播重连世界海","stage":"KF-1-5 打榜任务V","difficulty":"物资模式","cycle":"2026-12-15T08:59:00+08:00","attempt":1,"quota_type":"existing-ticket"}`。关卡战斗于北京时间 2026-12-15 08:59 截止，兑换另至 12-21 04:59，兑换期不是刷关期（战斗期见[官方主题活动预告](https://www.taptap.cn/moment/873954188269193197?group_id=232066)）。选择已三星且具备自律的单关。另填 `ticket=真爱勋章`、`ticket_capacity=6`、`all_three_stage_objectives=true`、`exact_batch_authorized=true`、`selected_runs`（1–3，不大于现存券）、`confirmation_title=自律准备`、`confirmation_control=确认`、`confirmation_enabled=true`，在最终确认面板预约，一次提交整批。核验填 `result=sweep-complete`，附 `reward` 帧和 `reward_name=粉丝点赞`、`reward_quantity`（每次 ×1000）。奖励弹窗不显示关卡或次数，须与预约时同关选定次数、所附结算画面及同活动票券扣量共同验收；额度必须恰减选定次数、体力不扣；禁止补券、改关、拆单重试或自动选择其他活动。普通单关仍只允许一次。

同活动「开播推流」单独核对：仅领取页面已达标且可领的任务，例如「决策构象」2/2，核验单条绿勾与对应「粉丝点赞 ×50」。北京时间 05:00 按页面实核重置；不把「军备解析」/「定向精研」当零体力项目，也不因以前用过体力而再消耗体力补单。非本自律凭证，不用扫荡扣券程序领任务。

## 明日方舟：仅记录明确授权的短期活动代理

可选项 sanity-event-stage 不属于默认关卡，不改 runner.py 的 TL-9 限制，不会点击、不调用 MAA Fight。只有当次明确给出关卡与授权时段，且核对游戏内**战斗**起止时间、精确普通关和可代理时才预约；活动商店关闭不是战斗截止。OS-7 是原生代理案例，不是配置、默认关或持续授权。

- facts：stage（明确普通关编号）、event、mode=native-auto-deploy、battle_starts_at 与 battle_ends_at（带时区，直接用游戏内战斗窗口）、sanity_per_run、planned_runs、natural_sanity_before、refill_or_retry=false；核对原有同日刷图记录与实际理智，按自然理智和 UI 批量上限设定次数，额外提供 event_window 截图。
- 结束后提供不同的新 result 截图，保留相同 stage/event/mode/时间窗，填 completed_runs 和 observed_sanity_spent。数量/费用不符或提交状态不明，留 unknown 和实测证据，不重开关卡。战斗窗口截止后不预约新动作；符合证据的同日已完成结果仍可核验。
- 不让临时活动、历史观察或战斗 cutoff 成为其他关卡的默认授权。

所有新账本存 `state/mumu/`、与旧执行入口共用本地 pipeline.lock；直接游戏操作仍由监督者确保同一时间只有唯一操作者。不要将状态、配置、证据、账号或实际收据提交至 Git。收据追踪过程，并不会将监督操作变成无人值守能力。
