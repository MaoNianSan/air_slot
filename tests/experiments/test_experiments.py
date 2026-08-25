from pathlib import Path
import pytest
from model.common.errors import ContractError
from exp.common.bootstrap import episode_bootstrap
from exp.exp1.runner import Exp1Runner
from exp.exp2.runner import Exp2Runner
from exp.exp3.llm_audit import audit_cases
from exp.workflows.promotion import promote

def test_variants_bootstrap_and_llm_absence_are_explicit(tmp_path:Path):
    assert set(Exp1Runner().variants)=={
        "EXP1A_NO_DIRECT_REUSE", "EXP1A_FULL",
        "EXP1B_CURRENT", "EXP1B_ADAPTIVE_HISTORY",
    }
    assert set(Exp2Runner().variants)=={
        "EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT",
        "EXP2B_SCALAR", "EXP2B_3CHANNEL", "EXP2B_7COMP",
    }
    result=episode_bootstrap([{"episode_id":"a","value":1},{"episode_id":"b","value":3}],"value",replicates=20,seed=1)
    assert result.replicates==20
    audit=audit_cases([{"case_id":"c"}],provider=None); assert audit[0]["status"]=="NOT_RUN"
    with pytest.raises(ContractError): promote(tmp_path,tmp_path/"paper",eligible=False)


def test_non_smoke_evaluation_is_not_automatically_a_paper_result():
    with pytest.raises(RuntimeError, match="EXP1_TYPED_CONTEXT_EXECUTION_REQUIRED"):
        Exp1Runner().run(smoke=False)


def test_main_text_promotion_rejects_appendix_dataset(tmp_path:Path):
    source=tmp_path/"run";source.mkdir()
    (source/"manifest.json").write_text('{"paper_result":true,"smoke":false,"dataset_instance_id":"data1_2019","dataset_role":"APPENDIX_REPLICATION"}',encoding="utf-8")
    with pytest.raises(ContractError,match="MAIN_TEXT_DATASET_ROLE_MISMATCH"):
        promote(source,tmp_path/"paper",eligible=True,destination_role="MAIN_TEXT")
