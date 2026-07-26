"""Policy evaluation errors without runtime side effects."""


class PolicyContractMismatchError(ValueError):
    """Raised when input contracts do not share provenance."""
