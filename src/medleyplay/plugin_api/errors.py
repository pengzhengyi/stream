"""The failures a plugin reports; any other exception is a fault in the plugin."""


class NetworkError(Exception):
    """The site couldn't be reached, or stopped answering; retrying later may work."""


class AuthError(Exception):
    """The site refused the login, for example because it expired."""
