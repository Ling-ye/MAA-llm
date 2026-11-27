import datetime as dt
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import mumu_daily as m


class MuMuDailyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "evidence").mkdir()
        self.now = dt.datetime(2030, 1, 10, 2, tzinfo=dt.timezone.utc)
        self.binding = {"serial": "127.0.0.1:12345", "vm_index": 1}
        self.n = 0

    def frame(self, at):
        self.n += 1
        # Tiny synthetic structural fixture, not game data and never persisted in repo.
        raw = b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR" + struct.pack(">II",16,9)
        raw += bytes([self.n, 0, 0, 0, 0]) + b"\0\0\0\0IEND\xaeB\x60\x82"
        path = self.root / "evidence" / f"{self.n}.png"
        path.write_bytes(raw)
        return {"path": str(path), "captured_at": at.isoformat(), "sha256": m.sha(raw)}

    def review(self, item, outcome="reserve", game="gf2", seconds=0, **specific):
        at = self.now + dt.timedelta(seconds=seconds)
        scope, results = m.item_checks(game,item)
        f = dict.fromkeys((scope + " " + results + " current_exact_item_eligible prior_completion_visually_confirmed exact_ineligibility_visually_confirmed").split(), True)
        f.update(specific)
        d = dict.fromkeys("""supervised exact_mumu_instance_reviewed adb_device official_package_reviewed decoded_fresh_guest_frame no_unhandled_prompt cross_transport_history_reviewed correct_account_home_reviewed expected_foreground_package_reviewed actual_weekly_cycle_reviewed""".split(), True)
        d.update(game=game, item=item, day=m.game_day(at), transport="mumu", package=m.PACKAGES[game],
                 maa_version=m.VERSIONS[game], desktop_state="unlocked",
                 reviewed_period=m.period(item, at), screens={"primary": self.frame(at)}, facts=f, **self.binding)
        if item == "tea":
            f.update(recipe="红枣茶", recipe_level=4, confirmation_recipe="红枣茶",
                     cost_reviewed_free=True, fee_or_premium_prompt=False, free_uses_remaining=1,
                     effect_type="饮品加成", effect_text="每消耗10情报拼图，可获取2~3数据链路",
                     cup_active_reviewed=True, tea_task_progress="1/1")
            d["screens"].update(confirm=self.frame(at), drink_effect=self.frame(at))
            f.update(specific)
        if item == "cooking":
            f.update(menu="常规菜品", recipe="芝士烤土豆", recipe_control="下一步",
                     final_control="确认邀请", first_serving_free_visible=True, fee_or_premium_prompt=False,
                     cooking_task_progress="0/1")
            d["screens"]["recipe"] = self.frame(at)
            f.update(specific)
        return d

    def call(self, item, action, review=None, seconds=0, game="gf2", reason=None):
        return m.mutate(self.root, game, item, action, review or {}, reason,
                        self.now + dt.timedelta(seconds=seconds),
                        authorize=lambda _: None, bind=lambda _: self.binding)

    def test_route_and_eligibility(self):
        self.assertFalse(m.route("gf2")["native_fallback"])
        self.assertFalse(m.route("gf2")["automatic_game_input"])
        self.assertFalse((self.root/"state").exists())
        item = "sanity-tl9"
        d = self.review(item, game="arknights")
        d.update(observation="ineligible", reason="stage_closed")
        self.call(item, "observe", d, game="arknights")
        self.assertEqual(m.load_record(self.root, "arknights", item, self.now)["status"], "observed_ineligible")
        d["reason"] = "choose_other_stage"
        with self.assertRaises(m.Blocked):
            self.call(item, "observe", d, game="arknights")

    def test_prior_results_and_unknown_block_replay(self):
        item = "tea"
        self.assertEqual(self.call(item, "reserve", self.review(item))["status"], "reserved")
        self.call(item, "mark-unknown", reason="no result")
        with self.assertRaises(m.Blocked):
            self.call(item, "reserve", self.review(item))
        with self.assertRaises(m.Blocked):
            self.call(item, "verify", self.review(item, seconds=4), seconds=4)

    def test_refill_slot_uses_plan_reservation_and_one_permit(self):
        import ark_recruit_refill as r
        item = "recruit-refill-slot-1"
        tags = ["近卫干员", "近战位", "重装干员", "防护", r.TOP]
        # Synthetic minimal calculator input for exercising the actual journal.
        pool = ([(6,"S",frozenset({r.TOP})),(3,"3",frozenset(tags[:-1])),
                 (4,"4",frozenset({"重装干员"})),(5,"5",frozenset({"医疗干员",r.SENIOR}))],"fixture")
        hold = self.review(item, game="arknights", slot=1, slot_state="empty",
                           tags=tags, permit_count=4)
        hold["screens"].update(overview=self.frame(self.now), confirm=self.frame(self.now))
        hold.update(observation="ineligible", reason="top_senior_hold")
        before = self.review(item, game="arknights", slot=1, slot_state="empty",
                             tags=tags[:-1]+["医疗干员"], permit_count=4, paid_prompt=False,
                             expedite_phase_ended=True, selected_tags=["医疗干员"],
                             duration_minutes=540, permit_cost=1, lmd=100, quoted_lmd=0)
        before["screens"].update(overview=self.frame(self.now), confirm=self.frame(self.now))
        with patch.object(r, "read_pool", return_value=pool):
            self.assertEqual(self.call(item, "observe", hold, game="arknights")["status"],
                             "observed_ineligible")
            with self.assertRaisesRegex(m.Blocked, "terminal"):
                self.call(item, "reserve", before, game="arknights")
        item = "recruit-refill-slot-2"
        before.update(item=item)
        before["facts"]["slot"] = 2
        def review(slot, stage, data, record):
            return r.review_slot(slot, stage, data, record, get_pool=lambda: pool, get_policy=lambda: r.POLICY)
        with patch.object(m, "recruit_refill_review", side_effect=review):
            self.assertEqual(self.call(item, "reserve", before, game="arknights")["status"], "reserved")
            after = self.review(item, game="arknights", seconds=5, slot=2, slot_state="running",
                                permit_count=3, lmd=100, selected_tags=["医疗干员"], remaining_seconds=32395,
                                refresh_or_expedite_used=False)
            after["screens"]["overview"] = self.frame(self.now + dt.timedelta(seconds=5))
            self.assertEqual(self.call(item, "verify", after, seconds=5, game="arknights")["status"], "verified")
            with self.assertRaisesRegex(m.Blocked, "existing attempt"):
                self.call(item, "reserve", before, game="arknights")

    def test_reservation_blocks_other_game_till_reconciled(self):
        self.call("tea", "reserve", self.review("tea"))
        with self.assertRaises(m.Blocked):
            self.call("base", "reserve", self.review("base", game="arknights"), game="arknights")
        self.call("tea", "mark-unknown", reason="typed synthetic note")
        self.call("base", "reserve", self.review("base", game="arknights"), game="arknights")

    def test_current_day_identity_and_evidence(self):
        item = "tea"
        r = self.review(item)
        for key, value in (("maa_version","v2.8.4"), ("package","com.not.official"), ("serial","127.0.0.1:12346"), ("desktop_state","locked"), ("day","2030-01-09")):
            with self.subTest(key=key), self.assertRaises(m.Blocked):
                self.call(item, "reserve", dict(r, **{key:value}))
        self.call(item, "reserve", r)
        with self.assertRaises(m.Blocked):
            self.call(item, "verify", r)
        self.assertEqual(self.call(item, "verify", self.review(item, seconds=2), seconds=2)["status"], "verified")
        Path(r["screens"]["primary"]["path"]).write_bytes(b"broken")
        status = m.reported_state(self.root, "gf2", self.now)
        self.assertIn({"id": item, "period": m.game_day(self.now), "status": "blocked_invalid_receipt"}, status["items"])

    def test_tea_requires_matching_free_confirmation_and_drink_proof(self):
        item = "tea"
        review = self.review(item, recipe_level=3)
        with self.assertRaises(m.Blocked):
            self.call(item, "reserve", review)
        for fields in ({"fee_or_premium_prompt": True}, {"free_uses_remaining": 0},
                       {"confirmation_recipe": "其他饮品"}, {"cost_reviewed_free": False}):
            with self.subTest(fields=fields), self.assertRaises(m.Blocked):
                self.call(item, "reserve", self.review(item, **fields))
        review = self.review(item)
        del review["screens"]["confirm"]
        with self.assertRaises(m.Blocked):
            self.call(item, "reserve", review)
        self.call(item, "reserve", self.review(item))
        for fields in ({"effect_type": "菜品加成"}, {"effect_text": "回复体力"},
                       {"cup_active_reviewed": False}, {"tea_task_progress": "0/1"}):
            with self.subTest(fields=fields), self.assertRaises(m.Blocked):
                self.call(item, "verify", self.review(item, seconds=1, **fields), seconds=1)
        review = self.review(item, seconds=2)
        del review["screens"]["drink_effect"]
        with self.assertRaises(m.Blocked):
            self.call(item, "verify", review, seconds=2)
        self.call(item, "verify", self.review(item, seconds=3), seconds=3)

    def test_tea_cycle_uses_cn_five_not_generic_four(self):
        before = dt.datetime(2030, 1, 10, 20, 59, tzinfo=dt.timezone.utc)
        after = before + dt.timedelta(minutes=1)
        self.assertEqual(m.game_day(before), m.game_day(after))
        self.assertEqual(m.period("tea", before), "2030-01-10")
        self.assertEqual(m.period("tea", after), "2030-01-11")
        self.assertEqual(m.period("cooking", before), m.period("cooking", after))

    def test_tea_keeps_same_claim_at_general_reset_and_rejects_prev_cycle_frame(self):
        self.now = dt.datetime(2030, 1, 10, 19, 59, 59, tzinfo=dt.timezone.utc)
        self.call("tea", "reserve", self.review("tea"))
        with self.assertRaises(m.Blocked):
            self.call("tea", "reserve", self.review("tea", seconds=2), seconds=2)
        self.call("tea", "verify", self.review("tea", seconds=2), seconds=2)
        self.now += dt.timedelta(hours=1, seconds=1)
        review = self.review("tea")
        review["screens"]["primary"] = self.frame(self.now-dt.timedelta(seconds=1))
        with self.assertRaisesRegex(m.Blocked, "05:00 reset"):
            self.call("tea", "reserve", review)

    def test_event_exact_window_and_native_result_not_maa(self):
        item, game = "sanity-event-stage", "arknights"
        before = dict(stage="AB-7", mode="native-auto-deploy", event="synthetic event",
                      battle_starts_at=(self.now-dt.timedelta(days=1)).isoformat(),
                      battle_ends_at=(self.now+dt.timedelta(hours=1)).isoformat(),
                      sanity_per_run=18, planned_runs=2, natural_sanity_before=40, refill_or_retry=False)
        for fields in ({"mode":"maa"}, {"stage":"TL-9"}, {"planned_runs":3}, {"refill_or_retry":True},
                       {"battle_ends_at":self.now.isoformat()}):
            review = self.review(item, game=game, **dict(before, **fields))
            review["screens"]["event_window"] = self.frame(self.now)
            with self.subTest(fields=fields), self.assertRaises(m.Blocked):
                self.call(item, "reserve", review, game=game)
        review = self.review(item, game=game, **before)
        review["screens"]["event_window"] = self.frame(self.now)
        self.call(item, "reserve", review, game=game)
        for count, cost in ((1,18),(2,35)):
            attempt = self.review(item, game=game, seconds=3, completed_runs=count, observed_sanity_spent=cost, **before)
            attempt["screens"]["result"] = self.frame(self.now+dt.timedelta(seconds=3))
            with self.assertRaises(m.Blocked):
                self.call(item, "verify", attempt, seconds=3, game=game)
        done = self.review(item, game=game, seconds=4, completed_runs=2, observed_sanity_spent=36, **before)
        done["screens"]["result"] = self.frame(self.now+dt.timedelta(seconds=4))
        result = self.call(item, "verify", done, seconds=4, game=game)
        self.assertFalse(result["game_action_performed"])

    def test_cooking_no_eligible_recipe_is_observation_not_completion(self):
        item = "cooking"
        review = self.review(item, cooking_task_progress="0/1",
                             research_notice="暂无可选择食材", creative_notice="暂无可选择菜谱",
                             archive_recipe="芝士烤土豆", archive_control="前往升级",
                             free_regular_action_absent=True)
        review.update(observation="ineligible", reason="no_eligible_free_recipe")
        with self.assertRaises(m.Blocked):
            self.call(item, "observe", review)
        review["screens"].update(creative=self.frame(self.now), archive=self.frame(self.now))
        with self.assertRaises(m.Blocked):
            self.call(item, "observe", review)
        review["screens"]["regular"] = self.frame(self.now)
        review["facts"].update(reviewed_menu="常规菜品", regular_first_free_unavailable_verified=True,
                               standard_recipe_next_absent_verified=True)
        for fields in ({"regular_first_free_unavailable_verified": False}, {"cooking_task_progress": "1/1"},
                       {"standard_recipe_next_absent_verified": False}, {"reviewed_menu": "创意"}):
            attempt = dict(review, facts=dict(review["facts"], **fields))
            with self.subTest(fields=fields), self.assertRaises(m.Blocked):
                self.call(item, "observe", attempt)
        self.assertEqual(self.call(item, "observe", review)["status"], "observed_ineligible")
        result = m.load_record(self.root, "gf2", item, self.now)
        self.assertNotIn("after", result)
        self.assertNotIn("before", result)
        # An explicitly reviewed free option appearing later is a separate reservation.
        self.call(item, "reserve", self.review(item, seconds=2), seconds=2)

    def test_cooking_actual_free_entry_and_meal_only(self):
        item = "cooking"
        for f in ({"recipe_control": "前往升级"}, {"menu": "创意"}, {"fee_or_premium_prompt": True}):
            with self.assertRaises(m.Blocked):
                self.call(item, "reserve", self.review(item, **f))
        self.call(item, "reserve", self.review(item))
        r = self.review(item, seconds=1, cooking_task_progress="1/1", active_meal_effect_reviewed=True)
        with self.assertRaises(m.Blocked):
            self.call(item, "verify", r, seconds=1)
        r["screens"]["meal_effect"] = self.frame(self.now + dt.timedelta(seconds=1))
        self.assertEqual(self.call(item, "verify", r, seconds=1)["status"], "verified")

    def test_activity_authorization_binding_and_no_replay(self):
        from unittest.mock import patch
        scope = dict(mode="event-stage", activity="synthetic event", stage="S-1", difficulty="normal",
                     cycle="synthetic window", attempt=1, quota_type="free-attempt")
        item = m.scope_key(scope)
        def reviewed(key=item, seconds=0, remaining=2, **updates):
            f = dict(activity_scope=scope, window_start=(self.now-dt.timedelta(days=1)).isoformat(),
                     window_end=(self.now+dt.timedelta(days=3)).isoformat(), stamina_cost=0,
                     stamina=42, purchase_or_refill_prompt=False, quota_remaining=remaining,
                     ticket_per_attempt=0, explicitly_selected_current_attempt=True, entry_tap_xy=[10, 10])
            f.update(updates)
            r = self.review(key, seconds=seconds, **f)
            at = self.now+dt.timedelta(seconds=seconds)
            r["screens"]["quota"] = self.frame(at)
            ref = self.root/"evidence"/"mock-proof.json"
            ref.write_text("{}")
            r["probe_proof"] = str(ref)
            s = r["screens"]["primary"]
            doc = {"frame": {"path": Path(s["path"]).relative_to(self.root).as_posix(), "sha256":s["sha256"]},
                   "captured_at":s["captured_at"], "identity":dict(self.binding,pid=600)}
            return r, doc
        for f in ({"stamina_cost": 1}, {"stamina_cost": False}, {"purchase_or_refill_prompt": True},
                  {"ticket_per_attempt": 1}, {"quota_remaining": 0}, {"window_end": self.now.isoformat()},
                  {"activity_scope": dict(scope, stage="S-2")}):
            r, doc = reviewed(**f)
            with patch("mumu_guest.proof",return_value=doc), self.assertRaises(m.Blocked):
                self.call(item, "reserve", r)
        second = dict(scope, attempt=2)
        second_item = m.scope_key(second)
        r, doc = reviewed(second_item, activity_scope=second)
        with patch("mumu_guest.proof",return_value=doc), self.assertRaisesRegex(m.Blocked,"prior ordered attempt"):
            self.call(second_item, "reserve", r)
        r, doc = reviewed()
        unproved = dict(r); unproved.pop("probe_proof")
        with self.assertRaisesRegex(m.Blocked,"exact GF2 probe"):
            self.call(item, "reserve", unproved)
        with patch("mumu_guest.proof",return_value=doc):
            self.call(item, "reserve", r)
        self.assertIn(item, m.current_items(self.root,"gf2",self.now + dt.timedelta(days=1)))
        for count, sta in ((2, 42), (1, 41)):
            r, doc = reviewed(seconds=1, remaining=count, stamina=sta, result="clear",
                              no_stamina_use_verified=True)
            with patch("mumu_guest.proof",return_value=doc), self.assertRaises(m.Blocked):
                self.call(item, "verify", r, seconds=1)
        r, doc = reviewed(seconds=2, remaining=1, stamina=43, result="clear", no_stamina_use_verified=True)
        with patch("mumu_guest.proof",return_value=doc):
            self.assertEqual(self.call(item,"verify",r,seconds=2)["status"],"verified")
        self.assertEqual(item,m.scope_key(dict(scope,quota_type="existing-ticket")))
        r,doc=reviewed(seconds=86400)
        with patch("mumu_guest.proof",return_value=doc), self.assertRaisesRegex(m.Blocked,"prior completion"):
            self.call(item,"reserve",r,seconds=86400)
        r,doc=reviewed(second_item, seconds=86400, activity_scope=second, remaining=1)
        with patch("mumu_guest.proof",return_value=doc):
            self.assertEqual(self.call(second_item,"reserve",r,seconds=86400)["status"],"reserved")

    def test_reviewed_material_batch_checks_closed_window_quota_and_exact_reward(self):
        from gf2_zero_stamina import MATERIAL_SCOPE, activity_review
        at = "2026-11-26T20:00:00+08:00"
        scope = dict(MATERIAL_SCOPE)
        item = m.scope_key(scope)
        facts = dict(activity_scope=scope, window_start="2026-11-26T04:00:00+08:00",
                     window_end=scope["cycle"], stamina=31, stamina_cost=0,
                     purchase_or_refill_prompt=False, quota_remaining=3, ticket="真爱勋章",
                     ticket_capacity=6, ticket_per_attempt=1, use_existing_ticket_authorized=True,
                     all_three_stage_objectives=True, selected_runs=3, exact_batch_authorized=True,
                     confirmation_title="自律准备", confirmation_control="确认", confirmation_enabled=True,
                     explicitly_selected_current_attempt=True, entry_tap_xy=[10, 10])
        d = dict(facts=facts, guest_identity={"pid":10}, at=at,
                 screens={x: {"captured_at":at} for x in ("primary","quota")})
        for change in ({"ticket": "wrong"}, {"ticket_capacity": 9}, {"quota_remaining": 2},
                       {"quota_remaining": 7}, {"confirmation_title": "购买"}, {"selected_runs": 4},
                       {"window_end": "2026-12-21T04:59:00+08:00"}, {"entry_tap_xy": [True,10]}):
            with self.subTest(change=change), self.assertRaises(m.Blocked):
                activity_review(item,"reserve",dict(d,facts=dict(facts,**change)),None)
        activity_review(item,"reserve",d,None)
        after = dict(facts,quota_remaining=0,result="sweep-complete",no_stamina_use_verified=True,
                     reward_name="粉丝点赞", reward_quantity=3000)
        result = dict(d,facts=after,screens={**d["screens"],"reward":{"captured_at":at}})
        for change in ({"reward_quantity": 2000}, {"reward_name":"wrong"}, {"quota_remaining": 1}, {"stamina": 30}):
            with self.subTest(change=change), self.assertRaises(m.Blocked):
                activity_review(item,"verify",dict(result,facts=dict(after,**change)),{"before":d})
        activity_review(item,"verify",result,{"before":d})
        with self.assertRaises(m.Blocked):
            activity_review(item,"reserve",dict(d,at=scope["cycle"]),None)

    def test_story_hero_stage_uses_distinct_first_clear_proofs(self):
        from gf2_zero_stamina import HERO_SCOPE, activity_review
        at = "2026-11-26T20:00:00+08:00"
        scope = dict(HERO_SCOPE)
        item = m.scope_key(scope)
        for scope_changes in ({"difficulty": "普通"}, {"quota_type": "free-attempt"},
                              {"mode": "permanent-challenge"}, {"cycle":"different"}):
            with self.subTest(scope_changes=scope_changes), self.assertRaises(m.Blocked):
                m.scope_key(dict(scope,**scope_changes))
        facts = dict(activity_scope=scope, window_start="2026-11-26T04:00:00+08:00",
                     window_end=scope["cycle"], stamina=31, stamina_cost=0,
                     purchase_or_refill_prompt=False, quota_remaining=1, ticket_per_attempt=0,
                     first_clear_pending=True, explicitly_selected_current_attempt=True, entry_tap_xy=[10, 10],
                     challenge_control="挑战", reviewed_story_hero_mode=True, team_and_any_assist_reviewed=True,
                     chapter_objectives=3, chapter_objective_cap=45)
        d = dict(facts=facts, guest_identity={"pid": 10}, at=at,
                 screens={x: {"captured_at": at} for x in ("primary","quota","map","stage")})
        for change in ({"reviewed_story_hero_mode": False}, {"team_and_any_assist_reviewed":False},
                       {"challenge_control": "观看"}, {"stamina_cost": 1}):
            with self.subTest(change=change), self.assertRaises(m.Blocked):
                activity_review(item,"reserve",dict(d,facts=dict(facts,**change)),None)
        activity_review(item,"reserve",d,None)
        after = dict(facts,quota_remaining=0,result="clear",no_stamina_use_verified=True, first_clear_pending=False,
                     win_objective_credited=True, within_eight_rounds_credited=True, at_most_one_allied_loss_credited=True,
                     same_hero_stage_complete_on_map=True, unlocked_stage_id="KS-1-4", chapter_objectives=6,
                     reward_name="坍塌晶条", reward_quantity=50)
        result = dict(d, facts=after, screens={**d["screens"],"reward": {"captured_at":at}})
        for change in ({"chapter_objectives": 5}, {"unlocked_stage_id": "KS-1-5"}, {"reward_quantity": 30},
                       {"at_most_one_allied_loss_credited": False}, {"first_clear_pending": True}):
            with self.subTest(change=change), self.assertRaises(m.Blocked):
                activity_review(item,"verify",dict(result,facts=dict(after,**change)),{"before":d})
        activity_review(item,"verify",result,{"before":d})

    def test_story_hero_branch_requires_seven_rounds_and_exact_next_stage(self):
        from gf2_zero_stamina import HERO_BRANCH_SCOPE, activity_review
        at = "2026-11-26T20:00:00+08:00"
        scope = dict(HERO_BRANCH_SCOPE)
        item = m.scope_key(scope)
        for scope_changes in ({"difficulty": "普通"}, {"quota_type": "free-attempt"},
                              {"mode": "permanent-challenge"}, {"cycle":"different"}):
            with self.subTest(scope_changes=scope_changes), self.assertRaises(m.Blocked):
                m.scope_key(dict(scope,**scope_changes))
        facts = dict(activity_scope=scope, window_start="2026-11-26T04:00:00+08:00",
                     window_end=scope["cycle"], stamina=31, stamina_cost=0,
                     purchase_or_refill_prompt=False, quota_remaining=1, ticket_per_attempt=0,
                     first_clear_pending=True, explicitly_selected_current_attempt=True, entry_tap_xy=[10, 10],
                     challenge_control="挑战", reviewed_story_hero_mode=True, team_and_any_assist_reviewed=True,
                     chapter_objectives=3, chapter_objective_cap=45)
        d = dict(facts=facts, guest_identity={"pid": 10}, at=at,
                 screens={x: {"captured_at": at} for x in ("primary","quota","map","stage")})
        for change in ({"reviewed_story_hero_mode": False}, {"team_and_any_assist_reviewed":False},
                       {"challenge_control": "观看"}, {"stamina_cost": 1}):
            with self.subTest(change=change), self.assertRaises(m.Blocked):
                activity_review(item,"reserve",dict(d,facts=dict(facts,**change)),None)
        activity_review(item,"reserve",d,None)
        after = dict(facts,quota_remaining=0,result="clear",no_stamina_use_verified=True, first_clear_pending=False,
                     win_objective_credited=True, within_seven_rounds_credited=True, at_most_one_allied_loss_credited=True,
                     same_hero_stage_complete_on_map=True, unlocked_stage_id="KZ-1-2", chapter_objectives=6,
                     reward_name="坍塌晶条", reward_quantity=30)
        result = dict(d, facts=after, screens={**d["screens"],"reward": {"captured_at":at}})
        for change in ({"chapter_objectives": 5}, {"unlocked_stage_id": "KZ-1-1"}, {"reward_quantity": 50},
                       {"within_seven_rounds_credited": False, "within_eight_rounds_credited": True}, {"at_most_one_allied_loss_credited": False}, {"first_clear_pending": True}):
            with self.subTest(change=change), self.assertRaises(m.Blocked):
                activity_review(item,"verify",dict(result,facts=dict(after,**change)),{"before":d})
        activity_review(item,"verify",result,{"before":d})

    def test_locked_gf2_needs_exact_guest_proof_and_continuity(self):
        from unittest.mock import patch
        item = "tea"
        r = self.review(item)
        r["desktop_state"] = "locked"
        root = self.root
        folder = root/"evidence/guest"
        folder.mkdir()
        ref = folder/"proof.json"
        ref.write_text("{}")
        with self.assertRaisesRegex(m.Blocked,"current focused guest proof"):
            self.call(item,"reserve",r)
        r["probe_proof"] = str(ref)
        ident = dict(self.binding, pid=100)
        primary = r["screens"]["primary"]
        doc = {"frame":{"path":Path(primary["path"]).relative_to(root).as_posix(),
                        "sha256":primary["sha256"]},"captured_at":primary["captured_at"],"identity":ident}
        with patch("mumu_guest.proof",return_value=doc):
            bad = self.review(item)
            bad.update({"desktop_state":"locked","probe_proof":str(ref)})
            with self.assertRaisesRegex(m.Blocked,"exact current ADB guest frame"):
                self.call(item,"reserve",bad)
            self.call(item,"reserve",r)
        r = self.review(item,seconds=2)
        r.update({"desktop_state":"unknown","probe_proof":str(ref)})
        primary = r["screens"]["primary"]
        doc = {"frame":{"path":Path(primary["path"]).relative_to(root).as_posix(),
                        "sha256":primary["sha256"]},"captured_at":primary["captured_at"],
               "identity":dict(ident,pid=101)}
        with patch("mumu_guest.proof",return_value=doc):
            with self.assertRaisesRegex(m.Blocked,"process/boot changed"):
                self.call(item,"verify",r,seconds=2)
            doc["identity"] = ident
            self.assertEqual(self.call(item,"verify",r,seconds=2)["status"],"verified")

    def test_unknown_guest_gesture_blocks_new_daily_reservation(self):
        from mumu_guest import unresolved
        from supervised_evidence import save
        path = unresolved(self.root)
        path.parent.mkdir(parents=True)
        save(path, {"status":"unknown_after_submission"})
        with self.assertRaisesRegex(m.Blocked, "previous guest input unconfirmed"):
            self.call("watering","reserve",self.review("watering"))

    def test_endfield_none_until_login_workflow_validation(self):
        with self.assertRaises(m.Blocked):
            self.call("daily-rewards", "reserve", self.review("daily-rewards", game="endfield"), game="endfield")
        self.assertFalse((self.root/"state").exists())

    def test_evidence_expired_and_stop(self):
        item = "tea"
        with self.assertRaises(m.Blocked):
            self.call(item, "reserve", self.review(item, seconds=-301))
        (self.root/"STOP").touch()
        with self.assertRaises(m.Blocked):
            self.call(item, "reserve", self.review(item))

    def test_duty_supply_distinct_and_bound_to_independent_log(self):
        item = "squad-duty-supply"
        fields = dict(product="要务补给·一", location=["班组","补给","分配中"], source="委托触发",
                      claim_all=False, selected_claim_available=True, item_reference="chosen synthetic row")
        self.call(item, "reserve", self.review(item, **fields))
        r = self.review(item, seconds=1, **fields)
        with self.assertRaises(m.Blocked):
            self.call(item, "verify", r, seconds=1)
        r["screens"]["log"] = self.frame(self.now + dt.timedelta(seconds=1))
        r["facts"]["item_reference"] = "wrong row"
        with self.assertRaises(m.Blocked):
            self.call(item, "verify", r, seconds=1)
        r["facts"]["item_reference"] = fields["item_reference"]
        self.call(item, "verify", r, seconds=1)
        self.assertIsNone(m.load_record(self.root,"gf2","squad-daily-supply",self.now))

    def test_withdraw_storage_and_production_before_breakthrough(self):
        item = "dispatch-stored-puzzle"
        fields = dict(location=["委托","每日订单","调度室"], selected_method="快速取出调度室储存情报拼图",
                      stored=5, stamina=5, stamina_capacity=10, paid_balance=7)
        with self.assertRaises(m.Blocked):
            self.call(item, "reserve", self.review(item, **dict(fields,stamina=6)))
        with self.assertRaises(m.Blocked):
            self.call("breakthrough-sweep", "reserve", self.review("breakthrough-sweep"))
        self.call(item, "reserve", self.review(item, **fields))
        with self.assertRaises(m.Blocked):
            self.call(item, "verify", self.review(item, seconds=1, **dict(fields,stored=0,stamina=9)), seconds=1)
        self.call(item, "verify", self.review(item, seconds=1, **dict(fields,stored=0,stamina=10)), seconds=1)
        with self.assertRaises(m.Blocked):
            self.call("breakthrough-sweep", "reserve", self.review("breakthrough-sweep", seconds=2), seconds=2)
        d = self.review("dispatch-production", seconds=2)
        d.update(observation="ineligible", reason="nothing_stored")
        self.call("dispatch-production", "observe", d, seconds=2)
        self.call("breakthrough-sweep", "reserve", self.review("breakthrough-sweep", seconds=3), seconds=3)
        self.assertIsNone(m.load_record(self.root,"gf2","dispatch-collect",self.now))

    def test_weekly_free_only_exact_box_and_actual_reset(self):
        item = "weekly-free-box"
        fields = dict(location=["商城","品质甄选","臻品礼包","主题精选"], product="周周乐补给箱",
                      price_text="免费", price=0, paid_balance=7, limit="周限购1/1",
                      control="购买", progress=3, goal=3)
        d = self.review(item, **fields)
        for bad in (dict(d, actual_weekly_cycle_reviewed=False),
                    dict(d, facts=dict(d["facts"], product="每日补给箱")),
                    dict(d, facts=dict(d["facts"], price=1))):
            with self.assertRaises(m.Blocked):
                self.call(item, "reserve", bad)
        self.call(item, "reserve", d)
        r = self.review(item, seconds=1, **dict(fields, remaining=0))
        r["screens"]["reward"] = self.frame(self.now + dt.timedelta(seconds=1))
        self.call(item, "verify", r, seconds=1)
        next_day = 86400
        d = self.review(item, seconds=next_day, **fields)
        with self.assertRaises(m.Blocked):
            self.call(item, "reserve", d, seconds=next_day)

    def test_observation_does_not_reserve_then_can_become_eligible(self):
        item = "prewar-signin"
        d = self.review(item)
        d.update(observation="ineligible", reason="not_yet_available")
        self.call(item, "observe", d)
        self.call(item, "reserve", self.review(item, seconds=1), seconds=1)
        self.assertEqual(m.load_record(self.root, "gf2", item, self.now)["history"][0]["reason"], "not_yet_available")


if __name__ == "__main__":
    unittest.main()
