"""A plugin whose import raises."""

message = "This plugin can't be imported."
raise RuntimeError(message)
