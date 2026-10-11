"""Authenticate internal routes before validating or processing their body."""
import secrets
from fastapi import HTTPException, Request


def require_internal_token(token: str):
    async def authenticate(request: Request) -> None:
        supplied = request.headers.get("authorization", "")
        if not secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
            raise HTTPException(status_code=401, detail="Unauthorized")
    return authenticate


def internal_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
