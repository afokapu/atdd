"""Clean endpoint: structured error detail + UPPER_SNAKE_CASE error_code."""
from fastapi import HTTPException


def get_user(user_id: str) -> dict:
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail={
                "status_code": 400,
                "error_code": "INVALID_INPUT",
                "message": "Missing required field: user_id",
            },
        )
    return {"user_id": user_id}
