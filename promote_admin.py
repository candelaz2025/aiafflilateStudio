"""Promote an existing account locally. Never accessible through the web UI."""
import os
import sqlite3
import sys
from pathlib import Path

if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Usage: python promote_admin.py email@example.com')
    data=Path(os.getenv('COMMUNITY_DATA_DIR',Path(__file__).parent/'data')).resolve()
    with sqlite3.connect(data/'community.db') as db:
        r=db.execute('UPDATE users SET role=? WHERE email=?',('admin',sys.argv[1].lower().strip()))
        if r.rowcount==0:
            raise SystemExit('Account not found: register first')
    print('Granted admin role. Sign out and sign in again.')
