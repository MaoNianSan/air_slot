class AirSlotError(Exception):
    code = "AIR_SLOT_ERROR"


class ContractError(AirSlotError):
    code = "CONTRACT_ERROR"


class ScopeViolationError(AirSlotError):
    code = "PROHIBITED_SCOPE"


class NotImplementedByScopeError(AirSlotError):
    code = "NOT_IMPLEMENTED_BY_SCOPE"


class RegistryError(ContractError):
    code = "REGISTRY_INVALID"


class NodeInvalidationError(ContractError):
    code = "NODE_LEVEL_INVALIDATION"
