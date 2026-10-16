"""Create the first administrator through a private terminal prompt."""

from getpass import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.local_auth import create_admin_account, ensure_account_table


def main() -> int:
    print("Create an administrator for AI Business Analytics Assistant")
    email = input("Admin email: ").strip()
    password = getpass("Admin password (12+ characters): ")
    confirmation = getpass("Confirm admin password: ")
    if password != confirmation:
        print("Passwords did not match. No account was created.")
        return 1

    try:
        ensure_account_table()
        created, message = create_admin_account(email, password)
    except Exception as exc:
        print(f"Could not create the admin account ({type(exc).__name__}). Check PostgreSQL and .env.")
        return 1
    print(message)
    return 0 if created else 1


if __name__ == "__main__":
    raise SystemExit(main())
