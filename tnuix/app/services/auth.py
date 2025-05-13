import hashlib
import secrets
import time
from typing import Optional, Dict
from fastapi import HTTPException, status, Cookie, Depends
from app.core.config import USERS, SESSION_EXPIRY
from app.models.user import User, UserSession

# 会话存储
sessions: Dict[str, UserSession] = {}

def create_session(username: str) -> str:
    """创建新的会话"""
    session_id = secrets.token_hex(16)
    sessions[session_id] = UserSession(
        username=username,
        created_at=time.time(),
        expires_at=time.time() + SESSION_EXPIRY
    )
    return session_id

def verify_session(session_id: Optional[str] = Cookie(None)) -> Optional[str]:
    """验证会话是否有效"""
    if not session_id or session_id not in sessions:
        return None
    
    session = sessions[session_id]
    if time.time() > session.expires_at:
        # 会话已过期
        del sessions[session_id]
        return None
        
    # 更新会话过期时间
    session.expires_at = time.time() + SESSION_EXPIRY
    return session.username

def get_current_user(session_id: Optional[str] = Cookie(None)) -> str:
    """获取当前用户，用作依赖项"""
    username = verify_session(session_id)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或会话已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username

def verify_password(username: str, password: str) -> bool:
    """验证用户密码"""
    if username not in USERS:
        return False
    
    user = USERS[username]
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return password_hash == user["password_hash"]

def get_user(username: str) -> Optional[User]:
    """获取用户信息"""
    if username not in USERS:
        return None
    
    user_data = USERS[username]
    return User(**user_data) 