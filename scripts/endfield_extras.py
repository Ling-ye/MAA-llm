"""Supervised Endfield additions. Preview is offline; no automatic retry."""
from __future__ import annotations
import argparse, copy, datetime as dt, hashlib, json, re, struct, time, uuid
from pathlib import Path
from endfield_common import (ROOT, APP, VERSION, FRAMEWORK, day, now, instance_id,
    read, digest, atomic_json, exclusive_lock, check_stop, local_versions, request,
    live_versions, idle_states, capture, log_position, collect_log, safety_errors, task_body)
from endfield_safe import state_success

POLICY_SHA256 = "c5e4aa6e30f262fb18c5ca25ab3d9f0a3b6f77c5e6464f4948b1fac5b01b26b8"
PHASES = ("gifts", "delivery", "tail", "recycle", "credit-claim", "credit-buy", "credit-refresh", "credit-review")
CREDIT_STOP = ("AutoGetCredits", "CreditShoppingBuyPriority2", "CreditShoppingBuyPriority3",
    "CreditShoppingBuyBlacklist", "CreditShoppingPrudentRefresh",
    "CreditShoppingRefreshCountReached", "CreditShippingCanNotToBuy", "RefreshItem")
OUTCOMES = {
    "gifts": ("purchased", "sold_out", "no_exact_discount"),
    "delivery": ("transferred_pending", "already_transferred", "cooldown", "insufficient_stock"),
    "tail": ("claimed", "pending_acceptance", "pending_delivery", "nothing_claimable"),
    "recycle": ("collected", "nothing_collectible"),
    "credit-claim": ("claimed", "nothing_claimable"),
    "credit-buy": ("purchased", "sold_out", "unaffordable", "budget_limit"),
    "credit-refresh": ("refreshed",),
    "credit-review": ("daily_limit_used_up", "budget_limit"),
}
NO_ACTION = {"sold_out", "no_exact_discount", "already_transferred", "cooldown",
             "pending_acceptance", "pending_delivery", "nothing_claimable",
             "nothing_collectible", "unaffordable", "daily_limit_used_up", "budget_limit", "insufficient_stock"}

def policy():
    p = Path(__file__).with_name("endfield-extra-policy.json")
    if digest(p) != POLICY_SHA256:
        raise ValueError("Extra policy changed; review code and policy together")
    return read(p)

def scope(phase, region=None, unit=None, cycle=0):
    p = policy()
    if phase not in PHASES or type(cycle) is not int or not 0 <= cycle <= 4:
        raise ValueError("Invalid phase/cycle")
    if phase == "gifts":
        if region != "valleyiv" or unit not in p["gifts"]: raise ValueError("Valley gift required")
    elif phase == "delivery":
        if unit not in p["depots"].get(region, []): raise ValueError("Explicit region/depot required")
    elif phase in ("tail", "recycle"):
        if region not in p["depots"] or unit is not None: raise ValueError("Explicit region required")
    elif phase == "credit-buy":
        if region is not None or unit not in p["credit_items"]: raise ValueError("Only gacha resources")
    elif region is not None or unit is not None:
        raise ValueError("Unexpected region/unit")
    if not phase.startswith("credit-") and cycle != 0: raise ValueError("Cycle applies to credit only")
    if phase in ("credit-claim", "credit-review") and cycle != 0: raise ValueError("Single daily phase")
    if phase == "credit-refresh" and cycle >= 4: raise ValueError("Four refreshes maximum")
    return ".".join([phase, region or "global", unit or "all", str(cycle)])

def disabled():
    return {"enabled": False, "action": "Custom", "custom_action": "FalseAction", "next": [], "on_error": []}

def make_plan(phase, region=None, unit=None, cycle=0, instance=None, review=None):
    """Construct exact overrides without reading an installed game or making API calls."""
    key = scope(phase, region, unit, cycle); p = policy(); review = review or {}
    ps = copy.deepcopy(p["base"])
    guard = {"DotExtraEnd": {"recognition": "DirectHit", "action": "DoNothing", "next": []}}
    entry = ""
    if phase == "gifts":
        # One product, one purchase confirmation, only the exact -80% shelf.
        ps.append({"AutoStockInStapleItemNameCultural": {"attach": {
            k: v if k == unit else False for k, v in p["gifts"].items()}}})
        ps.append(copy.deepcopy(p["gift_count_controls"]))
        guard.update({
            "AutoStockStapleValleyIV": {"enabled": True}, "AutoStockStapleWuling": {"enabled": False},
            "AutoStockBuyItemValleyIVTaskDaily": {"enabled": False},
            "AutoStockBuyItemValleyIVTaskIndustrial": {"enabled": False},
            "AutoStockBuyItemValleyIVTaskEngravingPermit": {"enabled": False},
            "AutoStockInStapleItemDiscountsValleyIVCultural": {"recognition": {"param": {
                "expected": ["-80"], "order_by": "Expected"}}},
            "AutoStockBuyItemValleyIVTaskCultural": {"max_hit": 1},
            "AutoStockStapleQuantityControlConfirmBuy": {"max_hit": 1},
        })
        entry = "AutoStockStapleMain"
    elif phase == "delivery":
        ps.extend(copy.deepcopy(p["delivery"][unit]))
        guard.update({k: disabled() for k in p["blocked_auto_delivery"]})
        guard.update({
            "DeliveryJobsSelectTypeOfGoodsToPackNextStep": {"next": ["DeliveryJobsCargoFillToMax"]},
            "DeliveryJobsDecideQuickTransfer": {"next": ["DeliveryJobsQuickTransfer"]},
            "DeliveryJobsTransferOngoingJob": {"next": ["DeliveryJobsClickTransferJob"]},
            "DeliveryJobsRedistributionBidNextStep": disabled(),
            "DeliveryJobsQuickTransferConfirm": {"max_hit": 1},
            "DeliveryJobsConfirmTaskTransfer": {"max_hit": 1},
            "DeliveryJobsEnter"+unit+"DeliveryJob": {"next": ["DeliveryJobsClickTransferJob"]},
        })
        entry = "DeliveryJobsMain"
    elif phase == "tail":
        reg = "ValleyIV" if region == "valleyiv" else "Wuling"
        guard["DotTailStart"] = {"action": "Custom", "custom_action": "SubTask",
            "custom_action_param": {"sub": ["SceneEnterMenuRegionalDevelopment"+reg+"DepotNode"]},
            "next": ["ClaimDeliveryJobsClickMyTransferredTab"]}
        entry = "DotTailStart"
    elif phase == "recycle":
        guard.update({"ResourceRecycleStationValleyIVSub": {"enabled": region == "valleyiv"},
                      "ResourceRecycleStationWulingSub": {"enabled": region == "wuling"}})
        entry = "ResourceRecycleStationStart"
    else:
        guard.update({k: disabled() for k in CREDIT_STOP})
        guard["CreditShoppingBuyPriority1"] = disabled()
        guard["CreditShoppingClaimConfirmClick"] = {"next": ["DotExtraEnd"]}
        guard["CreditShoppingNoCreditClaim"] = {"next": ["DotExtraEnd"]}
        guard["CreditShoppingScanItem"] = {"next": ["CreditShoppingBuyPriority1", "CreditShoppingNothingToBuy"]}
        if phase == "credit-claim":
            entry = "CreditShoppingMain"
        elif phase == "credit-buy":
            guard["CreditShoppingBuyPriority1"] = {"enabled": True, "action": "Click",
                "all_of": ["CreditShoppingPriority1Item", "CreditShoppingPriority1CanAfford",
                           "CreditShoppingPriority1Discount", "CreditShoppingPriority1ReserveCreditGate"],
                "recognition": "And", "box_index": 0, "max_hit": 1,
                "next": ["CreditShoppingBuyFailed", "CreditShoppingBuyConfirm"], "on_error": []}
            guard["CreditShoppingPriority1Item"] = {"custom_recognition_param": {
                "item_ids": [p["credit_items"][unit]]}, "attach": {
                "IconRecognition.item_ids."+item: item == p["credit_items"][unit]
                for item in list(p["credit_items"].values())+["item_gold"]}}
            guard["CreditShoppingPriority1Discount"] = {"recognition": "DirectHit"}
            guard["CreditShoppingPriority1ReserveCreditGate"] = {"recognition": "DirectHit"}
            # Price and balance must match the fresh supervisor review before confirmation.
            price = review.get("price", -1); balance = review.get("balance", -1)
            guard["DotCreditExactPrice"] = {"recognition": "Custom", "custom_recognition": "ExpressionRecognition",
                "custom_recognition_param": {"expression":
                    "{CreditShoppingBuyItemPriceOCR}=="+str(price)+" && {CreditShoppingReserveCreditOCRInternal}=="+str(balance)}}
            guard["CreditShoppingBuyConfirm"] = {"max_hit": 1, "recognition": {"type": "And", "param": {
                "all_of": ["YellowConfirmButtonType1", "DotCreditExactPrice"], "box_index": 0}}}
            entry = "CreditShoppingShopping"
        elif phase == "credit-refresh":
            cost = p["limits"]["refresh_costs"][cycle]
            balance = review.get("balance", -1)
            guard["DotRefreshBudget"] = {"recognition": "Custom", "custom_recognition": "ExpressionRecognition",
                "custom_recognition_param": {"expression": "{RefreshCost}=="+str(cost)+
                    " && {CreditShoppingReserveCreditOCRInternal}=="+str(balance)}}
            guard["DotRefreshOne"] = {"recognition": "And",
                "all_of": ["CreditShoppingScanItemTabSelected", "RefreshText", "DotRefreshBudget"],
                "box_index": 1, "action": "Click", "max_hit": 1, "post_delay": 1500,
                "next": ["CreditShoppingShopping", "[JumpBack]YellowConfirmButtonType1"]}
            guard["CreditShoppingShopping"] = {"next": ["DotExtraEnd"]}
            entry = "DotRefreshOne"
    ps.append(guard)
    tasks = [] if phase == "credit-review" else [{
        "entry": entry, "task_name": "SupervisedExtra-"+phase,
        "selected_task_id": "dot-extra-"+key, "pipeline_override": json.dumps(ps, ensure_ascii=False)}]
    return {"schema": 1, "game": "endfield", "game_day": day(), "phase": phase, "region": region,
        "unit": unit, "cycle": cycle, "scope": key, "instance": instance_id(instance),
        "policy_sha256": POLICY_SHA256, "limits": p["limits"], "supervision_required": True,
        "tasks": tasks, "tail_payment": "pending is not paid",
        "resource_limit_boundary": "Gift/cargo quantities require live review; native fill is not an independent OCR budget meter"}

def evidence(path, sha=None, fresh=False, root=ROOT):
    p = Path(path).resolve(); p.relative_to(Path(root).resolve())
    b = p.read_bytes()
    if len(b) < 24 or not b.startswith(b"\x89PNG\r\n\x1a\n") or struct.unpack("!II", b[16:24]) != (1280,720):
        raise ValueError("Expected current 1280x720 PNG evidence")
    if sha is not None and digest(p) != sha: raise ValueError("Evidence changed")
    if fresh and not -5 <= time.time()-p.stat().st_mtime <= 300: raise ValueError("Evidence older than five minutes")
    return {"path": str(p), "sha256": digest(p), "width": 1280, "height": 720}

def validate_review(plan, review, root=ROOT, fresh=True):
    for k in ("game_day", "phase", "region", "unit", "cycle"):
        if review.get(k) != plan.get(k): raise ValueError("Review mismatch: "+k)
    if review.get("supervised") is not True: raise ValueError("Live supervision required")
    stamp = dt.datetime.fromisoformat(review["reviewed_at"])
    if stamp.tzinfo is None or (fresh and not -5 <= time.time()-stamp.timestamp() <= 300):
        raise ValueError("Review must be timezone-aware and fresh")
    ev = review["evidence"]; evidence(ev["path"], ev["sha256"], fresh, root)
    phase = plan["phase"]; lim = policy()["limits"]
    def integer(name, lo, hi):
        v = review.get(name)
        if type(v) is not int or not lo <= v <= hi: raise ValueError("Invalid reviewed "+name)
        return v
    if phase == "delivery":
        if not isinstance(review.get("order_reference"),str) or not review["order_reference"].strip():
            raise ValueError("Record visible depot/cargo/order reference before any packing")
        if review.get("order_state") not in ("ready_to_pack","packed_untransferred","transferred_pending","cooldown","insufficient_stock"):
            raise ValueError("Inspect existing order state; unknown or ongoing shipment must not be repacked")
    if phase == "tail":
        orders=review.get("orders")
        if not isinstance(orders,list):raise ValueError("Record individual transferred order states and expiry text")
        if not orders and review.get("no_orders_visible") is not True:raise ValueError("Explicit empty transferred page review required")
        refs=[]
        for order in orders:
            ref=order.get("order_reference")
            if not isinstance(ref,str) or not ref.strip() or ref in refs:raise ValueError("Unique visible order references required")
            refs.append(ref)
            if order.get("state") not in ("pending_acceptance","pending_delivery","claimable","claimed","unknown"):
                raise ValueError("Invalid transferred order state")
            if not isinstance(order.get("expiry_text"),str) or not order["expiry_text"].strip():
                raise ValueError("Record displayed expiry or explicitly not shown")
            if order["state"]=="unknown":
                raise ValueError("Unknown transferred order; inspect first, never certify tail check or start new packing")
    if review.get("outcome") in NO_ACTION:
        if review["outcome"] not in OUTCOMES[phase]: raise ValueError("Wrong no-action outcome")
        return 0
    if phase == "gifts":
        qty = integer("quantity", lim["gift_quantity_each"], lim["gift_quantity_each"])
        if review.get("discount") != "-80%" or review.get("currency") != "ValleyIVStockBills":
            raise ValueError("Only exact -80% Valley gifts")
        price = integer("unit_price", lim["gift_unit_price"], lim["gift_unit_price"])
        cost = qty*price; integer("balance", cost, 2**53)
        return cost
    if phase == "delivery":
        qty = integer("quantity", 1, lim["cargo_quantity_per_depot"])
        integer("stock_quantity", qty, 2**53)
        capacity = integer("cargo_capacity", 1, 100000)
        volume = integer("item_volume", 1, 100000)
        if not (qty-1)*volume < capacity <= qty*volume:
            raise ValueError("Reviewed cargo quantity must fill this depot capacity")
        if review.get("order_state") not in ("ready_to_pack","packed_untransferred"):
            raise ValueError("Existing transfer/cooldown cannot start packing")
        if not review.get("item_name") or review.get("cargo_checked") is not True:
            raise ValueError("Inspect each depot material/quantity; do not infer from another depot")
        if review.get("transfer_available") is not True: raise ValueError("Transfer must be visible; no accept/route fallback")
    if phase == "credit-buy":
        price = integer("price", 1, lim["credit_item_max_price"])
        integer("balance", price, 2**53)
        if review.get("currency") != "Credits": raise ValueError("Credit currency required")
        return price
    if phase == "credit-refresh":
        cost = lim["refresh_costs"][plan["cycle"]]
        if review.get("price") != cost or review.get("targets_reviewed_first") is not True:
            raise ValueError("Buy affordable gacha resources before this single refresh")
        integer("balance", cost, 2**53)
        if review.get("currency") != "Credits": raise ValueError("Credit currency required")
        return cost
    if phase == "credit-review": raise ValueError("Credit closure is observation only")
    return 0

def legacy_guard(current_day, root=ROOT):
    from endfield_extra_audit import legacy_receipts
    # Existing ad-hoc receipts are attempts, even failed/partial. Never silently import success.
    if legacy_receipts(root,current_day):
        raise ValueError("Existing extra receipts for this day; review history, never replay in a new ledger")

def ledger_path(plan, root=ROOT):
    return Path(root)/"state"/("endfield-extras-"+plan["game_day"]+"-"+plan["scope"]+".attempt.json")

def attempted(plan, root=ROOT):
    legacy_guard(plan["game_day"], root)
    target = ledger_path(plan, root)
    if list(target.parent.glob(target.name+"*")): raise ValueError("Scope already attempted; never delete/reset ledger")
    if plan["phase"] == "delivery" and list(target.parent.glob(
        "endfield-regional-"+plan["game_day"]+"-delivery-jobs-"+plan["region"]+".attempt.json*")):
        raise ValueError("Legacy regional delivery already attempted")
    return target

def previous(plan, root=ROOT):
    records = []
    for p in (Path(root)/"state").glob("endfield-extras-"+plan["game_day"]+"-*.attempt.json"):
        v = read(p)
        if v.get("status") != "verified": raise ValueError("Unresolved extra attempt: "+p.name)
        from endfield_extra_audit import validate_record
        records.append(validate_record(p, root, plan["game_day"]))
    return records

def preflight_budget(plan, review, root=ROOT):
    cost = validate_review(plan, review, root)
    records = previous(plan, root)
    if plan["phase"] == "delivery" and not any(r["phase"]=="tail" and r["region"]==plan["region"] for r in records):
        raise ValueError("Inspect/claim this region transferred tail payments before new packing")
    if plan["phase"] == "gifts":
        spent = sum(r["reserved_cost"] for r in records if r["phase"] == "gifts")
        if spent+cost > policy()["limits"]["gift_daily_bills"]: raise ValueError("Gift daily budget exceeded")
    if plan["phase"].startswith("credit-"):
        spent = sum(r["reserved_cost"] for r in records if r["phase"].startswith("credit-"))
        cap=policy()["limits"]["credit_daily_spend"]
        if spent+cost > cap: raise ValueError("Daily credit budget exceeded")
        if plan["phase"]=="credit-buy" and review.get("outcome")=="budget_limit":
            price=review.get("price")
            if type(price) is not int or not 1<=price<=policy()["limits"]["credit_item_max_price"] or spent+price<=cap:
                raise ValueError("Budget-limited item must exceed the remaining recorded daily budget")
        phases = [(r["phase"],r["cycle"],r["unit"]) for r in records]
        if plan["phase"] != "credit-claim" and ("credit-claim",0,None) not in phases:
            raise ValueError("Claim/observe credit first")
        if plan["cycle"] and ("credit-refresh",plan["cycle"]-1,None) not in phases:
            raise ValueError("Previous shelf refresh not verified")
        if plan["phase"] == "credit-refresh":
            if any(("credit-buy",plan["cycle"],u) not in phases for u in policy()["credit_items"]):
                raise ValueError("Review both gacha resources before refresh")
        if plan["phase"] == "credit-review":
            if review.get("targets_reviewed_first") is not True: raise ValueError("Inspect remaining target shelf")
            final_cycle = max((r["cycle"]+1 for r in records if r["phase"]=="credit-refresh"),default=0)
            if any(("credit-buy",final_cycle,u) not in phases for u in policy()["credit_items"]):
                raise ValueError("Final shelf requires both target records, even when budget is limited")
    return cost

def checked_manifest():
    manifest = local_versions()
    for name, sha in policy()["resource_hashes"].items():
        if digest(APP/name) != sha: raise ValueError("Extra upstream resource changed: "+name)
    return manifest

def execution_enabled():
    # Source checkout uses explicit --execute. Portable checkout also requires local opt-in.
    if (Path(__file__).parent/"project_paths.py").exists():
        from project_paths import require_execution
        require_execution("endfield")

def new_record(plan, review, run, cost):
    return {"schema":"endfield-extras-v1","game":"endfield","game_day":plan["game_day"],
        "maa_version":VERSION,"framework_version":FRAMEWORK,
        **{k:plan[k] for k in ("phase","region","unit","cycle","scope","instance","policy_sha256")},
        "run_dir":str(run),"reserved_cost":cost,"review":review,"status":"submitting",
        "verified":False,"submission_attempted":False,"created_at":now(),
        "tail_payment_scope":"observed claimable rewards only; not all orders settled" if plan["phase"]=="tail" else None}

def execute(plan, review, api=request, root=ROOT):
    execution_enabled()
    if plan != make_plan(plan["phase"],plan["region"],plan["unit"],plan["cycle"],plan["instance"],review):
        raise ValueError("Plan differs from canonical policy")
    if review.get("outcome") in NO_ACTION or not plan["tasks"]: raise ValueError("Use observation, not execution")
    check_stop(); manifest = checked_manifest()
    with exclusive_lock(Path(root)/"state/pipeline.lock"):
        check_stop(); target = attempted(plan,root); cost = preflight_budget(plan,review,root)
        live_versions(api); states = idle_states(api); instance = plan["instance"]
        if not all(states.get(instance,{}).get(k) for k in ("connected","resource_loaded")):
            raise ValueError("Bootstrap/login must be reviewed")
        run = Path(root)/"runs"/("endfield-additions-"+time.strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:8])
        run.mkdir(parents=True)
        atomic_json(run/"request.json",plan); atomic_json(run/"review.json",review)
        r = new_record(plan,review,run,cost)
        if plan["phase"]=="delivery":
            r["warehouse"]={"region":plan["region"],"depot":plan["unit"],
                "order_reference":review["order_reference"],"before_state":review["order_state"],
                "state":"not_submitted","tail_payment_received":False}
        r.update(request_sha256=digest(run/"request.json"),review_sha256=digest(run/"review.json"))
        def save():
            atomic_json(run/"summary.json",r)
            if target.exists(): atomic_json(target,{"status":r["status"],"game_day":plan["game_day"],
                "run_dir":str(run),"summary_sha256":digest(run/"summary.json")})
        offset = log_position()
        try:
            r["before"] = capture(instance,run/"before.png",api,required=True)
            if (r["before"]["width"],r["before"]["height"]) != (1280,720): raise ValueError("Wrong capture size")
            check_stop()
            # Reserve before sending, including ambiguous transport errors.
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("x",encoding="utf8") as f: json.dump({"status":"submitting","run_dir":str(run)},f)
            r["submission_attempted"] = True
            if "warehouse" in r:r["warehouse"]["state"]="submission_unknown"
            save()
            r["response"] = api("/maa/instances/"+instance+"/tasks/start",task_body(plan["tasks"],manifest))
            r["status"] = "running"; save(); deadline = time.monotonic()+600
            while True:
                check_stop()
                if time.monotonic() > deadline: raise TimeoutError("Extra timeout; do not retry")
                time.sleep(2); r["state"] = api("/maa/state")["instances"][instance]; save()
                if not r["state"].get("is_running"): break
            r["after"] = capture(instance,run/"after.png",api,required=True)
            r["safety_errors"] = safety_errors(collect_log(offset,run/"go-service.log"))
            r["automation_succeeded"] = state_success(r["state"],plan["tasks"],r["response"]) and not r["safety_errors"]
            r["status"] = "awaiting_visual_verification" if r["automation_succeeded"] else "failed"
            if "warehouse" in r:r["warehouse"]["state"]="awaiting_visual_review" if r["automation_succeeded"] else "interrupted_unknown"
            save(); return r,0 if r["automation_succeeded"] else 2
        except Exception as e:
            r.update(status="failed",error=str(e),automation_succeeded=False)
            if r["submission_attempted"]:
                try: api("/maa/instances/"+instance+"/tasks/stop",{})
                except Exception as stop: r["stop_error"] = str(stop)
            if r["submission_attempted"]:
                try:r["after"]=capture(instance,run/"failure.png",api)
                except Exception as err:r["capture_error"]=str(err)
                try:r["safety_errors"]=safety_errors(collect_log(offset,run/"go-service.log"))
                except Exception as err:r["log_error"]=str(err)
            if "warehouse" in r:
                r["warehouse"]["state"]="interrupted_unknown" if r["submission_attempted"] else "not_submitted"
                r["recovery"]={"requires_current_order_inspection":True,"retry_permitted":False,
                    "note":"Inspect exact depot/order and partially filled cargo; never restart packing automatically"}
            save(); return r,2

def observe(plan, review, root=ROOT):
    if review.get("outcome") not in NO_ACTION: raise ValueError("Observation cannot assert a new purchase/refresh")
    if plan["game_day"] != day(): raise ValueError("Stale plan")
    with exclusive_lock(Path(root)/"state/pipeline.lock"):
        target=attempted(plan,root); cost=preflight_budget(plan,review,root)
        run=Path(root)/"runs"/("endfield-additions-observed-"+uuid.uuid4().hex)
        run.mkdir(parents=True); atomic_json(run/"request.json",plan); atomic_json(run/"review.json",review)
        r=new_record(plan,review,run,cost)
        r.update(status="verified",verified=True,observation_only=True,outcome=review["outcome"],
            request_sha256=digest(run/"request.json"),review_sha256=digest(run/"review.json"),
            verification_evidence=review["evidence"],verified_at=now())
        atomic_json(run/"summary.json",r);target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("x",encoding="utf8") as f:json.dump({"status":"verified","game_day":plan["game_day"],
            "run_dir":str(run),"summary_sha256":digest(run/"summary.json")},f)
        return r

def verify(summary, outcome, png, root=ROOT):
    p=Path(summary).resolve();p.relative_to(Path(root).resolve()/"runs")
    r=read(p); plan=read(p.parent/"request.json"); target=ledger_path(plan,root)
    with exclusive_lock(Path(root)/"state/pipeline.lock"):
        if r["game_day"]!=day() or r["status"]!="awaiting_visual_verification" or not r.get("automation_succeeded"):
            raise ValueError("Only current safely completed attempt can be verified")
        if outcome not in OUTCOMES[r["phase"]]: raise ValueError("Wrong phase outcome")
        if digest(p.parent/"request.json")!=r["request_sha256"] or digest(p.parent/"review.json")!=r["review_sha256"]:
            raise ValueError("Changed request/review")
        bound=read(target)
        if Path(bound["run_dir"]).resolve()!=p.parent or bound["summary_sha256"]!=digest(p):
            raise ValueError("Ledger/summary mismatch")
        if not state_success(r["state"],plan["tasks"],r["response"]) or r.get("safety_errors"):
            raise ValueError("Task evidence mismatch")
        ev=evidence(png,fresh=True,root=root)
        r.update(status="verified",verified=True,outcome=outcome,verification_evidence=ev,verified_at=now())
        if r["phase"]=="delivery":
            r["tail_payment_received"]=False
            r["warehouse"]["state"]=outcome
            r["followup"]="Check my transferred jobs next day; pending acceptance/delivery is not paid"
        atomic_json(p,r)
        atomic_json(target,{"status":"verified","game_day":r["game_day"],"run_dir":str(p.parent),"summary_sha256":digest(p)})
        return r

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--phase",choices=PHASES);p.add_argument("--region",choices=["valleyiv","wuling"])
    p.add_argument("--unit");p.add_argument("--cycle",type=int,default=0);p.add_argument("--instance")
    p.add_argument("--review");p.add_argument("--execute",action="store_true");p.add_argument("--observe",action="store_true")
    p.add_argument("--status",action="store_true");p.add_argument("--verify");p.add_argument("--outcome");p.add_argument("--evidence")
    a=p.parse_args(argv)
    try:
        if a.status:
            from endfield_extra_audit import audit
            result=audit(ROOT,day())
        elif a.verify:
            if a.execute or a.observe: raise ValueError("Verification never executes")
            result=verify(a.verify,a.outcome,a.evidence)
        else:
            rev=read(a.review) if a.review else {}
            plan=make_plan(a.phase,a.region,a.unit,a.cycle,a.instance,rev)
            if a.execute and a.observe: raise ValueError("Choose execute or observe")
            if a.execute:
                result,code=execute(plan,rev);print(json.dumps(result,ensure_ascii=False,indent=2));return code
            result=observe(plan,rev) if a.observe else plan
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Exception as e:
        print(json.dumps({"status":"blocked","error":str(e),"no_replay":True},ensure_ascii=False));return 2
if __name__=="__main__":raise SystemExit(main())
