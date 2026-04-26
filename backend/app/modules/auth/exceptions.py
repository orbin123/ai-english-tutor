"""Auth module exceptions."""

class EmailAlreadyExists(Exception):
    """Raised when attempting to signup with an email already in use."""
    pass

class InvalidCredentials(Exception):
    """Raised when login Credentials don't match."""
    pass

