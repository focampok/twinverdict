"""Tablas de jobs, políticas, métricas y el log de replay."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('search', 'baseline', 'eval')", name="ck_jobs_kind"),
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')",
            name="ck_jobs_status",
        ),
        Index("ix_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class PolicyRow(Base):
    __tablename__ = "policies"
    __table_args__ = (
        CheckConstraint(
            "source IN ('fixed', 'llm', 'optuna', 'llm_no_feedback')",
            name="ck_policies_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id"), nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    valid: Mapped[bool] = mapped_column(nullable=False, default=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MetricRow(Base):
    __tablename__ = "metrics"
    __table_args__ = (
        CheckConstraint(
            "seed_set IN ('train', 'holdout', 'stress')",
            name="ck_metrics_seed_set",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("policies.id"), nullable=False)
    seed_set: Mapped[str] = mapped_column(String(16), nullable=False)
    n_seeds: Mapped[int] = mapped_column(Integer, nullable=False)
    objective: Mapped[float] = mapped_column(Float, nullable=False)
    kpis: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ci_low: Mapped[float] = mapped_column(Float, nullable=False)
    ci_high: Mapped[float] = mapped_column(Float, nullable=False)
    sims_spent: Mapped[int] = mapped_column(Integer, nullable=False)


class RunEvent(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
