from sqlalchemy import Boolean, Column, String
from backend.app.models.base import TimeStampedModel


class User(TimeStampedModel):
    __tablename__ = "users"

    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), default="viewer", nullable=False)  # admin, viewer
    is_active = Column(Boolean, default=True, nullable=False)

