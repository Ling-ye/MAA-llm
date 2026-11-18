"""Read-only extra-task audit. No API, SDK, subprocess or execution-adapter imports."""
import datetime as dt
import hashlib
import json
import struct
from pathlib import Path

def read(path): return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def within(path, root):
    p=Path(path).resolve();p.relative_to(Path(root).resolve());return p
def png(value,root):
    p=within(value["path"],root);b=p.read_bytes()
    if len(b)<24 or not b.startswith(b"\x89PNG\r\n\x1a\n") or struct.unpack("!II",b[16:24])!=(1280,720) or sha(p)!=value["sha256"]:
        raise ValueError("Missing/changed 1280x720 evidence")
def validate_record(ledger,root,current_day):
    p=within(ledger,root);l=read(p);run=within(l["run_dir"],Path(root)/"runs");s=run/"summary.json";r=read(s)
    if l.get("status")!="verified" or l.get("summary_sha256")!=sha(s):raise ValueError("Unverified/changed ledger")
    if r.get("schema")!="endfield-extras-v1" or r.get("game")!="endfield" or r.get("game_day")!=current_day:
        raise ValueError("Wrong schema/game/day")
    if r.get("policy_sha256")!=sha(Path(__file__).with_name("endfield-extra-policy.json")):
        raise ValueError("Receipt policy changed")
    if r.get("maa_version")!="v3.1.0" or r.get("framework_version")!="v5.16.1":
        raise ValueError("Version mismatch")
    if r.get("status")!="verified" or r.get("verified") is not True or r.get("error") or r.get("safety_errors"):
        raise ValueError("Receipt not safely verified")
    if within(r["run_dir"],Path(root)/"runs")!=run:raise ValueError("Wrong run binding")
    if sha(run/"request.json")!=r["request_sha256"] or sha(run/"review.json")!=r["review_sha256"]:
        raise ValueError("Request/review changed")
    req=read(run/"request.json");rev=read(run/"review.json")
    if rev!=r["review"]:raise ValueError("Review content mismatch")
    for k in ("game_day","phase","region","unit","cycle","scope","instance","policy_sha256"):
        if r.get(k)!=req.get(k):raise ValueError("Plan/receipt mismatch: "+k)
    for k in ("game_day","phase","region","unit","cycle"):
        if r.get(k)!=rev.get(k):raise ValueError("Review identity mismatch: "+k)
    expected="endfield-extras-"+current_day+"-"+r["scope"]+".attempt.json"
    if p.name!=expected or p.parent!=Path(root).resolve()/"state":raise ValueError("Wrong attempt key")
    if rev.get("supervised") is not True:raise ValueError("No supervisor review")
    if type(r.get("reserved_cost")) is not int or r["reserved_cost"]<0:raise ValueError("Invalid budget")
    png(rev["evidence"],root);png(r["verification_evidence"],root)
    if r.get("observation_only"):
        permitted={"sold_out","no_exact_discount","already_transferred","cooldown","pending_acceptance",
          "pending_delivery","nothing_claimable","nothing_collectible","unaffordable","daily_limit_used_up","budget_limit","insufficient_stock"}
        if r.get("submission_attempted") or r["outcome"] not in permitted or r["reserved_cost"]!=0:
            raise ValueError("Observation cannot assert resource use")
    else:
        png(r["before"],root);png(r["after"],root)
        state=r["state"];tasks=req["tasks"];ids=r["response"].get("taskIds",[]);t=state.get("task_run_state",{})
        selected=[v["selected_task_id"] for v in tasks]
        if not ids or any(type(i) is not int or i<=0 for i in ids) or len(ids)!=len(selected) or len(set(ids))!=len(ids) or state.get("is_running") or t.get("overall_status")!="Succeeded":
            raise ValueError("Task did not safely complete")
        if t.get("pending_task_ids")!=ids or set(t.get("mappings",{}))!=set(map(str,ids)):
            raise ValueError("Task IDs mismatch")
        if [t["mappings"].get(str(i)) for i in ids]!=selected or any(t.get("statuses",{}).get(x)!="succeeded" for x in selected):
            raise ValueError("Task mapping mismatch")
        if r.get("submission_attempted") is not True or r.get("automation_succeeded") is not True:
            raise ValueError("Missing execution proof")
    if r["phase"]=="delivery" and r.get("tail_payment_received") is True:
        raise ValueError("Transfer is not tail-payment receipt")
    return r

def legacy_receipts(root,current_day):
    """Metadata beats filename calendar date around the Beijing 04:00 boundary."""
    found=[]
    for p in (Path(root)/"runs").glob("endfield-extra-*"):
        summary=p/"summary.json" if p.is_dir() else p
        candidate=current_day.replace("-","") in p.name
        try:
            r=read(summary);record_day=r.get("game_day")
            if not record_day and r.get("at"):
                stamp=dt.datetime.fromisoformat(r["at"])
                if stamp.tzinfo is not None:
                    record_day=(stamp.astimezone(dt.timezone(dt.timedelta(hours=8)))-dt.timedelta(hours=4)).date().isoformat()
            candidate=candidate or record_day==current_day
        except (OSError,ValueError,TypeError):pass
        if candidate:found.append(str(p))
    return found

def audit(root,current_day):
    root=Path(root).resolve();dt.date.fromisoformat(current_day)
    policy=read(Path(__file__).with_name("endfield-extra-policy.json"))
    keys=[]
    for g in policy["gifts"]:keys.append(("gifts.valleyiv."+g+".0","gifts"))
    for reg,depots in policy["depots"].items():
        keys.extend(("delivery."+reg+"."+d+".0","delivery") for d in depots)
        keys.extend((x+"."+reg+".all.0",x) for x in ("tail","recycle"))
    keys.extend((x+".global.all.0","credit") for x in ("credit-claim","credit-review"))
    # Include intermediate purchases/refreshes; an unverified step blocks completion.
    for p in (root/"state").glob("endfield-extras-"+current_day+"-*.attempt.json"):
        key=p.name[len("endfield-extras-"+current_day+"-"):-len(".attempt.json")]
        if key not in {k for k,_ in keys}:keys.append((key,"credit" if key.startswith("credit-") else "extra"))
    rows=[]
    for key,group in keys:
        row={"stage":"endfield.extra."+key,"game":"endfield","group":group,"status":"review_required","no_replay":True}
        p=root/"state"/("endfield-extras-"+current_day+"-"+key+".attempt.json")
        try:
            r=validate_record(p,root,current_day)
            row.update(status="recorded_verified",outcome=r["outcome"],receipt=str(Path(r["run_dir"])/"summary.json"))
            if r["outcome"] in ("budget_limit","insufficient_stock"):
                row["status"]="recorded_limited"
                row["reason"]="Known resource limit; do not claim full daily completion"
            if r["phase"]=="delivery":row["tail_payment"]="pending is not paid"
            if r["phase"]=="tail":
                row["tail_payment"]="Daily check/claim only; not all orders settled"
                row["orders_before"]=r["review"].get("orders",[])
        except (OSError,ValueError,KeyError,TypeError) as e:
            row["reason"]=str(e)
            try:
                ledger=read(p);run=within(ledger["run_dir"],root/"runs");summary=run/"summary.json";r=read(summary)
                if sha(summary)==ledger.get("summary_sha256") and r.get("game_day")==current_day and r.get("scope")==key:
                    row["receipt"]=str(summary)
                    if r.get("warehouse"):row["warehouse"]=r["warehouse"]
            except (OSError,ValueError,KeyError,TypeError):pass
        rows.append(row)
    legacy=legacy_receipts(root,current_day)
    return {"mode":"read_only","game_day":current_day,"stages":rows,
        "all_required_stages_recorded_verified":all(r["status"]=="recorded_verified" for r in rows),
        "legacy_receipts_present":bool(legacy),
        "legacy_note":"Existing ad-hoc receipts block new execution today; inspect them, do not invent migrated success" if legacy else None}
