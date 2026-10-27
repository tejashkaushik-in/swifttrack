from datetime import datetime, timedelta, timezone
import hashlib
import jwt
import bcrypt  # 🔴 Using the native modern driver directly now!
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.config import settings

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

def _get_clean_password(password: str) -> bytes:
    """
    Converts password into a 64-character SHA-256 hex string,
    then returns it as raw bytes for native bcrypt compatibility.
    """
    hex_str = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hex_str.encode("utf-8")

def hash_password(password: str) -> str:
    """Generates a secure, native salt and hashes the pre-cleaned password."""
    clean_pwd = _get_clean_password(password)
    # Generate a fresh random salt
    salt = bcrypt.gensalt()
    # Hash it and convert the resulting bytes back to a standard string for storage
    hashed = bcrypt.hashpw(clean_pwd, salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compares the incoming password directly against the database record string."""
    try:
        clean_pwd = _get_clean_password(plain_password)
        # Convert the stored string hash back to bytes to perform the check
        return bcrypt.checkpw(clean_pwd, hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(data: dict) -> str:
    """Generates a secure, short-lived JWT token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Decodes and validates an incoming JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        role: str = payload.get("role")
        
        if user_id is None or role is None:
            raise credentials_exception
            
        return {"user_id": int(user_id), "role": role}
    except jwt.PyJWTError:
        raise credentials_exception

class RoleChecker:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role")
        if user_role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access Denied: You do not have the required permissions."
            )
        return current_user