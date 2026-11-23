import datetime as dt
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

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
        scope, results = m.ITEMS[game][item]
        f = dict.fromkeys((scope + " " + results + " current_exact_item_eligible prior_completion_visually_confirmed exact_ineligibility_visually_confirmed").split(), True)
        f.update(specific)
        d = dict.fromkeys("""supervised exact_mumu_instance_reviewed adb_device official_package_reviewed decoded_fresh_guest_frame no_unhandled_prompt cross_transport_history_reviewed correct_account_home_reviewed expected_foreground_package_reviewed actual_weekly_cycle_reviewed""".split(), True)
        d.update(game=game, item=item, day=m.game_day(at), transport="mumu", package=m.PACKAGES[game],
                 maa_version=m.VERSIONS[game], desktop_state="unlocked",
                 reviewed_period=m.period(item, at), screens={"primary": self.frame(at)}, facts=f, **self.binding)
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
