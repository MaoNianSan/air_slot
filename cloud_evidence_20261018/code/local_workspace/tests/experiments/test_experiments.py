from pathlib import Path
import pytest
from model.common.errors import ContractError
from exp.common.bootstrap import episode_bootstrap
from exp.exp1.runner import Exp1Runner
from exp.exp2.runner import Exp2Runner
from exp.exp3.llm_audit import audit_cases
from exp.promotion import promote

def test_variants_bootstrap_and_llm_absence_are_explicit(tmp_path:Path):
    assert set(Exp1Runner().variants)=={"empirical","current","fixed_history","adaptive_history","independent_heads","leakage_diagnostic"}
    assert len(Exp2Runner().variants)==5
    result=episode_bootstrap([{"episode_id":"a","value":1},{"episode_id":"b","value":3}],"value",replicates=20,seed=1)
    assert result.replicates==20
    audit=audit_cases([{"case_id":"c"}],provider=None); assert audit[0]["status"]=="NOT_RUN"
    with pytest.raises(ContractError): promote(tmp_path,tmp_path/"paper",eligible=False)


def test_non_smoke_evaluation_is_not_automatically_a_paper_result():
    result=Exp1Runner().run([{"episode_id":"e1","metric":1.0}],smoke=False)
    assert result.manifest.paper_result is False


def test_main_text_promotion_rejects_appendix_dataset(tmp_path:Path):
    source=tmp_path/"run";source.mkdir()
    (source/"manifest.json").write_text('{"paper_result":true,"smoke":false,"dataset_instance_id":"data1_2019","dataset_role":"APPENDIX_REPLICATION"}',encoding="utf-8")
    with pytest.raises(ContractError,match="MAIN_TEXT_DATASET_ROLE_MISMATCH"):
        promote(source,tmp_path/"paper",eligible=True,destination_role="MAIN_TEXT")
