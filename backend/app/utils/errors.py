from fastapi import HTTPException, status


def not_found(
    resource: str,
) -> HTTPException:
    """Create a standardized resource-not-found exception."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found",
    )


def bad_request(
    message: str,
) -> HTTPException:
    """Create a standardized bad-request exception."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=message,
    )


def unauthorized(
    message: str = "Authentication required",
) -> HTTPException:
    """Create a standardized unauthorized exception."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
    )


def forbidden(
    message: str = "Access denied",
) -> HTTPException:
    """Create a standardized forbidden exception."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=message,
    )
