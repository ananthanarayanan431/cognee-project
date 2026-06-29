from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from debatemind.services.auth import decode_token

bearer = HTTPBearer()


def current_user_id(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    try:
        return decode_token(creds.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
