from fastapi import APIRouter


router = APIRouter(
    tags=["Health"],
)


@router.get(
    "/health",
    name="health_check",
)
def health_check() -> dict[str, str]:
    """
    Return the application health status.
    """

    return {
        "status": "ok",
    }
