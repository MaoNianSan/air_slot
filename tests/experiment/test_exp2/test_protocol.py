from exp.common.result_schema import ExperimentResult, SupportStatus
from exp.exp2.protocol import Exp2DownstreamInterface, Exp2RunContext
from exp.exp2.runner import Exp2Runner
from exp.exp2.variants import EXP2A_JOINT, EXP2A_MARGINAL


class RecordingDownstream(Exp2DownstreamInterface):
    def __init__(self):
        self.calls = []

    def run_m3(self, *, variant_id, scenarios, consequences):
        self.calls.append(("M3", variant_id, type(scenarios), type(consequences)))
        return ()

    def run_m4(self, *, variant_id, m3_envelopes):
        self.calls.append(("M4", variant_id, m3_envelopes))
        return ()


def test_all_representations_use_the_same_m3_then_m4_interface(m1_scenarios, m2_consequences):
    downstream = RecordingDownstream()
    result = Exp2Runner().execute(Exp2RunContext(
        variant_id=EXP2A_MARGINAL,
        dataset_id="DATA2_FIXTURE",
        seed=7,
        m1_scenarios=m1_scenarios,
        m2_consequences=m2_consequences,
        m1_artifact_version="M1_FIXTURE_V1",
        m2_artifact_version="M2_FIXTURE_V1",
        model_versions={"M1": "V2", "M2": "V2", "M3": "V4", "M4": "V2"},
        downstream=downstream,
    ))

    assert [call[:2] for call in downstream.calls] == [
        ("M3", EXP2A_JOINT),
        ("M4", EXP2A_JOINT),
        ("M3", EXP2A_MARGINAL),
        ("M4", EXP2A_MARGINAL),
    ]
    assert isinstance(result, ExperimentResult)
    assert result.experiment_id == "EXP2"
    assert result.variant_id == EXP2A_MARGINAL
    assert result.dataset_id == "DATA2_FIXTURE"
    assert result.seed == 7
    assert result.artifact_versions["EXP2_SOURCE_ARTIFACT"]
    assert result.scenario_hash.startswith("sha256:")
    assert result.support_status is SupportStatus.BLOCKED
    assert result.provenance["m4_bypassed"] is False
