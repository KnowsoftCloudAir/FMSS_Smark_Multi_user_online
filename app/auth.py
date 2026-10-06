from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, Cookie
from sqlmodel import Session, select
import os
import secrets

from app.database import get_session
from app.models import User, Business, PlatformAdmin

SECRET_KEY = os.getenv("SECRET_KEY", "knowsoft-bizpos-secret-change-in-prod-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash((password or "")[:72])


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify((plain or "")[:72], hashed)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def generate_approval_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def generate_sku(prefix: str = "SKU") -> str:
    return f"{prefix}-{secrets.token_hex(3).upper()}"


def get_token_from_request(request: Request, access_token: Optional[str] = Cookie(None)) -> Optional[str]:
    if access_token:
        return access_token
    # also accept admin_token for dual-session support
    admin_tok = request.cookies.get("admin_token")
    if admin_tok:
        return admin_tok
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:]
    return None


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
) -> User:
    token = get_token_from_request(request, access_token)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") == "admin":
            raise HTTPException(status_code=403, detail="Admin session — use admin area")
        uid = payload.get("sub")
        if not uid:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = session.get(User, int(uid))
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User inactive")
        biz = session.get(Business, user.business_id) if user.business_id else None
        if biz and biz.status != "approved":
            raise HTTPException(status_code=403, detail="Business not approved yet")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_optional_user(
    request: Request,
    session: Session = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
) -> Optional[User]:
    try:
        return get_current_user(request, session, access_token)
    except HTTPException:
        return None


def get_platform_admin(
    request: Request,
    session: Session = Depends(get_session),
    access_token: Optional[str] = Cookie(None),
    admin_token: Optional[str] = Cookie(None),
) -> PlatformAdmin:
    # Prefer dedicated admin_token cookie so a user login does not block admin
    token = admin_token or request.cookies.get("admin_token")
    if not token:
        token = get_token_from_request(request, access_token)
    def _fail(msg="Platform admin required"):
        accept = (request.headers.get("accept") or "")
        if "text/html" in accept or not accept.startswith("application/json"):
            raise HTTPException(
                status_code=303,
                detail="Redirect",
                headers={"Location": "/ks-admin/login"},
            )
        raise HTTPException(status_code=403, detail=msg)

    if not token:
        _fail("Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "admin":
            _fail("Platform admin required")
        admin = session.get(PlatformAdmin, int(payload.get("sub")))
        if not admin or not admin.is_active:
            _fail("Admin inactive")
        return admin
    except HTTPException:
        raise
    except JWTError:
        _fail("Invalid token")
