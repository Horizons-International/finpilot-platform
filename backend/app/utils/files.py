from pathlib import Path


def get_file_extension(filename: str) -> str:
    """Return the lowercase file extension without the leading dot."""
    return Path(filename).suffix.lower().lstrip(".")


def get_filename(filename: str) -> str:
    """Return the filename component from a path."""
    return Path(filename).name


def sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe filename."""
    filename = Path(filename).name

    return "".join(
        character
        for character in filename
        if character.isalnum() or character in {" ", ".", "_", "-"}
    )
