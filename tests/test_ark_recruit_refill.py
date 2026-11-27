import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ark_recruit_refill as r


class RefillTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "pool.json"
        rows = [(6, "琴柳", [r.TOP, "支援"]), (5, "桑葚", [r.SENIOR, "医疗干员"]),
                (5, "可颂", [r.SENIOR, "重装干员", "位移"]),
                (4, "罗比菈塔", ["支援", "辅助干员"]),
                (4, "阿消", ["位移"]), (3, "米格鲁", ["重装干员", "防护"]),
                (3, "安赛尔", ["医疗干员", "治疗"]),
                (1, "机器人", [r.ROBOT, "重装干员", "防护"]),
                (2, "黑角", ["重装干员", "防护"])]
        rows.extend((3, f"合成{i}", ["辅助干员"]) for i in range(25))
        self.raw = {"operators": [{"rarity": x, "name": name, "id": f"fixture{i}", "tags": tags}
                                  for i, (x, name, tags) in enumerate(rows)]}
        self.path.write_text(json.dumps(self.raw, ensure_ascii=False), encoding="utf8")
        self.pool = r.read_pool(self.path)
        self.tags = ["重装干员", "防护", "医疗干员", "位移", r.ROBOT]

    def decide(self, tags=None, count=4):
        return r.decide(self.tags if tags is None else tags, count, self.pool, r.POLICY)

    def test_five_beats_four_and_excludes_robot(self):
        p = self.decide()
        self.assertEqual(p["minimum_stars_if_tags_hold"], 5)
        self.assertEqual(p["selected_tags"], ["重装干员", "位移"])
        self.assertEqual(p["candidates"], ["可颂"])
        self.assertFalse(p["expedite"] or p["refresh"])

    def test_five_direct_senior(self):
        p = self.decide([r.SENIOR, "防护", "医疗干员", "辅助干员", r.ROBOT])
        self.assertEqual((p["minimum_stars_if_tags_hold"], p["selected_tags"]), (5, [r.SENIOR]))

    def test_six_takes_precedence_even_with_five_or_zero_budget(self):
        for permits in (0, 4):
            p = self.decide([r.TOP, r.SENIOR, "重装干员", "位移", r.ROBOT], permits)
            self.assertEqual(p["action"], "hold-six-star")
            self.assertNotIn("selected_tags", p)

    def test_four_and_three_paths_and_budget(self):
        self.assertEqual(self.decide(["重装干员", "防护", "医疗干员", "治疗", "支援"])["selected_tags"], ["支援"])
        p = self.decide(["重装干员", "防护", "医疗干员", "治疗", r.ROBOT])
        self.assertEqual((p["minimum_stars_if_tags_hold"], p["selected_tags"]), (3, []))
        self.assertEqual(self.decide(count=0)["action"], "hold-no-permit")

    def test_rejects_ocr_duplicates_unknown_or_fake_counts(self):
        for tags, permits in ((["重装干员"] * 5, 4), (self.tags[:-1] + ["识别失败"], 4), (self.tags, True)):
            with self.subTest(tags=tags, permits=permits), self.assertRaises(r.Blocked):
                self.decide(tags, permits)

    def test_rejects_stale_or_wrong_pool(self):
        self.raw["operators"][0]["name"] = "旧表"
        self.path.write_text(json.dumps(self.raw, ensure_ascii=False), encoding="utf8")
        with self.assertRaises(r.Blocked):
            r.read_pool(self.path)

    def test_config_cannot_enable_expedite_or_six(self):
        for edit in ({"expedite": True}, {"stars": [3, 4, 5, 6]}, {"refresh": 0}, {"slots": 5}):
            cfg = self.path.parent / "policy.json"
            cfg.write_text(json.dumps({**r.POLICY, **edit}), encoding="utf8")
            with patch.object(r, "config_path", return_value=cfg), self.assertRaises(r.Blocked):
                r.read_policy()

    def test_reserve_and_verify_evidence(self):
        facts = {"slot": 1, "slot_state": "empty", "expedite_phase_ended": True, "paid_prompt": False,
                 "tags": self.tags, "permit_count": 9, "selected_tags": ["重装干员", "位移"],
                 "duration_minutes": 540, "permit_cost": 1, "lmd": 100, "quoted_lmd": 0}
        before = {"facts": facts, "screens": {"overview": {}, "confirm": {}}}
        kwargs = {"get_pool": lambda: self.pool, "get_policy": lambda: r.POLICY}
        for invalid in ({"slot": 2}, {"duration_minutes": 60}, {"paid_prompt": True},
                        {"selected_tags": ["位移"]}, {"expedite_phase_ended": False}):
            with self.subTest(invalid=invalid), self.assertRaises(r.Blocked):
                r.review_slot(1, "reserve", {**before, "facts": {**facts, **invalid}}, None, **kwargs)
        r.review_slot(1, "reserve", before, None, **kwargs)
        self.assertEqual(facts["refill_plan"]["minimum_stars_if_tags_hold"], 5)
        f = {"slot": 1, "slot_state": "running", "selected_tags": facts["selected_tags"],
             "remaining_seconds": 32389, "permit_count": 8, "lmd": 100, "refresh_or_expedite_used": False}
        after = {"facts": f, "screens": {"overview": {}}}
        with self.assertRaises(r.Blocked):
            r.review_slot(1, "verify", {**after, "facts": {**f, "permit_count": 7}}, {"before": before})
        with self.assertRaises(r.Blocked):
            r.review_slot(1, "verify", {**after, "facts": {**f, "remaining_seconds": 0}}, {"before": before})
        r.review_slot(1, "verify", after, {"before": before})

    def test_cli_is_read_only_and_reproducible(self):
        cmd = [sys.executable, str(ROOT / "scripts/ark_recruit_refill.py"), "--pool", str(self.path),
               "--permits", "4", "--tags", *self.tags]
        output = subprocess.check_output(cmd, encoding="utf8", env={**os.environ, "PYTHONUTF8": "1"})
        self.assertEqual(json.loads(output), self.decide())
