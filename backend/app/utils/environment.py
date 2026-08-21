import os


def get_env(
    name: str,
    default: str | None = None,
) -> str | None:
    """Return an environment variable or its default value."""
    return os.getenv(name, default)


def get_required_env(name: str) -> str:
    """Return an environment variable or raise an error if missing."""
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Required environment variable '{name}' is not set.")

    return value
