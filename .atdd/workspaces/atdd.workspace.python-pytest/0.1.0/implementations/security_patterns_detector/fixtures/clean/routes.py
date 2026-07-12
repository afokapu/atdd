"""Clean: every route declares a Depends(<auth_fn>) parameter."""
from fastapi import APIRouter, Depends

router = APIRouter()


def get_current_user():
    return {"id": 1}


@router.get("/items")
def list_items(user=Depends(get_current_user)):
    return []


@router.post("/items")
def create_item(payload: dict, user=Depends(get_current_user)):
    return payload
