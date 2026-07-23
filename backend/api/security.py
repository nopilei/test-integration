import hmac

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from backend.config import settings

_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str | None = Security(_api_key_scheme)) -> None:
    expected = settings.api_key
    if not api_key or not hmac.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "API-Key"},
        )
