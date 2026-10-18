from model.common.errors import ContractError


def validate_episode_membership(
    flight_id: str, predecessor_id: str, successor_id: str
) -> bool:
    if predecessor_id == successor_id:
        raise ContractError("INVALID_PREDECESSOR_SUCCESSOR_MEMBERSHIP")
    return flight_id in {predecessor_id, successor_id}


def require_episode_identity(
    episode_id: str, predecessor_id: str, successor_id: str
) -> None:
    if (
        not episode_id
        or not predecessor_id
        or not successor_id
        or predecessor_id == successor_id
    ):
        raise ContractError("CRITICAL_EPISODE_IDENTITY_FAILURE")
