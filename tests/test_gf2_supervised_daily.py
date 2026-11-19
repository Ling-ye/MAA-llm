import contextlib
import copy
import datetime as dt
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gf2_supervised_daily as j
import gf2_daily_free_gift as gift
import gf2_squad_daily as squad
import gf2_dispatch_daily as dispatch
import gf2_heatdeath_supply as heat


class SupervisedDailyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.time = dt.datetime(2026, 11, 19, 16, 10, tzinfo=dt.timezone.utc)
        self.index = 0
        self.base = self.root / "installation"
        self.base.mkdir()
        (self.base / "interface.json").write_text('{"version":"v2.8.6"}')
        (self.base / "reviewed.json").write_bytes(b"synthetic reviewed resource")
        self.pins = {"reviewed.json": j.sha(b"synthetic reviewed resource")}

    def policy(self, original=gift.POLICY):
        return {**original, "pins": self.pins}

    def evidence(self, offset=0):
        self.index += 1
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
        data = b"\x89PNG\r\n\x1a\n"
        data += chunk(b"IHDR", struct.pack(">IIBBBBB", 1280, 720, 8, 2, 0, 0, 0))
        data += chunk(b"IDAT", zlib.compress((b"\0" + bytes([self.index % 255, 0, 0]) * 1280) * 720))
        data += chunk(b"IEND", b"")
        path = self.root / "evidence" / f"frame-{self.index}.png"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        os.utime(path, ((self.time - dt.timedelta(seconds=1)).timestamp(),) * 2)
        return {"path": str(path.relative_to(self.root)), "sha256": j.sha(data),
                "captured_at": (self.time - dt.timedelta(seconds=120 - offset)).isoformat()}

    def frame(self, phase, offset=0):
        return {"schema": 1, "game": "gf2", "phase": phase, "version": "v2.8.6",
                "game_day": j.game_day(self.time), "supervised": True,
                "reviewed_at": (self.time - dt.timedelta(seconds=1)).isoformat(),
                "evidence": self.evidence(offset),
                "window": {"hwnd": 123, "pid": 456, "title": "少女前线2：追放",
                           "executable": str(self.root / "GF2_Exilium.exe"),
                           "client_size": [1920, 1080], "foreground": True,
                           "scaled_evidence_confirmed": True}}

    def gift_frame(self, complete=False, offset=0):
        f = self.frame("daily-free-gift", offset)
        f.update(location=["商城", "品质甄选", "周期礼包", "每日礼包"],
                 selected_tab="每日补给箱", detail_product="每日补给箱", period="daily",
                 daily_free_description_confirmed=True, dialog_unambiguous=True,
                 reward_overlay_visible=False, same_detail_price_and_control=True,
                 paid_offer_selected=False, price=0, price_text="免费", currency="free",
                 balance=1000, progress=5 if complete else 4, progress_goal=21,
                 limit_text="日限购0/1" if complete else "日限购1/1",
                 remaining=0 if complete else 1, control_text="已售罄" if complete else "购买",
                 control_enabled=not complete)
        return f

    def supply_frame(self, complete=False, offset=0):
        f = self.frame("squad-daily-supply", offset)
        f.update(location=["班组", "补给"], period="daily", dust_frontline=False,
                 joined_existing_squad=True, dialog_unambiguous=True, paid_resources=False,
                 social_or_role_change=False, supply_name="每日补给·五", source_text="每日刷新",
                 selection="single_verified_item", claim_all=False, item_reference="synthetic-order",
                 identity_disambiguated=True, control_text="领取", control_enabled=not complete,
                 selected_item_claimed=complete, unclaimed_daily_items=0 if complete else 1,
                 green_check=complete, current_day_claim_record_visible=complete)
        return f

    def duty_frame(self, complete=False, offset=0):
        f = self.frame("squad-daily-duty", offset)
        f.update(location=["班组", "要务"], period="daily", dust_frontline=False,
                 joined_existing_squad=True, dialog_unambiguous=True, paid_resources=False,
                 social_or_role_change=False, duty_name="每日要务IV", enemy_level=39,
                 objective="全部歼灭", battle_state="not_started", control_text="开始作战",
                 entry_cost_reviewed_free=True, fee_or_currency_prompt=False, daily_completed_banner=False)
        if complete:
            f.update(battle_state="completed", daily_completed_banner="每日要务已完成",
                     result_text="任务完成", result_stage="DW-4 每日要务IV", reward_confirmed=True,
                     deployed_count=5, deployed_capacity=5, formation_supervised=True,
                     supporting_evidence={"deployment": self.evidence(20),
                                          "battle_result": self.evidence(40), "reward": self.evidence(60)})
        return f

    def reserve(self, frame, policy=None, inspect=None):
        return j.record_action(self.root, policy or self.policy(), "reserve", frame, self.base,
                               frame["window"]["executable"], moment=self.time,
                               inspect_window=inspect or (lambda: copy.deepcopy(frame["window"])))

    def manual(self, before, after, policy=None):
        return j.record_action(self.root, policy or self.policy(), "record-manual",
                               {"source": "external_supervisor", "before": before, "after": after},
                               moment=self.time)

    def test_preview_has_no_io_or_game_backend(self):
        with patch.object(j, "record_action", side_effect=AssertionError("mutation")), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(j.cli(self.root, self.policy(), []), 0)
        self.assertFalse(json.loads(out.getvalue())["automatic_execution"])
        self.assertFalse((self.root / "state").exists())

    def test_execute_always_blocks_before_state_or_input(self):
        with patch.object(j, "record_action", side_effect=AssertionError("mutation")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(j.cli(self.root, self.policy(), ["--execute"]), 2)
        self.assertFalse((self.root / "state").exists())

    def test_reservation_is_durable_and_never_claims_execution(self):
        f = self.gift_frame()
        r = self.reserve(f)
        self.assertEqual(r["status"], "manual_submission_reserved")
        self.assertFalse(r["script_executed_game_action"])
        self.assertTrue(j.ledger_path(self.root, "daily-free-gift", self.time).exists())

    def test_paid_same_position_and_stale_free_label_rejected(self):
        for change in ({"selected_tab": "每日晶条礼包"}, {"detail_product": "每日晶条礼包"},
                       {"price": 6, "price_text": "¥6", "currency": "CNY"}, {"paid_offer_selected": True},
                       {"same_detail_price_and_control": False}):
            with self.subTest(change=change):
                f = self.gift_frame()
                f.update(change)
                with self.assertRaises(j.Blocked):
                    self.reserve(f)

    def test_weekly_event_or_unbound_free_word_rejected(self):
        for change in ({"period": "weekly"}, {"period": "event"}, {"detail_product": "周周乐补给箱"},
                       {"price_text": "FREE elsewhere"}, {"price_text": "¥0"}, {"price": False},
                       {"currency": "unknown"}, {"dialog_unambiguous": False}, {"reward_overlay_visible": True}):
            with self.subTest(change=change):
                f = self.gift_frame()
                f.update(change)
                with self.assertRaises(j.Blocked):
                    gift.validate(f, "ready")

    def test_already_claimed_cannot_reserve(self):
        with self.assertRaises(j.Blocked):
            self.reserve(self.gift_frame(True))

    def test_observe_already_claimed_blocks_another_attempt(self):
        j.record_action(self.root, self.policy(), "observe", self.gift_frame(True), moment=self.time)
        with self.assertRaises(j.Blocked):
            self.reserve(self.gift_frame())

    def test_double_reservation_rejected(self):
        f = self.gift_frame()
        self.reserve(f)
        with self.assertRaises(j.Blocked):
            self.reserve(f)

    def test_foreground_switch_rejected(self):
        f = self.gift_frame()
        other = {**f["window"], "pid": 789}
        with self.assertRaises(j.Blocked):
            self.reserve(f, inspect=lambda: other)

    def test_foreground_switch_between_checks_rejected(self):
        f = self.gift_frame()
        reads = iter([f["window"], {**f["window"], "hwnd": 987}])
        with self.assertRaises(j.Blocked):
            self.reserve(f, inspect=lambda: next(reads))

    def test_other_executable_or_title_rejected(self):
        f = self.gift_frame()
        for field, value in (("title", "少女前线2自动化"), ("executable", str(self.root / "other.exe")),
                             ("foreground", False), ("client_size", [800, 600])):
            with self.subTest(field=field):
                with self.assertRaises(j.Blocked):
                    self.reserve(f, inspect=lambda: {**f["window"], field: value})

    def test_stale_before_evidence_rejected(self):
        f = self.gift_frame()
        f["evidence"]["captured_at"] = (self.time - dt.timedelta(minutes=6)).isoformat()
        with self.assertRaisesRegex(j.Blocked, "stale"):
            self.reserve(f)

    def test_hash_tamper_rejected(self):
        f = self.gift_frame()
        (self.root / f["evidence"]["path"]).write_bytes(b"changed")
        with self.assertRaises(j.Blocked):
            self.reserve(f)

    def test_evidence_path_escape_rejected(self):
        f = self.gift_frame()
        f["evidence"]["path"] = "../outside.png"
        with self.assertRaises(j.Blocked):
            self.reserve(f)

    def test_stop_blocks_reservation(self):
        (self.root / "STOP").touch()
        with self.assertRaises(j.Blocked):
            self.reserve(self.gift_frame())

    def test_wrong_install_version_rejected(self):
        (self.base / "interface.json").write_text('{"version":"v2.8.4"}')
        with self.assertRaises(j.Blocked):
            self.reserve(self.gift_frame())

    def test_resource_tamper_rejected(self):
        (self.base / "reviewed.json").write_bytes(b"changed")
        with self.assertRaises(j.Blocked):
            self.reserve(self.gift_frame())

    def test_shared_lock_blocks_reservation(self):
        with j.pipeline_lock(self.root):
            with self.assertRaises(j.Blocked):
                self.reserve(self.gift_frame())

    def test_unknown_submission_never_replays_or_overwrites(self):
        f = self.gift_frame()
        self.reserve(f)
        r = j.record_action(self.root, self.policy(), "mark-unknown", reason="connection lost", moment=self.time)
        self.assertEqual(r["status"], "submission_unknown")
        for action in ("reserve", "verify", "record-manual", "observe"):
            with self.subTest(action=action):
                with self.assertRaises(j.Blocked):
                    j.record_action(self.root, self.policy(), action, self.gift_frame(True, 80),
                                    self.base, f["window"]["executable"], moment=self.time)

    def test_supervised_before_after_is_manual_only(self):
        r = self.manual(self.gift_frame(), self.gift_frame(True, 80))
        self.assertEqual(r["status"], "manual_completion_recorded")
        self.assertFalse(r["script_executed_game_action"])
        self.assertFalse(r["automation_live_validated"])
        self.assertEqual(len(r["events"]), 1)

    def test_manual_record_requires_explicit_source(self):
        with self.assertRaises(j.Blocked):
            j.record_action(self.root, self.policy(), "record-manual",
                            {"before": self.gift_frame(), "after": self.gift_frame(True, 80)}, moment=self.time)

    def test_changed_balance_or_wrong_progress_rejected(self):
        before = self.gift_frame()
        for change in ({"balance": 994}, {"progress": 4}, {"progress": 6}):
            after = self.gift_frame(True, 80)
            after.update(change)
            with self.subTest(change=change), self.assertRaises(j.Blocked):
                self.manual(before, after)

    def test_reused_after_image_rejected(self):
        before = self.gift_frame()
        after = self.gift_frame(True, 80)
        after["evidence"] = before["evidence"]
        with self.assertRaises(j.Blocked):
            self.manual(before, after)

    def test_ledger_tamper_rejected(self):
        self.reserve(self.gift_frame())
        p = j.ledger_path(self.root, "daily-free-gift", self.time)
        data = json.loads(p.read_text(encoding="utf8"))
        data["status"] = "manual_completion_recorded"
        p.write_text(json.dumps(data), encoding="utf8")
        with self.assertRaises(j.Blocked):
            j.read_ledger(p, "daily-free-gift", self.time)

    def test_game_day_uses_beijing_four_am(self):
        self.assertEqual(j.game_day(dt.datetime(2026, 11, 19, 19, 59, tzinfo=dt.timezone.utc)), "2026-11-19")
        self.assertEqual(j.game_day(dt.datetime(2026, 11, 19, 20, 0, tzinfo=dt.timezone.utc)), "2026-11-20")
        with self.assertRaises(j.Blocked):
            j.game_day(dt.datetime(2026, 11, 19))

    def test_wrong_phase_and_date_rejected(self):
        for key, value in (("phase", "squad-daily-supply"), ("game_day", "2026-11-18"), ("version", "v2.8.4")):
            f = self.gift_frame()
            f[key] = value
            with self.subTest(key=key), self.assertRaises(j.Blocked):
                self.reserve(f)

    def test_supply_single_daily_item_and_receipt(self):
        p = self.policy(squad.POLICIES["supply"])
        r = self.manual(self.supply_frame(), self.supply_frame(True, 80), p)
        self.assertEqual(r["phase"], "squad-daily-supply")

    def test_supply_frontline_claim_all_or_duplicate_identity_rejected(self):
        for change in ({"dust_frontline": True}, {"source_text": "尘烟前线"}, {"claim_all": True},
                       {"identity_disambiguated": False}, {"joined_existing_squad": False},
                       {"social_or_role_change": True}, {"paid_resources": True}):
            f = self.supply_frame()
            f.update(change)
            with self.subTest(change=change), self.assertRaises(j.Blocked):
                squad.supply(f, "ready")

    def test_supply_absent_button_is_not_completion(self):
        after = self.supply_frame(True, 80)
        after["green_check"] = False
        with self.assertRaises(j.Blocked):
            squad.supply(after, "completed")

    def test_supply_different_item_rejected(self):
        before = self.supply_frame()
        after = self.supply_frame(True, 80)
        after["item_reference"] = "another-item"
        with self.assertRaises(j.Blocked):
            self.manual(before, after, self.policy(squad.POLICIES["supply"]))

    def test_three_scopes_have_independent_ledgers(self):
        self.manual(self.gift_frame(), self.gift_frame(True, 80))
        self.manual(self.supply_frame(), self.supply_frame(True, 80), self.policy(squad.POLICIES["supply"]))
        self.manual(self.duty_frame(), self.duty_frame(True, 80), self.policy(squad.POLICIES["duty"]))
        self.assertEqual(len(list((self.root / "state").glob("*.attempt.json"))), 3)

    def test_duty_requires_exact_tier_free_entry_and_objective(self):
        for change in ({"duty_name": "每日要务V"}, {"enemy_level": 40}, {"objective": "其他"},
                       {"entry_cost_reviewed_free": False}, {"fee_or_currency_prompt": True},
                       {"battle_state": "in_progress"}, {"control_text": "作战开始"}):
            f = self.duty_frame()
            f.update(change)
            with self.subTest(change=change), self.assertRaises(j.Blocked):
                squad.duty(f, "ready")

    def test_duty_reward_alone_does_not_complete(self):
        f = self.duty_frame(True, 80)
        f["daily_completed_banner"] = False
        with self.assertRaises(j.Blocked):
            squad.duty(f, "completed")

    def test_duty_missing_result_evidence_rejected(self):
        f = self.duty_frame(True, 80)
        del f["supporting_evidence"]["battle_result"]
        with self.assertRaises(j.Blocked):
            self.manual(self.duty_frame(), f, self.policy(squad.POLICIES["duty"]))

    def test_duty_supporting_evidence_tamper_rejected(self):
        f = self.duty_frame(True, 80)
        f["supporting_evidence"]["reward"]["sha256"] = "0" * 64
        with self.assertRaises(j.Blocked):
            self.manual(self.duty_frame(), f, self.policy(squad.POLICIES["duty"]))

    def test_duty_step_order_and_replay(self):
        policy = self.policy(squad.POLICIES["duty"])
        before = self.duty_frame()
        self.reserve(before, policy)
        deployment = self.duty_frame(offset=20)
        deployment.update(battle_state="deployment", control_text="作战开始",
                          deployed_count=5, deployed_capacity=5, formation_supervised=True)
        running = self.duty_frame(offset=40)
        running.update(battle_state="in_progress", battle_running_observed=True)
        with self.assertRaises(j.Blocked):
            j.record_action(self.root, policy, "record-step", running, moment=self.time, step="in_progress")
        r = j.record_action(self.root, policy, "record-step", deployment, moment=self.time, step="deployment")
        self.assertEqual(r["status"], "deployment_recorded")
        with self.assertRaises(j.Blocked):
            j.record_action(self.root, policy, "record-step", deployment, moment=self.time, step="deployment")
        r = j.record_action(self.root, policy, "record-step", running, moment=self.time, step="in_progress")
        self.assertEqual(r["status"], "in_progress_recorded")
        with self.assertRaises(j.Blocked):
            self.reserve(before, policy)

    def test_duty_unknown_in_progress_is_terminal(self):
        policy = self.policy(squad.POLICIES["duty"])
        self.reserve(self.duty_frame(), policy)
        j.record_action(self.root, policy, "mark-unknown", reason="interrupted before result", moment=self.time)
        with self.assertRaises(j.Blocked):
            j.record_action(self.root, policy, "verify", self.duty_frame(True, 80), moment=self.time)

    def test_duty_step_cannot_resume_after_original_evidence_changes(self):
        policy = self.policy(squad.POLICIES["duty"])
        before = self.duty_frame(); self.reserve(before, policy)
        (self.root / before["evidence"]["path"]).write_bytes(b"changed")
        deployment = self.duty_frame(offset=20)
        deployment.update(battle_state="deployment", control_text="作战开始",
                          deployed_count=5, deployed_capacity=5, formation_supervised=True)
        with self.assertRaises(j.Blocked):
            j.record_action(self.root, policy, "record-step", deployment, moment=self.time, step="deployment")

    def dispatch_frame(self, phase="collect", complete=False, offset=0):
        f = self.frame("dispatch-" + phase, offset)
        f.update(location=["公共区", "调度室"], dialog_unambiguous=True, paid_speedup=False,
                 team_changes=False, intelligence_storage=False, resource_production=False,
                 mystery_box=False, weekly_goal=25, weekly_count=20 if complete else 15,
                 dispatch_currency=1500 if complete else 1000, missions=sorted(dispatch.MISSIONS),
                 existing_teams_reviewed=True, completed_teams=5, control_text="一键领取",
                 control_enabled=True, dispatch_state="completed_unclaimed")
        if phase == "collect" and complete:
            f.update(dispatch_state="result", panel_title="派遣完成", control_text="再次派遣",
                     collected_teams=5, all_five_results_supervised=True,
                     supporting_evidence={"post_room": self.evidence(90)})
        if phase == "redispatch":
            f.update(same_original_teams=True, configuration_unchanged=True, dispatch_currency=1500,
                     no_cost_prompt=True, dispatch_state="result", panel_title="派遣完成", control_text="再次派遣")
            if complete:
                f.update(dispatch_state="in_progress", running_teams=5, capacity=5, claim_available=False,
                         countdown_by_mission={name: "19小时59分" for name in dispatch.MISSIONS})
        return f

    def weekly_frame(self, tier=25, state="locked", count=20, offset=0):
        p = dispatch.weekly_policy(tier, self.time)
        f = self.frame(p["phase"], offset)
        f.update(location=["公共区", "调度室"], dialog_unambiguous=True, paid_speedup=False,
                 team_changes=False, intelligence_storage=False, resource_production=False,
                 mystery_box=False, weekly_goal=25, weekly_count=count, panel_title="本周派遣收益",
                 period_key=p["period_key"], tier=tier, same_tier_control_confirmed=True,
                 tier_state=state, control_text="领取" if state == "claimable" else "未完成",
                 control_enabled=state == "claimable", green_check=state == "claimed")
        return f

    def test_dispatch_collection_and_redispatch_are_separate(self):
        self.manual(self.dispatch_frame(), self.dispatch_frame(complete=True, offset=80),
                    self.policy(dispatch.POLICIES["collect"]))
        self.manual(self.dispatch_frame("redispatch"), self.dispatch_frame("redispatch", True, 80),
                    self.policy(dispatch.POLICIES["redispatch"]))
        self.assertEqual(len(list((self.root / "state").glob("*.attempt.json"))), 2)

    def test_dispatch_wrong_public_area_paths_rejected(self):
        for change in ({"intelligence_storage": True}, {"resource_production": True},
                       {"mystery_box": True}, {"paid_speedup": True}, {"team_changes": True}):
            f = self.dispatch_frame()
            f.update(change)
            with self.subTest(change=change), self.assertRaises(j.Blocked):
                dispatch.collect(f, "ready")

    def test_running_dispatch_cannot_be_collected_again(self):
        f = self.dispatch_frame()
        f["dispatch_state"] = "in_progress"
        with self.assertRaises(j.Blocked):
            dispatch.collect(f, "ready")

    def test_redispatch_preserves_existing_teams(self):
        f = self.dispatch_frame("redispatch")
        f["same_original_teams"] = False
        with self.assertRaises(j.Blocked):
            dispatch.redispatch(f, "ready")

    def test_redispatch_requires_every_countdown(self):
        f = self.dispatch_frame("redispatch", True, 80)
        f["countdown_by_mission"].pop(next(iter(dispatch.MISSIONS)))
        with self.assertRaises(j.Blocked):
            dispatch.redispatch(f, "completed")

    def test_redispatch_hidden_before_balance_is_not_false_delta_proof(self):
        before = self.dispatch_frame("redispatch")
        before.update(dispatch_currency=None, currency_not_visible=True)
        r = self.manual(before, self.dispatch_frame("redispatch", True, 80),
                        self.policy(dispatch.POLICIES["redispatch"]))
        self.assertFalse(r["after"]["resource_delta_verified"])

    def test_locked_weekly_observation_does_not_consume_attempt(self):
        p = self.policy(dispatch.weekly_policy(25, self.time))
        j.record_action(self.root, p, "observe-pending", self.weekly_frame(), moment=self.time)
        self.assertFalse(j.ledger_path(self.root, p["phase"], self.time, p["period_key"]).exists())
        f = self.weekly_frame(state="claimable", count=25)
        self.reserve(f, p)
        self.assertTrue(j.ledger_path(self.root, p["phase"], self.time, p["period_key"]).exists())

    def test_claimed_lower_tier_does_not_block_later_tier(self):
        for tier in (5, 10, 15):
            p = self.policy(dispatch.weekly_policy(tier, self.time))
            j.record_action(self.root, p, "observe", self.weekly_frame(tier, "claimed"), moment=self.time)
        p = self.policy(dispatch.weekly_policy(25, self.time))
        self.reserve(self.weekly_frame(25, "claimable", 25), p)

    def test_claimed_tier_cannot_replay_next_day_same_week(self):
        p = self.policy(dispatch.weekly_policy(5, self.time))
        j.record_action(self.root, p, "observe", self.weekly_frame(5, "claimed"), moment=self.time)
        self.time += dt.timedelta(days=1)
        p = self.policy(dispatch.weekly_policy(5, self.time))
        with self.assertRaises(j.Blocked):
            self.reserve(self.weekly_frame(5, "claimable"), p)

    def test_new_calendar_week_does_not_automatically_unlock_claim(self):
        p = self.policy(dispatch.weekly_policy(5, self.time))
        j.record_action(self.root, p, "observe", self.weekly_frame(5, "claimed"), moment=self.time)
        self.time += dt.timedelta(days=7)
        p = self.policy(dispatch.weekly_policy(5, self.time))
        with self.assertRaises(j.Blocked):
            self.reserve(self.weekly_frame(5, "claimable"), p)

    def test_new_week_requires_fresh_explicit_zero_progress_reset(self):
        p = self.policy(dispatch.weekly_policy(5, self.time))
        j.record_action(self.root, p, "observe", self.weekly_frame(5, "claimed"), moment=self.time)
        self.time += dt.timedelta(days=7)
        p = self.policy(dispatch.weekly_policy(25, self.time))
        f = self.weekly_frame(count=0)
        f.update(cycle_reset_reviewed=True, claimed_tiers=[])
        j.record_action(self.root, p, "observe-pending", f, moment=self.time)
        data = json.loads((self.root / "state/gf2-dispatch-weekly-period.json").read_text())
        self.assertEqual(data["period_key"], p["period_key"])
        self.assertTrue(data["reset_reviewed"])

    def test_weekly_wrong_panel_or_unfinished_tier_rejected(self):
        p = dispatch.weekly_policy(25, self.time)
        for change in ({"panel_title": "调度收益"}, {"panel_title": "调度考核"},
                       {"tier": 15}, {"same_tier_control_confirmed": False}):
            f = self.weekly_frame(25, "claimable", 25)
            f.update(change)
            with self.subTest(change=change), self.assertRaises(j.Blocked):
                p["validate"](f, "ready")
        with self.assertRaises(j.Blocked):
            p["validate"](self.weekly_frame(), "ready")

    def test_weekly_unknown_submission_never_replays(self):
        p = self.policy(dispatch.weekly_policy(25, self.time))
        self.reserve(self.weekly_frame(25, "claimable", 25), p)
        j.record_action(self.root, p, "mark-unknown", reason="unknown weekly submission", moment=self.time)
        with self.assertRaises(j.Blocked):
            self.reserve(self.weekly_frame(25, "claimable", 25), p)

    def test_pending_status_uses_bound_observation_receipt(self):
        p = self.policy(dispatch.weekly_policy(25, self.time))
        j.record_action(self.root, p, "observe-pending", self.weekly_frame(), moment=self.time)
        with patch.object(j, "now", return_value=self.time):
            self.assertEqual(j.status(self.root, p)["status"], "pending_observed")
        with patch.object(j, "now", return_value=self.time + dt.timedelta(days=1)):
            self.assertEqual(j.status(self.root, p)["status"], "not_recorded")

    def test_evidence_tamper_blocks_status(self):
        before, after = self.gift_frame(), self.gift_frame(True, 80)
        self.manual(before, after)
        (self.root / after["evidence"]["path"]).write_bytes(b"changed")
        with patch.object(j, "now", return_value=self.time), self.assertRaises(j.Blocked):
            j.status(self.root, self.policy())

    def heat_frame(self, complete=False, offset=0):
        f = self.frame(heat.POLICY["phase"], offset)
        f.update(event=heat.EVENT, mode="物资模式", event_end=heat.END.isoformat(), dialog_unambiguous=True,
                 currency="准入密钥", key_scope="event_supply_only", key_inventory_cap=6,
                 keys=0 if complete else 3, refill=False, exchange=False, ordinary_stamina_spent=False,
                 paid_currency_spent=False, challenge_or_story=False, stage_id="DF-1-5", stage_name="于乱流中 V",
                 highest_unlocked_reviewed=True, all_three_objectives_complete=True, event_state="open")
        if complete:
            f.update(batch_state="completed", completed_runs=3, reward_name="火控残片", reward_quantity=2400,
                     reward_inventory=4000, supporting_evidence={"reward": self.evidence(40), "reward_name": self.evidence(60)})
        else:
            f.update(panel_title="自律准备", control_text="确认", control_enabled=True, selected_runs=3,
                     ui_max_runs=3, cost_per_run=1, total_key_cost=3, same_confirmation_cost_and_count=True,
                     supporting_evidence={"event_home": self.evidence(-60), "stage": self.evidence(-40),
                                          "key_details": self.evidence(-20)})
        return f

    def test_event_complete_manual_batch_is_not_script_execution(self):
        r = self.manual(self.heat_frame(), self.heat_frame(True, 80), self.policy(heat.POLICY))
        self.assertEqual(r["after"]["keys"], 0)
        self.assertFalse(r["script_executed_game_action"])

    def test_event_rejects_other_modes_stages_and_currencies(self):
        for change in ({"event": "其他活动"}, {"mode": "挑战模式"}, {"stage_id": "DF-1-4"},
                       {"currency": "情报"}, {"key_scope": "stamina"}, {"highest_unlocked_reviewed": False}):
            f = self.heat_frame(); f.update(change)
            with self.subTest(change=change), self.assertRaises(j.Blocked):
                heat.validate(f, "ready")

    def test_event_refill_exchange_and_ordinary_stamina_rejected(self):
        for field in ("refill", "exchange", "ordinary_stamina_spent", "paid_currency_spent", "challenge_or_story"):
            f = self.heat_frame(); f[field] = True
            with self.subTest(field=field), self.assertRaises(j.Blocked):
                heat.validate(f, "ready")

    def test_event_count_and_same_confirmation_cost_must_match(self):
        for change in ({"keys": 2}, {"total_key_cost": 4}, {"cost_per_run": True}, {"selected_runs": True},
                       {"ui_max_runs": 2}, {"keys": 7}, {"same_confirmation_cost_and_count": False}):
            f = self.heat_frame(); f.update(change)
            with self.subTest(change=change), self.assertRaises(j.Blocked):
                heat.validate(f, "ready")

    def test_event_zero_keys_skips_without_consuming_attempt(self):
        f = self.heat_frame(); f.update(keys=0, no_keys_reviewed=True)
        p = self.policy(heat.POLICY)
        r = j.record_action(self.root, p, "observe-pending", f, moment=self.time)
        self.assertEqual(r["status"], "pending_observed")
        self.assertFalse(j.ledger_path(self.root, p["phase"], self.time).exists())
        with self.assertRaises(j.Blocked):
            heat.validate(f, "ready")

    def test_event_closed_is_explicit_skip_unknown_stops(self):
        f = self.heat_frame(); f.update(event_state="closed", closed_entry_reviewed=True)
        heat.pending(f)
        f["event_state"] = "unknown"
        with self.assertRaises(j.Blocked): heat.pending(f)

    def test_event_shop_deadline_never_authorizes_combat(self):
        f = self.heat_frame(); f["event_end"] = heat.SHOP_END
        with self.assertRaises(j.Blocked): heat.validate(f, "ready")
        for moment in (heat.END, heat.END + dt.timedelta(days=1)):
            with self.subTest(moment=moment), self.assertRaises(j.Blocked):
                j.record_action(self.root, self.policy(heat.POLICY), "reserve", self.heat_frame(),
                                self.base, self.root / "GF2_Exilium.exe", moment=moment)

    def test_event_evidence_after_close_rejected(self):
        f = self.heat_frame(); f["evidence"]["captured_at"] = heat.END.isoformat()
        with self.assertRaises(j.Blocked): heat.validate(f, "ready")

    def test_event_requires_context_and_reward_evidence(self):
        f = self.heat_frame(); del f["supporting_evidence"]["key_details"]
        with self.assertRaises(j.Blocked): heat.validate(f, "ready")
        f = self.heat_frame(True, 80); del f["supporting_evidence"]["reward"]
        with self.assertRaises(j.Blocked): heat.validate(f, "completed")

    def test_event_batch_outcome_mismatch_rejected(self):
        for change in ({"completed_runs": 2}, {"keys": 1}, {"reward_name": "其他"}):
            after = self.heat_frame(True, 80); after.update(change)
            with self.subTest(change=change), self.assertRaises(j.Blocked):
                self.manual(self.heat_frame(), after, self.policy(heat.POLICY))

    def test_event_unknown_submission_blocks_replay(self):
        p = self.policy(heat.POLICY); before = self.heat_frame()
        self.reserve(before, p)
        j.record_action(self.root, p, "mark-unknown", reason="batch outcome unknown", moment=self.time)
        with self.assertRaises(j.Blocked): self.reserve(before, p)

    def test_event_reservation_rejects_stale_supporting_context(self):
        before = self.heat_frame()
        before["supporting_evidence"]["event_home"]["captured_at"] = (self.time - dt.timedelta(minutes=6)).isoformat()
        with self.assertRaisesRegex(j.Blocked, "stale"):
            self.reserve(before, self.policy(heat.POLICY))

    def test_audit_distinguishes_missing_manual_and_pending_scopes(self):
        import gf2_daily_additions_audit as a
        self.manual(self.gift_frame(), self.gift_frame(True, 80))
        p = self.policy(dispatch.weekly_policy(25, self.time))
        j.record_action(self.root, p, "observe-pending", self.weekly_frame(), moment=self.time)
        with patch.object(j, "now", return_value=self.time):
            report = a.audit(self.root)
        by = {x["phase"]: x for x in report["stages"]}
        self.assertEqual(by["daily-free-gift"]["status"], "manual_completion_recorded")
        self.assertEqual(by["dispatch-weekly-25"]["status"], "pending_observed")
        self.assertFalse(report["all_requested_scopes_recorded"])
        self.assertFalse(report["live_state_checked"])


if __name__ == "__main__":
    unittest.main()
