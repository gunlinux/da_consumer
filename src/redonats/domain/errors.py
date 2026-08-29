"""Domain exceptions."""


class RedonatsError(Exception):
    """Base class for redonats domain errors."""


class ConfigError(RedonatsError):
    """Raised when required configuration is missing or invalid."""


class ProtocolError(RedonatsError):
    """Raised when the gateway returns an unexpected payload."""
