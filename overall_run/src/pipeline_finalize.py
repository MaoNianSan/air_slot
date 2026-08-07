from __future__ import annotations

from .failures import M4ContractMismatch
from .m4.contracts import M4FormalArtifact


def finalize_experiment(artifact: M4FormalArtifact) -> M4FormalArtifact:
    if not isinstance(artifact, M4FormalArtifact):
        raise M4ContractMismatch("M4_FINALIZATION_ARTIFACT_REQUIRED")
    if artifact.test_only:
        raise M4ContractMismatch("M4_TEST_ONLY_FINALIZATION_FORBIDDEN")
    return artifact
