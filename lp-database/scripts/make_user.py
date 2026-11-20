"""Make a PORTAL_USERS entry.  usage: python3 scripts/make_user.py <userid> <role: admin|user> [password]
Prints the entry and, if no password was given, a generated one. Join entries with ';' in the
PORTAL_USERS environment variable on Render. Only the hash is stored; keep the password elsewhere."""
import hashlib, os, secrets, sys
uid, role = sys.argv[1].strip().lower(), sys.argv[2]
pw = sys.argv[3] if len(sys.argv) > 3 else "-".join(secrets.token_urlsafe(4) for _ in range(3))
salt = os.urandom(16)
h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 310000).hex()
print(f"{uid}:{role}:pbkdf2_sha256$310000${salt.hex()}${h}")
if len(sys.argv) <= 3: print("password:", pw, file=sys.stderr)
