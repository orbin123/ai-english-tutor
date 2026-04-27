"""Diagnosis module exceptions."""


class DiagnosisAlreadyCompleted(Exception):
    """Raised when a user tries to submit diagnosis a second time."""
    pass


class DiagnosisInvalidPayload(Exception):
    """Raised when submission references unknown question/passage IDs."""
    pass