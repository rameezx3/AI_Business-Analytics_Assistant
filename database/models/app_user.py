"""Local application accounts; passwords are stored only as salted hashes."""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Integer, String, func

from database.models.base import Base


class AppUser(Base):
    __tablename__ = "app_users"

    email: str = Column(String(254), primary_key=True)
    role: str = Column(String(10), nullable=False, default="user", index=True)
    password_hash: str = Column(String(255), nullable=False)
    is_active: bool = Column(Boolean, nullable=False, default=True)
    failed_attempts: int = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'user')", name="ck_app_users_role"),
    )
