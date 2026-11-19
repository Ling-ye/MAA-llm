import copy, datetime as dt, hashlib, json, os, struct, sys, tempfile, time, unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import endfield_extras as e
import endfield_extra_audit as audit

class ExtraTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/"state").mkdir();(self.root/"evidence").mkdir()
        self.png=self.root/"evidence/proof.png"
        self.png.write_bytes(b"\x89PNG\r\n\x1a\n"+b"\0"*8+struct.pack("!II",1280,720)+b"fixture")
    def plan(self,phase="gifts",region="valleyiv",unit="breeze_of_kjersch",cycle=0,**kw):
        return e.make_plan(phase,region,unit,cycle,**kw)
    def review(self,plan,**kw):
        r={k:plan[k] for k in ("game_day","phase","region","unit","cycle")}
        r.update(supervised=True,reviewed_at=e.now(),evidence=e.evidence(self.png,root=self.root),
            quantity=10,unit_price=6000,balance=1000000,currency="ValleyIVStockBills",discount="-80%",
            cargo_checked=True,item_name="reviewed resource",transfer_available=True,stock_quantity=100000,cargo_capacity=100,item_volume=10,order_state="ready_to_pack",order_reference="visible depot cargo",orders=[{"order_reference":"existing transfer","state":"pending_acceptance","expiry_text":"reviewed expiry"}])
        r.update(kw);return r
    def merged(self,plan):
        merged={}
        for p in json.loads(plan["tasks"][0]["pipeline_override"]):
            for k,v in p.items():merged.setdefault(k,{}).update(v)
        return merged
    def fake_capture(self,instance,target,*args,**kw):
        Path(target).write_bytes(self.png.read_bytes());return e.evidence(target,root=self.root)
    def run_fake(self,plan,review,fail=False):
        plan=self.plan(plan["phase"],plan["region"],plan["unit"],plan["cycle"],review=review)
        if plan["phase"]=="delivery":
            tail=self.plan("tail",plan["region"],None)
            e.observe(tail,self.review(tail,outcome="pending_acceptance"),self.root)
        ident=plan["tasks"][0]["selected_task_id"];calls=[]
        state={"is_running":False,"task_run_state":{"overall_status":"Succeeded","pending_task_ids":[17],
            "mappings":{"17":ident},"statuses":{ident:"succeeded"}}}
        def api(path,body=None,**kw):
            calls.append(path)
            if path.endswith("/tasks/start"):
                if fail:raise TimeoutError("ambiguous submission")
                return {"taskIds":[17]}
            if path=="/maa/state":return {"instances":{plan["instance"]:state}}
            return {}
        with ExitStack() as s:
            for name,value in [("execution_enabled",lambda:None),("checked_manifest",lambda:{}),
                ("live_versions",lambda api:None),("idle_states",lambda api:{plan["instance"]:{"connected":True,"resource_loaded":True}}),
                ("capture",self.fake_capture),("log_position",lambda:0),("collect_log",lambda *a:""),
                ("task_body",lambda tasks,m:{"tasks":tasks}),("check_stop",lambda:None)]:
                s.enter_context(patch.object(e,name,value))
            s.enter_context(patch.object(e.time,"sleep",lambda _:None))
            result,code=e.execute(plan,review,api,root=self.root)
        return result,code,calls,plan
    def test_policy_hash(self):self.assertEqual(len(e.policy()["gifts"]),7)
    def test_scope_requires_region_and_depot(self):
        for args in [("delivery",None,None),("gifts","wuling","breeze_of_kjersch"),("tail",None,None),("credit-buy",None,"TCreds")]:
            with self.assertRaises(ValueError):e.make_plan(*args)
    def test_preview_has_no_api(self):
        with patch.object(e,"request",side_effect=AssertionError("API")):
            self.assertTrue(self.plan()["supervision_required"])
    def test_gift_only_exact_discount_and_one_confirmation(self):
        p=self.merged(self.plan())
        self.assertEqual(p["AutoStockInStapleItemDiscountsValleyIVCultural"]["recognition"]["param"]["expected"],["-80"])
        self.assertEqual(p["AutoStockStapleQuantityControlConfirmBuy"]["max_hit"],1)
        self.assertFalse(p["AutoStockBuyItemValleyIVTaskDaily"]["enabled"])
        self.assertEqual(sum(bool(v) for v in p["AutoStockInStapleItemNameCultural"]["attach"].values()),1)
    def test_each_depot_transfer_only(self):
        for region,depots in e.policy()["depots"].items():
            for unit in depots:
                p=self.merged(self.plan("delivery",region,unit))
                self.assertEqual(p["DeliveryJobsDecideQuickTransfer"]["next"],["DeliveryJobsQuickTransfer"])
                self.assertEqual(p["DeliveryJobsOngoingDeliveryFor"+unit]["next"],["DeliveryJobsTransferOngoingJob"])
                for name in e.policy()["blocked_auto_delivery"]:self.assertFalse(p[name]["enabled"])
    def test_transfer_does_not_fallback_to_accept(self):
        p=self.merged(self.plan("delivery","valleyiv","OriginLodespring"))
        self.assertFalse(p["DeliveryJobsRedistributionBidNextStep"]["enabled"])
        self.assertEqual(p["DeliveryJobsTransferOngoingJob"]["next"],["DeliveryJobsClickTransferJob"])
    def test_tail_is_claim_only(self):
        p=self.plan("tail","wuling",None);text=json.dumps(p)
        self.assertIn("ClaimDeliveryJobsClickMyTransferredTab",text)
        self.assertNotIn("DeliveryJobsCargoFillToMax",text)
    def test_recycle_one_region(self):
        for region in ("valleyiv","wuling"):
            p=self.merged(self.plan("recycle",region,None))
            self.assertEqual(p["ResourceRecycleStationWulingSub"]["enabled"],region=="wuling")
    def test_credit_claim_cannot_shop(self):
        p=self.merged(self.plan("credit-claim",None,None))
        self.assertEqual(p["CreditShoppingClaimConfirmClick"]["next"],["DotExtraEnd"])
        self.assertFalse(p["CreditShoppingBuyPriority1"]["enabled"])
    def test_credit_gacha_only_and_all_fallbacks_disabled(self):
        for unit in ("Oroberyl","ArsenalTicket"):
            p=self.merged(self.plan("credit-buy",None,unit))
            for node in e.CREDIT_STOP:self.assertFalse(p[node]["enabled"])
            self.assertEqual(p["CreditShoppingBuyPriority1"]["max_hit"],1)
            self.assertEqual(p["CreditShoppingClaimConfirmClick"]["next"],["DotExtraEnd"])
    def test_credit_exact_price_guard(self):
        plan=self.plan("credit-buy",None,"Oroberyl");rev=self.review(plan,price=300,balance=500,currency="Credits")
        p=self.merged(self.plan("credit-buy",None,"Oroberyl",review=rev))
        self.assertIn("==300",p["DotCreditExactPrice"]["custom_recognition_param"]["expression"])
        self.assertIn("DotCreditExactPrice",p["CreditShoppingBuyConfirm"]["recognition"]["param"]["all_of"])
    def test_refresh_is_single_and_no_purchase(self):
        p=self.merged(self.plan("credit-refresh",None,None,0))
        self.assertEqual(p["DotRefreshOne"]["max_hit"],1)
        self.assertEqual(p["CreditShoppingShopping"]["next"],["DotExtraEnd"])
        self.assertFalse(p["CreditShoppingRefreshCountReached"]["enabled"])
    def test_refresh_max_four(self):
        with self.assertRaises(ValueError):self.plan("credit-refresh",None,None,4)
    def test_review_requires_supervision(self):
        p=self.plan()
        with self.assertRaises(ValueError):e.validate_review(p,self.review(p,supervised=False),self.root)
    def test_review_wrong_day(self):
        p=self.plan()
        with self.assertRaises(ValueError):e.validate_review(p,self.review(p,game_day="2000-01-01"),self.root)
    def test_review_stale(self):
        p=self.plan()
        with self.assertRaises(ValueError):e.validate_review(p,self.review(p,reviewed_at="2000-01-01T00:00:00+08:00"),self.root)
    def test_review_wrong_hash(self):
        p=self.plan();r=self.review(p);r["evidence"]["sha256"]="0"*64
        with self.assertRaises(ValueError):e.validate_review(p,r,self.root)
    def test_review_wrong_resolution(self):
        self.png.write_bytes(b"\x89PNG\r\n\x1a\n"+b"\0"*8+struct.pack("!II",1920,1080))
        with self.assertRaises(ValueError):e.evidence(self.png,root=self.root)
    def test_gift_limits_and_currency(self):
        p=self.plan()
        for kw in [{"quantity":11},{"unit_price":6001},{"currency":"paid"},{"discount":"-20%"},{"quantity":True}]:
            with self.assertRaises(ValueError):e.validate_review(p,self.review(p,**kw),self.root)
    def test_cargo_quantity_and_transfer_required(self):
        p=self.plan("delivery","valleyiv","PowerPlateau")
        for kw in [{"quantity":6001},{"transfer_available":False},{"cargo_checked":False}]:
            with self.assertRaises(ValueError):e.validate_review(p,self.review(p,**kw),self.root)
    def test_credit_price_and_balance(self):
        p=self.plan("credit-buy",None,"Oroberyl")
        for kw in [{"price":401,"balance":900},{"price":300,"balance":299},{"price":100,"balance":900,"currency":"paid"}]:
            r=self.review(p,currency="Credits");r.update(kw)
            with self.assertRaises(ValueError):e.validate_review(p,r,self.root)
    def test_refresh_requires_target_review(self):
        p=self.plan("credit-refresh",None,None)
        with self.assertRaises(ValueError):e.validate_review(p,self.review(p,price=80,currency="Credits"),self.root)
    def test_existing_ad_hoc_receipts_block_replay(self):
        (self.root/"runs").mkdir()
        (self.root/"runs"/("endfield-extra-"+e.day().replace("-","")+"-summary.json")).write_text("{}")
        with self.assertRaises(ValueError):e.attempted(self.plan(),self.root)
    def test_backup_ledger_also_blocks(self):
        p=self.plan();e.ledger_path(p,self.root).with_suffix(".json.bak").write_text("{}")
        with self.assertRaises(ValueError):e.attempted(p,self.root)
    def test_legacy_delivery_region_blocks(self):
        p=self.plan("delivery","valleyiv","PowerPlateau")
        (self.root/"state"/("endfield-regional-"+e.day()+"-delivery-jobs-valleyiv.attempt.json")).write_text("{}")
        with self.assertRaises(ValueError):e.attempted(p,self.root)
    def test_submission_timeout_is_attempt_and_stop_no_retry(self):
        p=self.plan();r,code,calls,p=self.run_fake(p,self.review(p),fail=True)
        self.assertEqual(code,2);self.assertTrue(e.ledger_path(p,self.root).exists())
        self.assertTrue(any(c.endswith("/tasks/stop") for c in calls))
        with self.assertRaises(ValueError):e.attempted(p,self.root)
    def test_success_needs_visual_verification(self):
        p=self.plan();r,code,calls,p=self.run_fake(p,self.review(p))
        self.assertEqual(code,0);self.assertFalse(r["verified"])
        with self.assertRaises(ValueError):audit.validate_record(e.ledger_path(p,self.root),self.root,e.day())
    def test_verified_record_and_tamper(self):
        p=self.plan();r,_,_,p=self.run_fake(p,self.review(p))
        e.verify(Path(r["run_dir"])/"summary.json","purchased",self.png,self.root)
        self.assertEqual(audit.validate_record(e.ledger_path(p,self.root),self.root,e.day())["outcome"],"purchased")
        (Path(r["run_dir"])/"request.json").write_text("{}")
        with self.assertRaises(ValueError):audit.validate_record(e.ledger_path(p,self.root),self.root,e.day())
    def test_valley_legacy_execution_is_disabled_before_api(self):
        for unit in ("OriginiumSciencePark","OriginLodespring","PowerPlateau"):
            plan=self.plan("delivery","valleyiv",unit)
            with self.subTest(unit=unit),self.assertRaisesRegex(ValueError,"automatic submission is disabled"):
                e.execute(plan,self.review(plan),api=lambda *a,**k: self.fail("unexpected API"),root=self.root)
    def test_delivery_pending_is_not_paid(self):
        p=self.plan("delivery","wuling","WulingCity");r,_,_,p=self.run_fake(p,self.review(p))
        v=e.verify(Path(r["run_dir"])/"summary.json","transferred_pending",self.png,self.root)
        self.assertFalse(v["tail_payment_received"])
    def test_observation_no_action(self):
        p=self.plan();r=e.observe(p,self.review(p,outcome="sold_out"),self.root)
        self.assertFalse(r["submission_attempted"]);self.assertEqual(r["reserved_cost"],0)
        self.assertEqual(audit.validate_record(e.ledger_path(p,self.root),self.root,e.day())["outcome"],"sold_out")
    def test_observation_cannot_fake_purchase(self):
        p=self.plan()
        with self.assertRaises(ValueError):e.observe(p,self.review(p,outcome="purchased"),self.root)
    def test_credit_requires_claim_first(self):
        p=self.plan("credit-buy",None,"Oroberyl")
        with self.assertRaises(ValueError):e.preflight_budget(p,self.review(p,outcome="sold_out"),self.root)
    def test_credit_refresh_requires_both_targets(self):
        p=self.plan("credit-claim",None,None);e.observe(p,self.review(p,outcome="nothing_claimable"),self.root)
        p=self.plan("credit-refresh",None,None)
        with self.assertRaises(ValueError):e.preflight_budget(p,self.review(p,price=80,currency="Credits",targets_reviewed_first=True),self.root)
    def test_audit_has_all_units(self):
        r=audit.audit(self.root,e.day());self.assertEqual(len(r["stages"]),18)
        self.assertFalse(r["all_required_stages_recorded_verified"])
    def test_new_game_day_requires_extras_in_common_audit(self):
        import daily_audit
        r=daily_audit.audit("2026-11-19",self.root,{"day":"2026-11-19","games":{}})
        self.assertTrue(any(x.startswith("endfield.extra.") for x in r["blocked_stages"]))

    def test_low_stock_blocks_before_api(self):
        p=self.plan("delivery","wuling","WulingCity")
        with self.assertRaises(ValueError):e.validate_review(p,self.review(p,stock_quantity=9),self.root)
    def test_cargo_not_full_blocks(self):
        p=self.plan("delivery","wuling","WulingCity")
        with self.assertRaises(ValueError):e.validate_review(p,self.review(p,cargo_capacity=101),self.root)
    def test_unknown_order_never_repacks(self):
        p=self.plan("delivery","wuling","TestArea")
        for state in ("unknown","ongoing","transferred_pending"):
            with self.assertRaises(ValueError):e.validate_review(p,self.review(p,order_state=state),self.root)
    def test_interrupted_delivery_retains_identity_and_screenshot(self):
        p=self.plan("delivery","wuling","TestArea")
        r,code,calls,p=self.run_fake(p,self.review(p),fail=True)
        self.assertEqual(r["warehouse"]["depot"],"TestArea")
        self.assertEqual(r["warehouse"]["state"],"interrupted_unknown")
        self.assertFalse(r["warehouse"]["tail_payment_received"])
        self.assertFalse(r["recovery"]["retry_permitted"])
        self.assertTrue(Path(r["after"]["path"]).exists())
        with self.assertRaises(ValueError):e.verify(Path(r["run_dir"])/"summary.json","transferred_pending",self.png,self.root)
    def test_credit_closure_requires_both_final_targets(self):
        p=self.plan("credit-claim",None,None);e.observe(p,self.review(p,outcome="nothing_claimable"),self.root)
        for outcome in ("daily_limit_used_up","budget_limit"):
            p=self.plan("credit-review",None,None)
            with self.assertRaises(ValueError):e.preflight_budget(p,self.review(p,outcome=outcome,targets_reviewed_first=True),self.root)
    def test_budget_limited_is_not_full_completion(self):
        p=self.plan("credit-claim",None,None);e.observe(p,self.review(p,outcome="nothing_claimable"),self.root)
        for unit in ("Oroberyl","ArsenalTicket"):
            p=self.plan("credit-buy",None,unit);e.observe(p,self.review(p,outcome="unaffordable"),self.root)
        p=self.plan("credit-review",None,None)
        e.observe(p,self.review(p,outcome="budget_limit",targets_reviewed_first=True),self.root)
        row=next(r for r in audit.audit(self.root,e.day())["stages"] if r["stage"].endswith("credit-review.global.all.0"))
        self.assertEqual(row["status"],"recorded_limited")
    def test_low_stock_observation_stays_limited(self):
        tail=self.plan("tail","wuling",None);e.observe(tail,self.review(tail,outcome="pending_acceptance"),self.root)
        p=self.plan("delivery","wuling","WulingCity")
        e.observe(p,self.review(p,outcome="insufficient_stock",order_state="insufficient_stock"),self.root)
        row=next(r for r in audit.audit(self.root,e.day())["stages"] if "WulingCity" in r["stage"])
        self.assertEqual(row["status"],"recorded_limited")


    def test_delivery_requires_region_tail_check(self):
        p=self.plan("delivery","valleyiv","OriginLodespring")
        with self.assertRaises(ValueError):e.preflight_budget(p,self.review(p),self.root)
    def test_item_budget_limit_has_truthful_outcome(self):
        p=self.plan("credit-buy",None,"Oroberyl")
        rev=self.review(p,outcome="budget_limit",price=300,currency="Credits")
        records=[{"phase":"credit-claim","cycle":0,"unit":None,"reserved_cost":0},
                 {"phase":"credit-buy","cycle":0,"unit":"ArsenalTicket","reserved_cost":1800}]
        with patch.object(e,"previous",return_value=records):
            self.assertEqual(e.preflight_budget(p,rev,self.root),0)
        with patch.object(e,"previous",return_value=records[:1]):
            with self.assertRaises(ValueError):e.preflight_budget(p,rev,self.root)
    def test_audit_exposes_failed_depot_identity_without_success(self):
        p=self.plan("delivery","wuling","TestArea");r,_,_,p=self.run_fake(p,self.review(p),fail=True)
        row=next(r for r in audit.audit(self.root,e.day())["stages"] if "TestArea" in r["stage"])
        self.assertEqual(row["warehouse"]["state"],"interrupted_unknown")
        self.assertNotEqual(row["status"],"recorded_verified")


    def test_legacy_game_day_survives_midnight_filename(self):
        run=self.root/"runs/endfield-extra-delivery-20261120";run.mkdir(parents=True)
        (run/"summary.json").write_text(json.dumps({"game_day":"2026-11-19"}))
        with self.assertRaises(ValueError):e.legacy_guard("2026-11-19",self.root)
    def test_legacy_timestamp_obeys_four_am_boundary(self):
        run=self.root/"runs/endfield-extra-recovery-20261120";run.mkdir(parents=True)
        (run/"summary.json").write_text(json.dumps({"at":"2026-11-20T01:00:00+08:00"}))
        with self.assertRaises(ValueError):e.legacy_guard("2026-11-19",self.root)


    def test_tail_requires_order_states_and_expiry(self):
        p=self.plan("tail","valleyiv",None)
        for orders in (None,[{"order_reference":"order","state":"pending_acceptance"}],[]):
            with self.assertRaises(ValueError):e.validate_review(p,self.review(p,outcome="pending_acceptance",orders=orders),self.root)
    def test_tail_check_keeps_pending_orders_unpaid(self):
        p=self.plan("tail","valleyiv",None)
        e.observe(p,self.review(p,outcome="pending_acceptance"),self.root)
        row=next(r for r in audit.audit(self.root,e.day())["stages"] if ".tail.valleyiv." in r["stage"])
        self.assertEqual(row["orders_before"][0]["state"],"pending_acceptance")
        self.assertIn("not all orders settled",row["tail_payment"])


    def test_unknown_tail_cannot_certify_or_unlock_packing(self):
        p=self.plan("tail","valleyiv",None)
        r=self.review(p,outcome="nothing_claimable",orders=[{"order_reference":"uncertain order","state":"unknown","expiry_text":"not shown"}])
        with self.assertRaises(ValueError):e.observe(p,r,self.root)
        self.assertFalse(e.ledger_path(p,self.root).exists())

if __name__=="__main__":unittest.main()
