class AppError(Exception):
    """A safe, user-facing error; never wrap raw provider/request text."""

    exit_code = 3


class InputError(AppError):
    exit_code = 2


class ProviderError(AppError):
    pass


class ModelOutputError(AppError):
    """A retryable output-format error, distinct from network/API failures."""
