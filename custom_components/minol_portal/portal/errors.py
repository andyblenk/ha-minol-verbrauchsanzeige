"""Stable errors whose messages are safe for a local UI or diagnostic log."""


class PortalError(Exception):
    code = "portal_error"


class AuthenticationError(PortalError):
    code = "authentication_failed"


class SessionExpired(PortalError):
    code = "session_expired"


class ProtocolError(PortalError):
    code = "unexpected_response"


class ConnectionError(PortalError):
    code = "connection_failed"


class SelectionError(PortalError):
    code = "invalid_selection"


def raise_for_temporary_status(status: int) -> None:
    """Keep service failures recoverable instead of requesting new credentials."""
    if status in {408, 429} or 500 <= status < 600:
        raise ConnectionError(
            f"Der Minol-Dienst meldet einen vorübergehenden Fehler (Status {status}).")
