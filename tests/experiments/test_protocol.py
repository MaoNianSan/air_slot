import pytest

from exp.common.protocol import ExperimentProtocol
from exp.common.runner import ExperimentRunner


def test_protocol_is_abstract_and_requires_all_four_hooks():
    assert ExperimentProtocol.__abstractmethods__ == {
        "prepare", "run", "evaluate", "report",
    }
    with pytest.raises(TypeError):
        ExperimentProtocol()


def test_common_runner_sequences_an_interface_fixture(common_result):
    events = []

    class FixtureProtocol(ExperimentProtocol):
        def prepare(self, context):
            events.append(("prepare", context))
            return "prepared"

        def run(self, prepared):
            events.append(("run", prepared))
            return "execution"

        def evaluate(self, execution):
            events.append(("evaluate", execution))
            return "evaluation"

        def report(self, evaluation):
            events.append(("report", evaluation))
            return common_result

    result = ExperimentRunner().execute(FixtureProtocol(), context="fixture")

    assert result is common_result
    assert events == [
        ("prepare", "fixture"),
        ("run", "prepared"),
        ("evaluate", "execution"),
        ("report", "evaluation"),
    ]


def test_common_runner_rejects_non_protocol():
    with pytest.raises(TypeError, match="EXPERIMENT_PROTOCOL_TYPE_REQUIRED"):
        ExperimentRunner().execute(object())
