import contextlib
import copy
import datetime as dt
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
import endfield_valley_transfer as v
import test_gf2_supervised_daily as fixtures


class ValleyTransferTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.SupervisedDailyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.root=self.f.root;self.time=self.f.time;self.base=self.f.base
        (self.base/'interface.json').write_text('{"version":"v3.1.0"}')
        self.node='OriginiumSciencePark'

    def frame(self,state='quoted_unpublished',offset=0,node=None):
        node=node or self.node
        f=self.f.frame('unused',offset);f.pop('phase')
        f.update(game='endfield',version='v3.1.0',framework='v5.16.1',region='valleyiv',node=node,
                 node_name=v.NODES[node],dialog_unambiguous=True,node_order_bound=True,
                 order_reference='synthetic-reviewed-order-'+node,navigation_or_acceptance=False,tail_claim_action=False,
                 order_state=state,item_name='蓝铁装备原件',item_hover_verified=True,quantity_and_stock_same_item=True,
                 quantity=10,stock_quantity=90,capacity=200,item_volume=20,stock_basis='remaining_after_packing',
                 packed_quantity=10,already_published=False,paid_resources=False,control_enabled=True,
                 existing_quote=True,quote_bound_to_cargo=True,control_text='快速转交',control_color='white',
                 yellow_start_transport_selected=False,supporting_evidence={'item_identity':self.f.evidence(offset-5)})
        f['window'].update(title='明日方舟：终末地',executable=str(self.root/'Endfield.exe'),client_size=[1280,720])
        if state=='ready_to_pack':
            f.update(existing_quote=False,control_text='下一步',next_step_has_side_effect=True,
                     stock_basis='available_before_packing',stock_quantity=100)
        if state=='posted_waiting':
            f.update(panel_title='我转交的委托',publish_text='已发布',acceptance_text='等待接单中',tail_state='pending_acceptance',
                     tail_payment_received=False,deposit_observed=False,expiry_text='合成：2天后过期')
        return f

    def act(self,action,frame=None,**kwargs):
        return v.record(self.root,self.node,action,frame,self.base,self.root/'Endfield.exe',
                        moment=self.time,inspect=kwargs.pop('inspect',lambda:copy.deepcopy(frame['window'])),**kwargs)

    def test_plan_is_offline_and_execute_blocked(self):
        with patch.object(v,'ROOT',self.root),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(v.main([]),0);self.assertEqual(v.main(['--execute']),2)
        self.assertFalse((self.root/'state').exists())

    def test_existing_quote_reserves_transfer_without_repacking(self):
        r=self.act('reserve',self.frame())
        self.assertEqual(r['status'],'manual_transfer_reserved')
        self.assertFalse(r['script_executed_game_action'])
        with self.assertRaises(v.e.Blocked):self.act('record-quote',self.frame(offset=20))

    def test_next_step_is_reserved_before_quote_and_transfer(self):
        self.assertEqual(self.act('reserve',self.frame('ready_to_pack'))['status'],'manual_pack_reserved')
        self.assertEqual(self.act('record-quote',self.frame(offset=20))['status'],'quote_recorded')
        self.assertEqual(self.act('reserve-transfer',self.frame(offset=40))['status'],'manual_transfer_reserved')
        r=self.act('verify',self.frame('posted_waiting',80))
        self.assertEqual(r['status'],'manual_transferred_pending');self.assertFalse(r['tail_payment_received'])

    def test_next_step_is_not_a_harmless_preview(self):
        f=self.frame('ready_to_pack');f['next_step_has_side_effect']=False
        with self.assertRaises(v.e.Blocked):self.act('reserve',f)

    def test_existing_quote_cannot_be_repacked(self):
        f=self.frame('ready_to_pack');f['existing_quote']=True
        with self.assertRaises(v.e.Blocked):self.act('reserve',f)

    def test_low_stock_stops_before_window_access(self):
        f=self.frame('ready_to_pack');f['stock_quantity']=9
        with self.assertRaises(v.e.Blocked):
            self.act('reserve',f,inspect=lambda:(_ for _ in ()).throw(AssertionError('window accessed')))

    def test_partial_unknown_and_published_cannot_reserve(self):
        for state in ('partially_packed','unknown','posted_waiting'):
            with self.subTest(state=state),self.assertRaises(v.e.Blocked):self.act('reserve',self.frame(state))

    def test_unknown_submission_cannot_replay_or_certify(self):
        self.act('reserve',self.frame());self.act('mark-unknown',reason='interrupted transfer')
        for action in ('reserve','verify','observe'):
            with self.subTest(action=action),self.assertRaises(v.e.Blocked):self.act(action,self.frame('posted_waiting',80))

    def test_exact_node_cargo_and_stock_required(self):
        for change in ({'node_name':'武陵'},{'node_order_bound':False},{'item_hover_verified':False},
                       {'item_name':'unreviewed'},{'quantity_and_stock_same_item':False},{'capacity':201},
                       {'quantity':True},{'stock_basis':'unknown'}):
            f=self.frame();f.update(change)
            with self.subTest(change=change),self.assertRaises(v.e.Blocked):self.act('reserve',f)

    def test_quick_transfer_must_not_select_yellow_transport(self):
        for change in ({'control_text':'开始运送'},{'control_color':'yellow'},{'yellow_start_transport_selected':True},
                       {'navigation_or_acceptance':True},{'tail_claim_action':True},{'paid_resources':True}):
            f=self.frame();f.update(change)
            with self.subTest(change=change),self.assertRaises(v.e.Blocked):self.act('reserve',f)

    def test_quote_stock_delta_must_match_reserved_item(self):
        self.act('reserve',self.frame('ready_to_pack'))
        f=self.frame(offset=20);f['stock_quantity']=89
        with self.assertRaises(v.e.Blocked):self.act('record-quote',f)

    def test_changed_material_or_order_stops_resume(self):
        self.act('reserve',self.frame('ready_to_pack'))
        for change in ({'item_name':'精选养愈胶囊'},{'order_reference':'different'}):
            f=self.frame(offset=20);f.update(change)
            with self.subTest(change=change),self.assertRaises(v.e.Blocked):self.act('record-quote',f)

    def test_only_transfer_reservation_can_verify_publication(self):
        self.act('reserve',self.frame('ready_to_pack'))
        with self.assertRaises(v.e.Blocked):self.act('verify',self.frame('posted_waiting',80))

    def test_published_observation_locks_node_and_keeps_tail_unpaid(self):
        r=self.act('observe',self.frame('posted_waiting'))
        self.assertEqual(r['status'],'already_transferred_observed');self.assertFalse(r['tail_payment_received'])
        with self.assertRaises(v.e.Blocked):self.act('reserve',self.frame(offset=80))

    def test_deposit_cannot_be_reported_as_tail_income(self):
        for change in ({'tail_payment_received':True},{'tail_state':'paid'},{'deposit_observed':True,'deposit_amount':50}):
            f=self.frame('posted_waiting');f.update(change)
            with self.subTest(change=change),self.assertRaises(v.e.Blocked):self.act('observe',f)

    def test_blocked_observation_preserves_unknown_order(self):
        f=self.frame('partially_packed');f['blocked_reason']='synthetic low stock after interruption'
        r=self.act('observe-blocked',f)
        self.assertEqual(r['latest']['order_state'],'partially_packed')
        with self.assertRaises(v.e.Blocked):self.act('reserve',self.frame(offset=80))

    def test_window_switch_blocks_reservation(self):
        f=self.frame();reads=iter([f['window'],{**f['window'],'pid':999}])
        with self.assertRaises(v.e.Blocked):self.act('reserve',f,inspect=lambda:next(reads))

    def test_wrong_version_stop_and_stale_evidence(self):
        (self.base/'interface.json').write_text('{"version":"unknown"}')
        with self.assertRaises(v.e.Blocked):self.act('reserve',self.frame())
        (self.base/'interface.json').write_text('{"version":"v3.1.0"}')
        f=self.frame();f['evidence']['captured_at']=(self.time-dt.timedelta(minutes=6)).isoformat()
        with self.assertRaises(v.e.Blocked):self.act('reserve',f)
        (self.root/'STOP').touch()
        with self.assertRaises(v.e.Blocked):self.act('reserve',self.frame())

    def test_legacy_node_attempt_and_backup_block_reservation(self):
        p=self.root/'state'/f'endfield-extras-{v.day(self.time)}-delivery.valleyiv.{self.node}.0.attempt.json.bak'
        p.parent.mkdir();p.write_text('{}')
        with self.assertRaises(v.e.Blocked):self.act('reserve',self.frame())

    def test_legacy_ad_hoc_game_day_blocks_even_after_midnight(self):
        p=self.root/'runs/endfield-extra-after-midnight/summary.json';p.parent.mkdir(parents=True)
        p.write_text(json.dumps({'game_day':v.day(self.time)}))
        with self.assertRaises(v.e.Blocked):self.act('reserve',self.frame())

    def test_nodes_have_independent_daily_attempts(self):
        for node in v.NODES:
            self.node=node;self.act('observe',self.frame('posted_waiting',node=node))
        self.assertEqual(len(list((self.root/'state').glob('*.attempt.json'))),3)

    def test_ledger_or_evidence_tamper_blocks_audit(self):
        f=self.frame('posted_waiting');self.act('observe',f)
        (self.root/f['evidence']['path']).write_bytes(b'changed')
        with self.assertRaises(v.e.Blocked):v.status(self.root,self.node,self.time)

    def test_original_evidence_is_checked_before_step_resume(self):
        f=self.frame('ready_to_pack');self.act('reserve',f)
        (self.root/f['evidence']['path']).write_bytes(b'changed')
        with self.assertRaises(v.e.Blocked):self.act('record-quote',self.frame(offset=20))


if __name__=='__main__':unittest.main()
