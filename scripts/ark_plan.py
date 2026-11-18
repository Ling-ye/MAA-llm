"""Explicit approved recruitment/base/credit supplement. No startup or DLL at import."""


import runner as base


def make_plan(c):
 base_plan=ORIGINAL_MAKE_PLAN(dict(c,recruit={'enabled':False},infrast={'enabled':False},mall={'enabled':False})) # Validate connection/stage/time bounds, not used as execution plan.
 if c.get('game')!='arknights' or c.get('supplement_policy')!='approved-ark-operations-v1' or c.get('expected_version')!='v6.22.0':raise ValueError('Supplement policy/version mismatch')
 return [
 {'type':'Recruit','params':{'select':[4],'confirm':[3,4],'times':4,'refresh':False,'force_refresh':False,'expedite':False,'expedite_times':0,'set_time':True,'recruitment_time':{'3':540,'4':540},'preserve_tags':['\u9ad8\u7ea7\u8d44\u6df1\u5e72\u5458','\u8d44\u6df1\u5e72\u5458','\u652f\u63f4\u673a\u68b0'],'report_to_penguin':False,'report_to_yituliu':False}},
 {'type':'Infrast','params':{'mode':0,'facility':['Power','Office','Control','Mfg','Trade','Reception','Recycle','Dorm'],'drones':'_NotUse','threshold':0.3,'replenish':False,'dorm_trust_enabled':False,'dorm_notstationed_enabled':True,'reception_clue_exchange':False,'reception_send_clue':False,'continue_training':False}},
 {'type':'Mall','params':{'visit_friends':True,'shopping':True,'buy_first':['\u62db\u8058\u8bb8\u53ef'],'blacklist':['\u78b3','\u5bb6\u5177','\u52a0\u6025\u8bb8\u53ef'],'force_shopping_if_credit_full':False,'credit_fight':False}},
 {'type':'Award','params':{'award':True,'mail':False,'recruit':False,'orundum':False,'mining':False,'specialaccess':False,'signinevent':False}}]
ORIGINAL_MAKE_PLAN=base.make_plan
