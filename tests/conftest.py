import json
import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine, get_session
from app.main import app
from app.models import (Activity, ActivityGeneration, ActivityVariant, ComponentActivityMapping, PolicyVersion,
                        Competency, Course, DomainVersion, Enrollment, Learner, LearnerSkillState, LoopPlan, LoopStep, Skill, SkillPrerequisite)

CLEANUP_MODELS = (Activity, ActivityGeneration, LoopStep, LoopPlan, ComponentActivityMapping, ActivityVariant, PolicyVersion,
                  LearnerSkillState, Enrollment, Learner, SkillPrerequisite, Skill, Competency, DomainVersion, Course)

TEST_API_KEY = "synthetic-test-key-32-characters-long"
ROLE_KEYS = {role: "synthetic-" + role + "-key-32-characters-long" for role in ["instructor", "learner", "integration", "author"]}
SECOND_LEARNER_KEY = "synthetic-second-learner-key-32-characters-long"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", TEST_API_KEY)
    monkeypatch.setenv("DEV_PRINCIPALS", json.dumps([
        {"subject": "other-" + role, "roles": [role], "api_key": key}
        for role, key in ROLE_KEYS.items()
    ] + [{"subject": "second-learner", "roles": ["learner"], "api_key": SECOND_LEARNER_KEY}]))
    # Does not connect for unit tests. Integration tests override get_session.
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://test:test@127.0.0.1/learning_loop_test")
    get_settings.cache_clear()
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def headers():
    return {"X-API-Key": TEST_API_KEY}


@pytest.fixture
def role_headers():
    return {**{role: {"X-API-Key": key} for role, key in ROLE_KEYS.items()},
            "learner2": {"X-API-Key": SECOND_LEARNER_KEY}}


# Shared disposable MySQL fixture; never connects to the application database.
@pytest.fixture(scope="session")
def mysql_engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Run docker compose --profile test run --rm tests for real MySQL checks")
    parsed = make_url(url)
    if parsed.drivername != "mysql+pymysql" or parsed.database != "learning_loop_test":
        pytest.fail("Integration tests require the dedicated learning_loop_test MySQL database")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", url)
        patch.setenv("API_KEY", "migration-test-key-32-characters-long")
        patch.setenv("DEV_PRINCIPALS", "[]")
        get_settings.cache_clear()
        get_engine.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        assert "courses" not in inspect(get_engine()).get_table_names()
        command.upgrade(config, "0001_courses")
        # Only the disposable migration fixture uses SQL to emulate a Day 1 row.
        with get_engine().begin() as connection:
            connection.execute(text("INSERT INTO courses (id, code, title, description, created_at) "
                                    "VALUES (:id, 'LEGACY', 'Preserved title', 'Preserved evidence reference', '2026-09-30 12:00:00')"),
                               {"id": "00000000-0000-0000-0000-000000000001"})
        command.upgrade(config, "0002_course_lifecycle")
        with get_engine().begin() as connection:
            connection.execute(text("INSERT INTO courses (id, code, title, description, created_at, created_by, updated_at, archived_at) "
                                    "VALUES (:id, 'DAY2', 'Archived Day 2', 'Keep', '2026-10-01 10:00:00', "
                                    "'other-author', '2026-10-01 11:00:00', '2026-10-01 11:00:00')"),
                               {"id": "00000000-0000-0000-0000-000000000002"})
            before_day3 = connection.execute(text("SELECT * FROM courses ORDER BY code")).mappings().all()
        command.upgrade(config, "0003_domain_authoring")
        with get_engine().begin() as connection:
            connection.execute(text("INSERT INTO domain_versions (id, course_id, version, status, created_at) "
                                    "VALUES ('00000000-0000-0000-0000-000000000003', "
                                    "'00000000-0000-0000-0000-000000000001', 1, 'draft', '2026-10-02 12:00:00')"))
            connection.execute(text("INSERT INTO competencies (id, domain_version_id, code, statement, created_at, updated_at) "
                                    "VALUES ('00000000-0000-0000-0000-000000000004', "
                                    "'00000000-0000-0000-0000-000000000003', 'DEBUG', 'Preserve competency', "
                                    "'2026-10-02 12:00:00', '2026-10-02 12:00:00')"))
            connection.execute(text("INSERT INTO skills (id, domain_version_id, competency_id, code, title, description, "
                                    "skill_kind, requires_automaticity, created_at, updated_at) VALUES "
                                    "('00000000-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000003', "
                                    "'00000000-0000-0000-0000-000000000004', 'TRACE', 'Preserve skill', 'Keep description', "
                                    "'routine', 1, '2026-10-02 12:00:00', '2026-10-02 12:00:00')"))
            domain_columns = "id, course_id, version, status, created_at"
            before_day4 = {
                "domain_versions": connection.execute(text("SELECT " + domain_columns + " FROM domain_versions")).mappings().all(),
                "competencies": connection.execute(text("SELECT * FROM competencies")).mappings().all(),
                "skills": connection.execute(text("SELECT * FROM skills")).mappings().all(),
            }
        command.upgrade(config, "head")
        command.check(config)
        # Day 4 is additive; existing draft content survives its downgrade/re-upgrade.
        for target in ["0003_domain_authoring", "head"]:
            with get_engine().connect() as connection:
                for table, expected in before_day4.items():
                    columns = domain_columns if table == "domain_versions" else "*"
                    assert connection.execute(text("SELECT " + columns + " FROM " + table)).mappings().all() == expected
                if target == "0003_domain_authoring":
                    assert connection.execute(text("SELECT published_at FROM domain_versions")).scalar_one() is None
            if target == "0003_domain_authoring":
                command.downgrade(config, target)
                assert "skill_prerequisites" not in inspect(get_engine()).get_table_names()
                assert "published_at" not in {column["name"] for column in inspect(get_engine()).get_columns("domain_versions")}
            else:
                command.upgrade(config, target)
        command.check(config)
        # Day 5 leaves the complete Day 4 schema content intact through downgrade/re-upgrade.
        with get_engine().connect() as connection:
            before_day5 = {table: connection.execute(text("SELECT * FROM " + table + " ORDER BY id")).mappings().all()
                           for table in ("courses", "domain_versions", "competencies", "skills", "skill_prerequisites")}
        command.downgrade(config, "0004_domain_publishing")
        assert not {"learners", "enrollments", "learner_skill_states"} & set(inspect(get_engine()).get_table_names())
        command.upgrade(config, "head")
        with get_engine().connect() as connection:
            for table, expected in before_day5.items():
                assert connection.execute(text("SELECT * FROM " + table + " ORDER BY id")).mappings().all() == expected
        command.check(config)
        # Day 6 preserves populated Day 5 records through downgrade/re-upgrade.
        with get_engine().begin() as connection:
            connection.execute(Learner.__table__.insert().values(id="migration-learner", principal_subject="migration-subject"))
            connection.execute(Enrollment.__table__.insert().values(
                id="migration-enrollment", learner_id="migration-learner",
                course_id="00000000-0000-0000-0000-000000000001",
                domain_version_id="00000000-0000-0000-0000-000000000003"))
            connection.execute(LearnerSkillState.__table__.insert().values(
                enrollment_id="migration-enrollment", skill_id="00000000-0000-0000-0000-000000000005",
                domain_version_id="00000000-0000-0000-0000-000000000003"))
            day5_tables = ("courses", "domain_versions", "competencies", "skills", "skill_prerequisites",
                           "learners", "enrollments", "learner_skill_states")
            before_day6 = {table: connection.execute(text("SELECT * FROM " + table)).mappings().all() for table in day5_tables}
        command.downgrade(config, "0005_learners")
        assert not {"policy_versions", "activity_variants", "component_activity_mappings"} & set(inspect(get_engine()).get_table_names())
        command.upgrade(config, "head")
        with get_engine().connect() as connection:
            for table, expected in before_day6.items():
                assert connection.execute(text("SELECT * FROM " + table)).mappings().all() == expected
        command.check(config)
        # Day 7 is additive; populated reviewed catalog and learner records survive.
        from app.planner_fixtures import synthetic_input
        fixture = synthetic_input()
        with get_engine().begin() as connection:
            for policy in [fixture.learning_science_policy, fixture.safety_policy]:
                values = policy.model_dump()
                values["id"] = str(policy.id)
                values["created_at"] = policy.created_at.replace(tzinfo=None)
                values["reviewed_at"] = policy.reviewed_at.replace(tzinfo=None)
                values["rules"] = policy.rules.model_dump(mode="json")
                connection.execute(PolicyVersion.__table__.insert().values(**values))
            for activity in fixture.activities:
                values = activity.model_dump(exclude={"mappings"})
                values["created_at"] = activity.created_at.replace(tzinfo=None)
                values["reviewed_at"] = activity.reviewed_at.replace(tzinfo=None)
                for field in ["id", "learning_science_policy_id", "safety_policy_id"]:
                    values[field] = str(values[field])
                connection.execute(ActivityVariant.__table__.insert().values(**values))
                for mapping in activity.mappings:
                    connection.execute(ComponentActivityMapping.__table__.insert().values(
                        activity_variant_id=str(activity.id), **mapping.model_dump()))
            day6_tables = (*day5_tables, "policy_versions", "activity_variants", "component_activity_mappings")
            before_day7 = {table: connection.execute(text("SELECT * FROM " + table)).mappings().all() for table in day6_tables}
        command.downgrade(config, "0006_catalog")
        assert not {"loop_plans", "loop_steps"} & set(inspect(get_engine()).get_table_names())
        command.upgrade(config, "head")
        with get_engine().connect() as connection:
            for table, expected in before_day7.items():
                assert connection.execute(text("SELECT * FROM " + table)).mappings().all() == expected
        command.check(config)
        # Day 8 preserves populated Day 7 plans, ordered steps, catalogs and states.
        with get_engine().begin() as connection:
            connection.execute(LoopPlan.__table__.insert().values(
                id="migration-plan", enrollment_id="migration-enrollment",
                domain_version_id="00000000-0000-0000-0000-000000000003",
                target_skill_id="00000000-0000-0000-0000-000000000005",
                focus_skill_id="00000000-0000-0000-0000-000000000005",
                learning_science_policy_id=str(fixture.learning_science_policy.id),
                safety_policy_id=str(fixture.safety_policy.id), input_fingerprint="a" * 64,
                time_budget_minutes=25, estimated_minutes=10, decision={"migration": "preserve"},
                input_snapshot=fixture.model_dump(mode="json")))
            connection.execute(LoopStep.__table__.insert().values(
                loop_plan_id="migration-plan", position=1,
                domain_version_id="00000000-0000-0000-0000-000000000003",
                skill_id="00000000-0000-0000-0000-000000000005",
                activity_variant_id=str(fixture.activities[-1].id), role="whole_task",
                components=["learning_tasks"], support_level="minimal", estimated_minutes=10, rationale="Preserve step"))
            day7_tables = (*day6_tables, "loop_plans", "loop_steps")
            before_day8 = {table: connection.execute(text("SELECT * FROM " + table)).mappings().all() for table in day7_tables}
        command.downgrade(config, "0007_planner")
        assert not {"activity_generations", "activities"} & set(inspect(get_engine()).get_table_names())
        command.upgrade(config, "head")
        with get_engine().connect() as connection:
            for table, expected in before_day8.items():
                assert connection.execute(text("SELECT * FROM " + table)).mappings().all() == expected
        command.check(config)
        with get_engine().connect() as connection:
            assert connection.execute(text("SELECT * FROM courses ORDER BY code")).mappings().all() == before_day3
        command.downgrade(config, "0002_course_lifecycle")
        assert "domain_versions" not in inspect(get_engine()).get_table_names()
        with get_engine().connect() as connection:
            assert connection.execute(text("SELECT * FROM courses ORDER BY code")).mappings().all() == before_day3
        command.upgrade(config, "head")
        command.check(config)
        with get_engine().connect() as connection:
            legacy = connection.execute(text("SELECT * FROM courses WHERE code = 'LEGACY'")).mappings().one()
            assert legacy["created_by"] == "dev-author"
            assert legacy["created_at"] == legacy["updated_at"]
            assert legacy["archived_at"] is None
            assert legacy["description"] == "Preserved evidence reference"
        command.downgrade(config, "0001_courses")
        with get_engine().connect() as connection:
            assert connection.execute(text("SELECT title FROM courses WHERE code = 'LEGACY'")).scalar_one() == "Preserved title"
        command.upgrade(config, "head")
        command.check(config)
        with get_engine().begin() as connection:
            for model in CLEANUP_MODELS:
                connection.execute(delete(model))
        get_engine().dispose()
        get_engine.cache_clear()
        get_settings.cache_clear()
    engine = create_engine(url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def mysql_client(mysql_engine, client):
    def session_override():
        with Session(mysql_engine, expire_on_commit=False) as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    yield client
    with mysql_engine.begin() as connection:
        for model in CLEANUP_MODELS:
            connection.execute(delete(model))
