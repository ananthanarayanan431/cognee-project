from datetime import datetime, timedelta, timezone

import httpx
from jose import JWTError, jwt
from passlib.context import CryptContext

from debatemind.config import settings

_jwks_cache: dict | None = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": user_id, "exp": expire}, settings.secret_key, algorithm=settings.algorithm
    )


def decode_token(token: str) -> str:
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    user_id: str = payload.get("sub")
    if user_id is None:
        raise JWTError("Invalid token")
    return user_id


async def verify_sso_jwt(token: str) -> dict:
    global _jwks_cache
    if not _jwks_cache:
        async with httpx.AsyncClient() as client:
            r = await client.get(settings.auth_jwks_url)
            r.raise_for_status()
            _jwks_cache = r.json()
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    key = next((k for k in _jwks_cache["keys"] if k.get("kid") == kid), None)
    if not key:
        _jwks_cache = None  # bust cache in case keys rotated
        raise JWTError("Key not found in JWKS")
    return jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})
