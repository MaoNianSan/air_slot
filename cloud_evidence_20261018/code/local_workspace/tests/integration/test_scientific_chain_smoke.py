from validation.scientific_smoke import run_scientific_smoke


def test_bounded_data2_and_data1_scientific_chain_smoke(tmp_path):
    result=run_scientific_smoke(tmp_path,scenario_count=8,seed=13)
    assert result["data2_2019"]["status"]=="PASS"
    assert result["data1_2019"]["status"]=="PASS"
    assert result["data1_2019"]["r_ob_support"]=="ABSTAIN"
    assert result["data1_2019"]["decision_node_status"]=="CONSTRUCTED"
    assert result["paper_result"] is False
