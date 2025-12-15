from db import _conn, ensure_tables
def add_fav(user_id, item_id):
    ensure_tables()
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO favorites (user_id,item_id) VALUES (?,?)", (user_id, item_id))
        c.commit()

def remove_fav(user_id, item_id):
    with _conn() as c:
        c.execute("DELETE FROM favorites WHERE user_id=? AND item_id=?", (user_id, item_id))
        c.commit()

def list_favs(user_id):
    with _conn() as c:
        return [r[0] for r in c.execute("SELECT item_id FROM favorites WHERE user_id=?", (user_id,))]

