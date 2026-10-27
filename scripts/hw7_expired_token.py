#!/usr/bin/env python3

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import crud  # noqa: E402
import jwt_auth  # noqa: E402
from db import db_session_basede26  # noqa: E402

db = db_session_basede26()
try:
    print(jwt_auth.create_access_token(crud.get_user_by_username(db, sys.argv[1]), ttl_seconds=-60))
finally:
    db.close()
