from sqlalchemy import Column, Integer, String, Boolean, DateTime
from .database import Base
from passlib.context import CryptContext
from datetime import datetime
from enum import Enum
import secrets

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Services(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    domain = Column(String(100), nullable=False, unique=True)
    active = Column(Boolean, default=True, nullable=True)
    requester_email = Column(String(100), nullable=False)
    api_key = Column(String(64), nullable=True, unique=True, index=True)
    api_secret_hash = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    credentials_retrieved = Column(Boolean, default=False)
    
    def generate_credentials(self):
        self.api_key = secrets.token_urlsafe(32)
        api_secret = secrets.token_urlsafe(32)
        self.api_secret_hash = pwd_context.hash(api_secret)
        return self.api_key, api_secret
    
    def verify_secret(self, api_secret: str) -> bool:
        if not self.api_secret_hash:
            return False
        return pwd_context.verify(api_secret, self.api_secret_hash)


class ServiceCredentialsToken(Base):
    __tablename__ = "service_credentials_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    service_id = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    api_secret_plain = Column(String(64), nullable=True)
    
    def is_valid(self) -> bool:
        return not self.used and datetime.utcnow() < self.expires_at


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    USER = "USER"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), nullable=False, unique=True)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(100), nullable=False)
    name = Column(String(100), nullable=True)
    surname = Column(String(100), nullable=True)
    active = Column(Boolean, default=False, nullable=True)
    city = Column(String(100), nullable=True)
    description = Column(String(100), nullable=True)
    email_verified = Column(Boolean, default=False, nullable=True)
    email_verification_token = Column(String(255), nullable=True)
    email_verification_expires = Column(DateTime, nullable=True)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime, nullable=True)
    role = Column(
        String(10),
        nullable=False,
        default=UserRole.USER.value
    )
    google_id = Column(String(255), unique=True, nullable=True, index=True)
    apple_id = Column(String(255), unique=True, nullable=True, index=True)

    def __repr__(self):
        return f"User(username={self.username}, email={self.email})"

    def set_password(self, raw_password):
        self.password = pwd_context.hash(raw_password)

    def verify_password(self, raw_password):
        return pwd_context.verify(raw_password, self.password)