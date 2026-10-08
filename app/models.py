from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    # MySQL DATETIME stores naive values. The API interprets these as UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    @property
    def status(self) -> str:
        return "archived" if self.archived_at is not None else "active"


class DomainVersion(Base):
    __tablename__ = "domain_versions"
    __table_args__ = (
        UniqueConstraint("course_id", "version", name="uq_domain_course_version"),
        UniqueConstraint("id", "course_id", name="uq_domain_id_course"),
        CheckConstraint("version > 0", name="ck_domain_positive_version"),
        CheckConstraint("status IN ('draft', 'published')", name="ck_domain_status"),
        CheckConstraint("(status = 'draft' AND published_at IS NULL) OR "
                        "(status = 'published' AND published_at IS NOT NULL)", name="ck_domain_publication"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Competency(Base):
    __tablename__ = "competencies"
    __table_args__ = (
        UniqueConstraint("domain_version_id", "code", name="uq_competency_domain_code"),
        UniqueConstraint("id", "domain_version_id", name="uq_competency_id_domain"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    domain_version_id: Mapped[str] = mapped_column(ForeignKey("domain_versions.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        ForeignKeyConstraint(
            ["competency_id", "domain_version_id"], ["competencies.id", "competencies.domain_version_id"],
            name="fk_skill_competency_domain",
        ),
        UniqueConstraint("domain_version_id", "code", name="uq_skill_domain_code"),
        UniqueConstraint("id", "domain_version_id", name="uq_skill_id_domain"),
        CheckConstraint("skill_kind IN ('routine', 'non_routine')", name="ck_skill_kind"),
        CheckConstraint("requires_automaticity IN (0, 1)", name="ck_skill_automaticity_boolean"),
        CheckConstraint("skill_kind = 'routine' OR requires_automaticity = 0", name="ck_skill_automaticity_routine"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    domain_version_id: Mapped[str] = mapped_column(ForeignKey("domain_versions.id"), nullable=False)
    competency_id: Mapped[str] = mapped_column(String(36), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    skill_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    requires_automaticity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class SkillPrerequisite(Base):
    __tablename__ = "skill_prerequisites"
    __table_args__ = (
        ForeignKeyConstraint(["skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"],
                             name="fk_prerequisite_skill_domain"),
        ForeignKeyConstraint(["prerequisite_skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"],
                             name="fk_prerequisite_required_domain"),
        UniqueConstraint("domain_version_id", "skill_id", "prerequisite_skill_id", name="uq_prerequisite_edge"),
        CheckConstraint("skill_id <> prerequisite_skill_id", name="ck_prerequisite_not_self"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    domain_version_id: Mapped[str] = mapped_column(ForeignKey("domain_versions.id"), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(36), nullable=False)
    prerequisite_skill_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class Learner(Base):
    __tablename__ = "learners"
    __table_args__ = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # Internal development identity mapping; never exposed in learner responses.
    principal_subject: Mapped[str] = mapped_column(String(128, collation="utf8mb4_bin"), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        ForeignKeyConstraint(["domain_version_id", "course_id"], ["domain_versions.id", "domain_versions.course_id"],
                             name="fk_enrollment_domain_course"),
        UniqueConstraint("learner_id", "course_id", name="uq_enrollment_learner_course"),
        UniqueConstraint("id", "domain_version_id", name="uq_enrollment_id_domain"),
        CheckConstraint("status = 'active'", name="ck_enrollment_status"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), nullable=False)
    domain_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class LearnerSkillState(Base):
    __tablename__ = "learner_skill_states"
    __table_args__ = (
        ForeignKeyConstraint(["enrollment_id", "domain_version_id"], ["enrollments.id", "enrollments.domain_version_id"],
                             name="fk_state_enrollment_domain"),
        ForeignKeyConstraint(["skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"],
                             name="fk_state_skill_domain"),
        CheckConstraint("band = 'unknown' AND evidence_count = 0 AND revision = 0", name="ck_state_initial_unknown"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    enrollment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    domain_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    band: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class CatalogReview:
    """Immutable content with a single, attributed prototype review transition."""
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128, collation="utf8mb4_bin"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    review_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="synthetic_only")
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(128, collation="utf8mb4_bin"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    references: Mapped[list] = mapped_column(JSON, nullable=False)


def catalog_constraints(prefix):
    return (
        CheckConstraint("version > 0", name="ck_" + prefix + "_version"),
        CheckConstraint("review_status IN ('draft', 'approved', 'rejected')", name="ck_" + prefix + "_status"),
        CheckConstraint("review_scope = 'synthetic_only'", name="ck_" + prefix + "_scope"),
        CheckConstraint("(review_status = 'draft' AND reviewed_by IS NULL AND reviewed_at IS NULL AND review_note IS NULL) OR "
                        "(review_status IN ('approved', 'rejected') AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL "
                        "AND review_note IS NOT NULL AND reviewed_by <> created_by)", name="ck_" + prefix + "_review"),
    )


class PolicyVersion(CatalogReview, Base):
    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint("category", "code", "version", name="uq_policy_category_code_version"),
        CheckConstraint("category IN ('learning_science', 'safety')", name="ck_policy_category"),
        *catalog_constraints("policy"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    rules: Mapped[dict] = mapped_column(JSON, nullable=False)


class ActivityVariant(CatalogReview, Base):
    __tablename__ = "activity_variants"
    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_activity_code_version"),
        CheckConstraint("activity_type IN ('worked_example', 'selected_response', 'constructed_response')", name="ck_activity_type"),
        CheckConstraint("evidence_tier = 'provisional'", name="ck_activity_evidence_tier"),
        CheckConstraint("estimated_minutes > 0 AND estimated_minutes <= 180", name="ck_activity_minutes"),
        *catalog_constraints("activity"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="provisional")
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    guidance: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    learning_science_policy_id: Mapped[str] = mapped_column(ForeignKey("policy_versions.id"), nullable=False)
    safety_policy_id: Mapped[str] = mapped_column(ForeignKey("policy_versions.id"), nullable=False)
    mappings: Mapped[list["ComponentActivityMapping"]] = relationship(order_by="ComponentActivityMapping.component")


class ComponentActivityMapping(Base):
    __tablename__ = "component_activity_mappings"
    __table_args__ = (
        CheckConstraint("component IN ('learning_tasks', 'supportive_information', 'procedural_information', 'part_task_practice')",
                        name="ck_mapping_component"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    activity_variant_id: Mapped[str] = mapped_column(ForeignKey("activity_variants.id"), primary_key=True)
    component: Mapped[str] = mapped_column(String(32), primary_key=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)


class LoopPlan(Base):
    __tablename__ = "loop_plans"
    __table_args__ = (
        ForeignKeyConstraint(["enrollment_id", "domain_version_id"], ["enrollments.id", "enrollments.domain_version_id"],
                             name="fk_plan_enrollment_domain"),
        ForeignKeyConstraint(["target_skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"],
                             name="fk_plan_target_domain"),
        ForeignKeyConstraint(["focus_skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"],
                             name="fk_plan_focus_domain"),
        UniqueConstraint("enrollment_id", "input_fingerprint", name="uq_plan_enrollment_input"),
        UniqueConstraint("id", "domain_version_id", name="uq_plan_id_domain"),
        CheckConstraint("time_budget_minutes > 0 AND time_budget_minutes <= 180", name="ck_plan_budget"),
        CheckConstraint("estimated_minutes > 0 AND estimated_minutes <= time_budget_minutes", name="ck_plan_duration"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    enrollment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    domain_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_skill_id: Mapped[str] = mapped_column(String(36), nullable=False)
    focus_skill_id: Mapped[str] = mapped_column(String(36), nullable=False)
    learning_science_policy_id: Mapped[str] = mapped_column(ForeignKey("policy_versions.id"), nullable=False)
    safety_policy_id: Mapped[str] = mapped_column(ForeignKey("policy_versions.id"), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    time_budget_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[dict] = mapped_column(JSON, nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    steps: Mapped[list["LoopStep"]] = relationship(order_by="LoopStep.position")


class LoopStep(Base):
    __tablename__ = "loop_steps"
    __table_args__ = (
        ForeignKeyConstraint(["loop_plan_id", "domain_version_id"], ["loop_plans.id", "loop_plans.domain_version_id"],
                             name="fk_step_plan_domain"),
        ForeignKeyConstraint(["skill_id", "domain_version_id"], ["skills.id", "skills.domain_version_id"],
                             name="fk_step_skill_domain"),
        CheckConstraint("position > 0", name="ck_step_position"),
        CheckConstraint("estimated_minutes > 0 AND estimated_minutes <= 180", name="ck_step_duration"),
        CheckConstraint("support_level IN ('high', 'minimal')", name="ck_step_support"),
        CheckConstraint("role IN ('whole_task_context', 'focus_practice', 'whole_task_return', 'whole_task')", name="ck_step_role"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
    loop_plan_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(36), nullable=False)
    activity_variant_id: Mapped[str] = mapped_column(ForeignKey("activity_variants.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    components: Mapped[list] = mapped_column(JSON, nullable=False)
    support_level: Mapped[str] = mapped_column(String(16), nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
