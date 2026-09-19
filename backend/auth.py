from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
# Compatibility: bcrypt>=4.1 removed __about__; silence passlib probe
try:
    import bcrypt as _bcrypt_mod
    if not hasattr(_bcrypt_mod, "__about__"):
        class _About:
            __version__ = getattr(_bcrypt_mod, "__version__", "4.0.1")
        _bcrypt_mod.__about__ = _About()  # type: ignore
except Exception:
    pass
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
from models import User, Company
import os
import secrets

SECRET_KEY = os.getenv("SECRET_KEY", "knowsoft-fmss-super-secret-key-change-in-production-0160XPRO")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if isinstance(plain_password, str):
        plain_password = plain_password[:72]

    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    # bcrypt only uses first 72 bytes
    if isinstance(password, str):
        password = password[:72]

    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)

def generate_license_key(company_slug: str) -> str:
    raw = secrets.token_hex(8).upper()
    return f"KFM-{company_slug[:6].upper()}-{raw[:8]}-{raw[8:16]}"

def get_user_by_username(db: Session, username: str, company_id: Optional[int] = None):
    q = db.query(User).filter(User.username == username)
    if company_id is not None:
        q = q.filter(User.company_id == company_id)
    elif company_id is False:
        # explicit platform user
        q = q.filter(User.company_id.is_(None))
    return q.first()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        company_id = payload.get("company_id")  # may be None for superadmin
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    if company_id is None:
        user = db.query(User).filter(User.username == username, User.company_id.is_(None)).first()
    else:
        user = get_user_by_username(db, username=username, company_id=company_id)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_superadmin(current_user: User = Depends(get_current_active_user)):
    if current_user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Platform superadmin required")
    return current_user

async def get_company_admin(current_user: User = Depends(get_current_active_user)):
    if current_user.role not in ("company_admin", "superadmin", "admin"):
        raise HTTPException(status_code=403, detail="Company admin required")
    return current_user

def require_roles(*roles):
    async def _dep(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in roles and current_user.role != "superadmin":
            raise HTTPException(403, f"Requires one of: {', '.join(roles)}")
        return current_user
    return _dep

def check_company_license(db: Session, company_id: int):
    """Block login/use if company not approved or license expired."""
    from datetime import date
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(403, "Company not found")
    if company.status == "pending":
        raise HTTPException(403, "Company registration is pending superadmin approval")
    if company.status == "rejected":
        raise HTTPException(403, "Company registration was rejected")
    if company.status == "suspended":
        raise HTTPException(403, "Company account is suspended")
    if company.license_expires and company.license_expires < date.today():
        raise HTTPException(403, "Annual license has expired. Contact Knowsoft support.")
    return company
