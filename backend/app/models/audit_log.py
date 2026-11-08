from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, JSON, String, Text
from backend.app.models.base import TimeStampedModel


class AuditLog(TimeStampedModel):
    __tablename__ = "audit_logs"

    event_type = Column(String(100), nullable=False, index=True)
    actor_type = Column(String(50), default="SYSTEM_AUTONOMOUS", nullable=False) # SYSTEM_AUTONOMOUS, USER
    actor_id = Column(String(100), nullable=False, index=True)
    action = Column(String(255), nullable=False)
    payload_diff = Column(JSON, nullable=True)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )

