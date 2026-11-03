class AppError(Exception):
    """A safe, user-facing error; never wrap raw provider/request text."""

    exit_code = 3


class InputError(AppError):
    exit_code = 2


class ProviderError(AppError):
    pass


class ModelOutputError(AppError):
    """A retryable output-format error, distinct from network/API failures."""

    def __init__(self, message: str, *, repair_code: str | None = None):
        super().__init__(message)
        self.repair_code = repair_code
