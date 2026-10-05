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
        {"subject": "dev-" + name, "roles": [role], "api_key": secrets.token_hex(32)}
        for name, role in [("instructor", "instructor"), ("learner", "learner"),
                           ("learner-2", "learner"), ("integration", "integration")]
    ], separators=(",", ":"))
    principal_line = "DEV_PRINCIPALS=" + principals + "\n"
    try:
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = target.read_text()
        lines = existing.splitlines(keepends=True)
        principal_indices = [i for i, line in enumerate(lines)
                             if line.strip().startswith(("DEV_PRINCIPALS=", "export DEV_PRINCIPALS="))]
        if not principal_indices:
            with target.open("a") as handle:
                handle.write(("" if existing.endswith("\n") else "\n") + principal_line)
            print("Added development role credentials; preserved existing credentials.")
        else:
            if len(principal_indices) != 1:
                raise SystemExit("Expected one DEV_PRINCIPALS setting; existing file left unchanged.")
            index = principal_indices[0]
            raw = lines[index].split("=", 1)[1].strip()
            if raw.startswith("'") and raw.endswith("'"):
                raw = raw[1:-1]
            try:
                entries = json.loads(raw)
                if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
                    raise ValueError
            except (ValueError, TypeError):
                raise SystemExit("DEV_PRINCIPALS must be a JSON array; existing file left unchanged.")
            learner_count = sum(entry.get("roles") == ["learner"] for entry in entries)
            subjects = {entry.get("subject") for entry in entries}
            if learner_count < 2:
                for number in range(learner_count + 1, 3):
                    name = "dev-learner" if number == 1 else "dev-learner-2"
                    while name in subjects:
                        name += "-synthetic"
                    if learner_count < 2:
                        entries.append({"subject": name, "roles": ["learner"], "api_key": secrets.token_hex(32)})
                        subjects.add(name)
                        learner_count += 1
                prefix = lines[index].split("=", 1)[0]
                lines[index] = prefix + "=" + json.dumps(entries, separators=(",", ":")) + "\n"
                target.write_text("".join(lines))
                print("Added missing synthetic learner credentials; preserved all existing credentials.")
            else:
                print(".env already contains two learner credentials; preserved existing credentials.")
        return
    with os.fdopen(fd, "w") as handle:
        handle.write(content)
        handle.write(principal_line)
    print("Created .env with local credentials. Do not commit this file.")


if __name__ == "__main__":
    main()
