"""Create local credentials without printing them or overwriting existing values."""
import os
import json
from pathlib import Path
import secrets


def main():
    target = Path(__file__).resolve().parents[1] / ".env"
    password = secrets.token_hex(24)
    content = (
        "MYSQL_DATABASE=learning_loop\nMYSQL_USER=loop_app\n"
        "MYSQL_PASSWORD={password}\nMYSQL_ROOT_PASSWORD={root}\nAPI_KEY={key}\n"
        "DATABASE_URL=mysql+pymysql://loop_app:{password}@127.0.0.1:3307/"
        "learning_loop?charset=utf8mb4\n"
    ).format(password=password, root=secrets.token_hex(24), key=secrets.token_hex(32))
    principals = json.dumps([
        {"subject": "dev-" + role, "roles": [role], "api_key": secrets.token_hex(32)}
        for role in ["instructor", "learner", "integration"]
    ], separators=(",", ":"))
    principal_line = "DEV_PRINCIPALS=" + principals + "\n"
    try:
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = target.read_text()
        if not any(line.strip().startswith(("DEV_PRINCIPALS=", "export DEV_PRINCIPALS=")) for line in existing.splitlines()):
            with target.open("a") as handle:
                handle.write(("" if existing.endswith("\n") else "\n") + principal_line)
            print("Added development role credentials; preserved existing credentials.")
        else:
            print(".env already contains development principals; preserved existing credentials.")
        return
    with os.fdopen(fd, "w") as handle:
        handle.write(content)
        handle.write(principal_line)
    print("Created .env with local credentials. Do not commit this file.")


if __name__ == "__main__":
    main()
