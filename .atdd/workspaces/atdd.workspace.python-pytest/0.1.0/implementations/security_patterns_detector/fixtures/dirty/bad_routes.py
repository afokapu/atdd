"""Dirty: a route with no Depends(<auth_fn>) parameter -> missing-auth."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/admin")
def admin_panel():
    # ❌ no auth dependency injected
    return {"status": "ok"}
