"""Reviewed fixed target-inventory policy; no GUI config or resource snapshot needed."""
import json
from project_paths import POLICIES
APPROVED_TARGETS={'T_CREDS':3580000,'PROTOHEDRON':1100,'PROTOPRISM':920,'COGNITIVE_CARRIER_EXP':2100000,'COMBAT_RECORD_EXP':1500000,'PROTOSET':120,'PROTODISK':65,'WEAPON_EXP':5000000,'HEAVY_CAST_DIE':100,'CAST_DIE':45,'WARP_PLASMA_COATED_SLIDE':260,'TRIPHASIC_NANOFLAKE':260,'QUADRANT_FITTING_FLUID':260,'TACHYON_SCREENING_LATTICE':260,'D96_STEEL_SAMPLE_4':260,'METADIASTIMA_PHOTOEMISSION_TUBE':260}
DISABLED = ['ProtocolSpacePopupSanityLowUseSpMedicationPrepare', 'ProtocolSpaceRewardClaimSuccessSanityLowUseSpMedicationPrepare', 'ProtocolSpaceRewardClaimRestoreSanityUseMedication', 'ProtocolSpaceRewardUsePermit', 'ProtocolSpaceRewardFallbackSingle']

def build():
    from policy_integrity import read_policy
    task = read_policy('endfield-target-inventory-request.json')
    options = task['options']
    for key, expected in {'ProtocolSpaceMode':'TargetInventory', 'ProtocolSpaceUseSpMedication':'EndTask', 'ProtocolSpaceObtainModeClaim':'ObtainScaling1'}.items():
        if options.get(key) != expected:
            raise ValueError('Unsafe inventory option: ' + key)
    targets = options['SupplyPlanLimits']
    if targets != {'SupplyPlanLimit_'+key:str(value) for key,value in APPROVED_TARGETS.items()}:
        raise ValueError('Inventory targets changed; review policy before use')
    patches = json.loads(task['pipeline_override'])
    # Always append defense-in-depth overrides last, even to the reviewed policy.
    patches.append({node:{'enabled':False} for node in DISABLED})
    task['pipeline_override'] = json.dumps(patches, ensure_ascii=False)
    return task, dict(targets)

if __name__ == '__main__':
    task, targets = build()
    print(json.dumps({'mode':'plan_only', 'task':task, 'targets':targets}, ensure_ascii=False))
