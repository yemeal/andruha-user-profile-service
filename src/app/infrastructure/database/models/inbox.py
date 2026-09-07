from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base


class ProcessedEventORM(Base):
    __tablename__ = "processed_events"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(consumer)) > 0", name="ck_processed_events_consumer"
        ),
    )

    consumer: Mapped[str] = mapped_column(String(200), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
