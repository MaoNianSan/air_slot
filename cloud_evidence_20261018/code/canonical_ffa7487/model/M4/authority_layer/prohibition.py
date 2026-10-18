"""Selection is deliberately outside the current scientific model."""

from model.common.errors import ContractError


SELECTION_STATE = "UNIMPLEMENTED"


def project_authority(*_args, **_kwargs):
    """Reject the retired selector path.

    Framework capability labels describe action-template scope only. They are
    not contemporaneous authority and cannot authorize an operational choice.
    """
    raise ContractError("M4_SELECTION_NOT_AUTHORIZED")
