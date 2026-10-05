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
from app.models import Competency, Course, DomainVersion, Skill, SkillPrerequisite

TEST_API_KEY = "synthetic-test-key-32-characters-long"
ROLE_KEYS = {role: "synthetic-" + role + "-key-32-characters-long" for role in ["instructor", "learner", "integration", "author"]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", TEST_API_KEY)
    monkeypatch.setenv("DEV_PRINCIPALS", json.dumps([
        {"subject": "other-" + role, "roles": [role], "api_key": key}
        for role, key in ROLE_KEYS.items()
    ]))
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
    return {role: {"X-API-Key": key} for role, key in ROLE_KEYS.items()}


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
            for model in (SkillPrerequisite, Skill, Competency, DomainVersion, Course):
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
        for model in (SkillPrerequisite, Skill, Competency, DomainVersion, Course):
            connection.execute(delete(model))
