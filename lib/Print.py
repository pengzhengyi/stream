def out(msg, quiet=False):
    """
    Prints a message if quiet is False

    Args:
        msg: message to be printed
        quiet: whether message will be silenced
            default to False
    """
    if not quiet:
        print(msg)
