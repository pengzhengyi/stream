"""The errors the core raises, rooted in one type so callers can catch them together."""


class MedleyplayError(Exception):
    """A failure the core reports to its caller."""


class InvalidInputError(MedleyplayError):
    """A value breaks a domain rule, such as a username with spaces."""


class NotFoundError(MedleyplayError):
    """The thing asked for does not exist, or the caller may not see it."""


class ConflictError(MedleyplayError):
    """The request clashes with what already exists, such as a taken username."""


class ForbiddenError(MedleyplayError):
    """The caller is signed in but may not do this."""


class NotSignedInError(MedleyplayError):
    """The request carries no valid session."""


class SignInRefusedError(MedleyplayError):
    """The username and password don't match an Account."""


class SignInThrottledError(MedleyplayError):
    """Too many failed sign-ins for this username; try again later."""

    def __init__(self, retry_after_seconds: int) -> None:
        """Record how long the caller should wait."""
        super().__init__(f"Too many failed sign-ins; retry in {retry_after_seconds} s.")
        self.retry_after_seconds = retry_after_seconds
