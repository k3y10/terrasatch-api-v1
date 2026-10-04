"""Run locally on the server; passwords are entered privately, never as CLI arguments."""
import getpass
import json
import os
from pathlib import Path

from app import password_hash

path = Path(os.environ.get("INBOX_USERS_FILE", "data/users.json"))
email = input("Team member email: ").strip().lower()
mailboxes = [m.strip().lower() for m in input("Allowed mailboxes, comma separated: ").split(",")]
if not email or not mailboxes or any(not m.endswith("@terrasatch.com") for m in mailboxes):
    raise SystemExit("Use explicit @terrasatch.com mailbox addresses")
password = getpass.getpass("New password (16+ characters): ")
if len(password) < 16 or password != getpass.getpass("Confirm password: "):
    raise SystemExit("Passwords must match and contain at least 16 characters")
users = json.loads(path.read_text()) if path.exists() else {}
users[email] = {"password_hash": password_hash(password), "mailboxes": mailboxes}
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(users, indent=2))
path.chmod(0o600)
print("User saved. Previous sessions are invalidated if the password changed.")
