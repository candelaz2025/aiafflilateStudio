"""Reset a forgotten password from the server shell. Never accessible through the web UI.

Prints a one-time temporary password; sign in with it, then change it in the web
(เมนู API ของฉัน → เปลี่ยนรหัสผ่าน). All of that account's sessions are signed out.
"""
import os
import secrets
import sqlite3
import string
import sys
from pathlib import Path

from argon2 import PasswordHasher

# Same parameters as community_app.PH, so the hash verifies the same way.
PH = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)


def temporary_password():
    # Login and change-password both require letters and digits.
    alphabet = string.ascii_letters + string.digits
    while True:
        value = ''.join(secrets.choice(alphabet) for _ in range(16))
        if any(c.isalpha() for c in value) and any(c.isdigit() for c in value):
            return value


if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Usage: python reset_password.py email@example.com')
    email=sys.argv[1].lower().strip()
    data=Path(os.getenv('COMMUNITY_DATA_DIR',Path(__file__).parent/'data')).resolve()
    password=temporary_password()
    with sqlite3.connect(data/'community.db') as db:
        row=db.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()
        if not row:
            raise SystemExit('Account not found: check the email')
        db.execute('UPDATE users SET password_hash=? WHERE id=?',(PH.hash(password),row[0]))
        db.execute('DELETE FROM sessions WHERE user_id=?',(row[0],))
        # Clear lockouts from the failed attempts that usually come before a reset.
        db.execute('DELETE FROM login_attempts WHERE email=?',(email,))
        db.execute('DELETE FROM login_failures WHERE email=?',(email,))
    print('Temporary password:',password)
    print('Sign in with it, then change it at API ของฉัน → เปลี่ยนรหัสผ่าน.')
