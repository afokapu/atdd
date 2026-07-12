"""Dirty endpoint: bare-string HTTPException detail + lowercase error_code."""
from fastapi import HTTPException


def get_user(user_id: str) -> dict:
    if not user_id:
        raise HTTPException(status_code=400, detail="missing user_id")
    return {"user_id": user_id}


FALLBACK_ERROR = {
    "error_code": "bad_input",
    "message": "could not process the request",
}
