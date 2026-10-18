"""Machine-readable Section 3--5 implementation reconciliation."""
import argparse,json
from pathlib import Path
from .shared_store import atomic_json,file_hash
from .scientific_tracks import MECHANISM_VERSION


def build(output,*,manuscript_root):
    rows=[
      ('E1','Delay / exposure / consequence screening','e1_shared_evaluation.run','YEAR_LOCAL_V5 + common support + paired chain bootstrap','IMPLEMENTED_TARGETED'),
      ('E2','CJ/HJ/HP/HM screening and recovery','shared_actions.run_actions','C1 full eligible, C2 shortlist union, C3 rolling identities','IMPLEMENTED_SCOPE_EXPANDED'),
      ('E3','Objective x distribution and mechanism controls','shared_actions + mechanisms','four objectives, Joint/Exact Marginal, threshold/headroom operators','IMPLEMENTED_PENDING_FULL_RUN'),
      ('E4','Annual/regime/rolling heterogeneity','e4_shared_aggregate.aggregate','read-only annual aggregation; rolling rows retained in C3','IMPLEMENTED_PENDING_SIX_YEAR'),
      ('CU','Year-local V5 scales','annual_cu.load_annual_cu','five annual positive H1 medians + event scales one','IMPLEMENTED'),
      ('TAIL','Annual M1 tail','annual_tail.load_annual_tail','N=4096 H1 Train active-positive labels, no cross-year fallback','IMPLEMENTED_FAIL_CLOSED'),
      ('HEADROOM','Stage-II nominal','scientific_tracks.nominal_headroom','41/45/.25 common retrospective policy; annual sensitivity separate','IMPLEMENTED'),
      ('TIME','F_continuity','model.M2.consequence_service.native_consequence_vector','R_IB internal minutes and turnaround reference; manuscript origin reconciliation retained','REQUIRES_FINAL_SCIENTIFIC_CHECK'),
      ('MECHANISM','E3 operators','mechanisms.compare',MECHANISM_VERSION,'IMPLEMENTED_OPERATOR_LEDGER'),
    ]
    payload=dict(schema_version='JATM_MANUSCRIPT_CODE_RECONCILIATION_V1',source_manifest=file_hash(Path(manuscript_root)/'05_experiment.tex'),rows=[dict(module=a,claim=b,implementation=c,contract=d,status=e) for a,b,c,d,e in rows],
        manuscript_files={name:file_hash(Path(manuscript_root)/name) for name in ('03_methodology.tex','04_implement.tex','05_experiment.tex','SUPPLEMENT.tex')},final_test_access_count=0)
    atomic_json(output,payload);return payload


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--manuscript-root',type=Path,required=True);a=p.parse_args();build(a.output,manuscript_root=a.manuscript_root)
