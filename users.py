from db import _conn, ensure_tables

import os, hashlib, base64, hmac

def _hash_pw(pw: str, salt: bytes | None = None):
    if salt is None: salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return base64.b64encode(dk).decode(), base64.b64encode(salt).decode()

def _verify_pw(pw: str, salt_b64: str, hash_b64: str) -> bool:
    salt = base64.b64decode(salt_b64.encode())
    expected = base64.b64decode(hash_b64.encode())
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return hmac.compare_digest(dk, expected)

def create_user(email: str, password: str, api_key: str) -> int:
    ensure_tables()
    with _conn() as c:
        row = c.execute("SELECT user_id FROM users WHERE email=?", (email,)).fetchone()
        if row: return row["user_id"]
        pw_hash, salt = _hash_pw(password)
        cur = c.cursor()
        cur.execute("INSERT INTO users(email,password_hash,salt,api_key) VALUES(?,?,?,?)",
                    (email, pw_hash, salt, api_key))
        c.commit()
        return cur.lastrowid

def verify_user(email: str, password: str) -> int | None:
    with _conn() as c:
        row = c.execute("SELECT user_id,password_hash,salt FROM users WHERE email=?", (email,)).fetchone()
        if not row: return None
        return row["user_id"] if _verify_pw(password, row["salt"], row["password_hash"]) else None

def get_api_key(user_id: int) -> str | None:
    with _conn() as c:
        row = c.execute("SELECT api_key FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row["api_key"] if row else None