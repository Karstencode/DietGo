import calendar
import hashlib
import json
import os
import sqlite3
from datetime import date, datetime, timedelta

import streamlit as st

from main import (
    Value, CategoryLimit, FoodEntry, DietDay, SpendingEntry,
    categories_satisfied, compute_streaks, compute_budget_streaks,
    period_met, period_start_of, next_period_start,
    period_expenses, diet_rank, diet_score, STRINGS, MEALS, CATEGORIES, PERIODS, UNITS, LANGS,
    budget_allowance_factor,
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "streamlit_data.db")

ADMIN_USER = "admin"

MAX_DAYS = 60


def tr(key):
    lang = st.session_state.get("lang", "en")
    table = STRINGS.get(lang, STRINGS["en"])
    return table.get(key, key)


def budget_cat_display(c):
    """Translated label for a stored (English) budget category."""
    key = "budget_cat_" + c.lower().replace(" ", "_")
    return tr(key) if tr(key) != key else c


def unit_display(u):
    """Translated label for a stored (English) unit."""
    key = "unit_" + str(u).lower()
    return tr(key) if tr(key) != key else str(u)


def UNIT_INDEX(u):
    return UNITS.index(u) if u in UNITS else 0


# ------------------------------------------------------------- database

def get_db():
    return sqlite3.connect(DB_PATH)


def _add_column(conn, table, column, decl):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db():
    with get_db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users "
            "(username TEXT PRIMARY KEY, salt TEXT, hash TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS user_data "
            "(username TEXT PRIMARY KEY, json TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS leaderboards "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
            "access_code TEXT NOT NULL, owner TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memberships "
            "(leaderboard_id INTEGER NOT NULL, username TEXT NOT NULL, "
            "is_owner INTEGER DEFAULT 0, "
            "PRIMARY KEY (leaderboard_id, username))"
        )
        _add_column(conn, "leaderboards", "owner", "TEXT")
        _add_column(conn, "leaderboards", "is_public", "INTEGER DEFAULT 0")
        _add_column(conn, "memberships", "is_owner", "INTEGER DEFAULT 0")
        _add_column(conn, "memberships", "share", "TEXT DEFAULT 'both'")


def hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), 200_000
    ).hex()


def signup(username, password):
    if not username.strip():
        return False, tr("username_empty")
    if len(password) < 4:
        return False, tr("password_short")
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            return False, tr("username_exists")
        salt = os.urandom(16).hex()
        conn.execute(
            "INSERT INTO users (username, salt, hash) VALUES (?, ?, ?)",
            (username, salt, hash_password(password, salt)),
        )
    return True, tr("account_created")


def signin(username, password):
    with get_db() as conn:
        row = conn.execute(
            "SELECT salt, hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if not row:
        return False, tr("user_not_found")
    salt, expected = row
    if hash_password(password, salt) != expected:
        return False, tr("wrong_password")
    return True, tr("signed_in")


def delete_account(username, password):
    """Delete the account and its data after password check."""
    if not signin(username, password)[0]:
        return False, tr("wrong_password")
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.execute("DELETE FROM user_data WHERE username = ?", (username,))
    return True, tr("account_deleted")


def reset_password(username, new_password):
    """Overwrite an account's password hash (no way to recover the old one)."""
    if not username.strip():
        return False, tr("username_empty")
    if len(new_password) < 4:
        return False, tr("password_short")
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            return False, tr("user_not_found")
    salt = os.urandom(16).hex()
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET salt = ?, hash = ? WHERE username = ?",
            (salt, hash_password(new_password, salt), username),
        )
    return True, tr("password_reset")


# -------------------------------------------------------------- groups

SHARE_OPTIONS = ("diet", "budget", "both")


def _valid_share(share):
    return share if share in SHARE_OPTIONS else "both"


def create_group(name, code, username=None, is_public=False):
    """Create a group. `username` (optional) becomes its owner and first member.

    Admin-created groups are always public (joinable by name only). User-created
    groups are private by default and require an access code to join."""
    name = (name or "").strip()
    code = (code or "").strip()
    if not username or username == ADMIN_USER:
        is_public = True
    if not name or (not is_public and not code):
        return False, "name_empty"
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM leaderboards WHERE name = ?", (name,)).fetchone():
            return False, "group_exists"
        cur = conn.execute(
            "INSERT INTO leaderboards (name, access_code, owner, is_public) VALUES (?, ?, ?, ?)",
            (name, code, username or ADMIN_USER, 1 if is_public else 0),
        )
        if username:
            conn.execute(
                "INSERT INTO memberships (leaderboard_id, username, is_owner, share) VALUES (?, ?, 1, 'both')",
                (cur.lastrowid, username),
            )
    return True, "group_created"


def join_group(name, code, username, share="both"):
    """Join an existing group by name. Private groups need the access code;
    public groups can be joined with just the name.

    `share` is what the member lets the group owner view: 'diet', 'budget'
    or 'both' (default)."""
    name = (name or "").strip()
    code = (code or "").strip()
    if not name:
        return False, "wrong_access_code"
    share = _valid_share(share)
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, access_code, is_public FROM leaderboards WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return False, "wrong_access_code"
        lid, group_code, is_public = row[0], row[1] or "", bool(row[2])
        if not is_public and code != group_code:
            return False, "wrong_access_code"
        if conn.execute(
            "SELECT 1 FROM memberships WHERE leaderboard_id = ? AND username = ?",
            (lid, username),
        ).fetchone():
            return False, "already_member"
        conn.execute(
            "INSERT INTO memberships (leaderboard_id, username, is_owner, share) VALUES (?, ?, 0, ?)",
            (lid, username, share),
        )
    return True, "group_joined"


def group_members(lid):
    """Members of a group as [{username, is_owner, share}] sorted by username."""
    with get_db() as conn:
        return [
            {"username": r[0], "is_owner": bool(r[1]), "share": r[2] or "both"}
            for r in conn.execute(
                "SELECT username, is_owner, share FROM memberships "
                "WHERE leaderboard_id = ? ORDER BY username", (lid,),
            ).fetchall()
        ]


def member_share(lid, username):
    """What a member lets the group owner view ('diet' | 'budget' | 'both')."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT share FROM memberships WHERE leaderboard_id = ? AND username = ?",
            (lid, username),
        ).fetchone()
    return (row[0] or "both") if row else "both"


def set_member_share(lid, username, share):
    """A member updates what the owner may view of their records."""
    share = _valid_share(share)
    with get_db() as conn:
        if not conn.execute(
            "SELECT 1 FROM memberships WHERE leaderboard_id = ? AND username = ?",
            (lid, username),
        ).fetchone():
            return False
        conn.execute(
            "UPDATE memberships SET share = ? WHERE leaderboard_id = ? AND username = ?",
            (share, lid, username),
        )
    return True


def granted_share(share, kind):
    """True when a member's share setting allows viewing `kind` ('diet'/'budget')."""
    share = _valid_share(share)
    return share == "both" or share == kind


def is_group_owner(lid, username):
    with get_db() as conn:
        return conn.execute(
            "SELECT 1 FROM memberships WHERE leaderboard_id = ? AND username = ? AND is_owner = 1",
            (lid, username),
        ).fetchone() is not None


def group_owner(lid):
    """The username recorded as the group's creator."""
    with get_db() as conn:
        row = conn.execute("SELECT owner FROM leaderboards WHERE id = ?", (lid,)).fetchone()
        return row[0] if row else None


def leave_group(lid, username):
    """Remove a user's membership; ranks recompute on next render."""
    with get_db() as conn:
        conn.execute(
            "DELETE FROM memberships WHERE leaderboard_id = ? AND username = ?", (lid, username)
        )
    return True, "group_left"


def group_public(lid):
    """True when the group is public (joinable by name only)."""
    with get_db() as conn:
        row = conn.execute("SELECT is_public FROM leaderboards WHERE id = ?", (lid,)).fetchone()
        return bool(row and row[0])


def can_manage_group(lid, username):
    """Owner members manage their group; the admin only manages public groups
    (the ones the admin created) and never touches private groups."""
    if username == ADMIN_USER:
        return group_public(lid)
    return is_group_owner(lid, username)


def kick_member(lid, username, actor):
    """An owner (or admin, in an admin-created group) removes a member."""
    if not can_manage_group(lid, actor):
        return False, "not_allowed"
    if username == actor:
        return False, "not_allowed"
    with get_db() as conn:
        conn.execute(
            "DELETE FROM memberships WHERE leaderboard_id = ? AND username = ?", (lid, username)
        )
    return True, "member_kicked"


def promote_owner(lid, username, actor):
    """An owner promotes an existing member to co-owner."""
    if not can_manage_group(lid, actor):
        return False, "not_allowed"
    with get_db() as conn:
        if not conn.execute(
            "SELECT 1 FROM memberships WHERE leaderboard_id = ? AND username = ?",
            (lid, username),
        ).fetchone():
            return False, "not_a_member"
        conn.execute(
            "UPDATE memberships SET is_owner = 1 WHERE leaderboard_id = ? AND username = ?",
            (lid, username),
        )
    return True, "owner_promoted"


def demote_owner(lid, username, actor):
    """An owner removes co-owner status from another owner (not themselves)."""
    if not can_manage_group(lid, actor):
        return False, "not_allowed"
    if username == actor:
        return False, "not_allowed"
    with get_db() as conn:
        if not conn.execute(
            "SELECT 1 FROM memberships WHERE leaderboard_id = ? AND username = ? AND is_owner = 1",
            (lid, username),
        ).fetchone():
            return False, "not_a_member"
        conn.execute(
            "UPDATE memberships SET is_owner = 0 WHERE leaderboard_id = ? AND username = ?",
            (lid, username),
        )
    return True, "owner_demoted"


def delete_group(lid, actor):
    """Delete a group and its memberships. Allowed for its owner(s) or, for
    public groups, the admin."""
    if not can_manage_group(lid, actor):
        return False, "not_allowed"
    with get_db() as conn:
        conn.execute("DELETE FROM leaderboards WHERE id = ?", (lid,))
        conn.execute("DELETE FROM memberships WHERE leaderboard_id = ?", (lid,))
        rows = [r[0] for r in conn.execute("SELECT id FROM leaderboards ORDER BY id").fetchall()]
        for new_id, old_id in enumerate(rows, start=1):
            if old_id != new_id:
                conn.execute("UPDATE leaderboards SET id = ? WHERE id = ?", (new_id, old_id))
                conn.execute(
                    "UPDATE memberships SET leaderboard_id = ? WHERE leaderboard_id = ?",
                    (new_id, old_id),
                )
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_sequence'").fetchone():
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'leaderboards'")
            conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('leaderboards', ?)",
                         (len(rows),))
    return True, "group_removed"


def my_groups(username):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT l.id, l.name, l.access_code, l.owner, l.is_public, m.is_owner "
            "FROM leaderboards l JOIN memberships m ON m.leaderboard_id = l.id "
            "WHERE m.username = ? ORDER BY l.name",
            (username,),
        ).fetchall()
    groups = []
    for lid, name, code, owner, is_public, user_is_owner in rows:
        members = group_members(lid)
        groups.append({
            "id": lid, "name": name, "access_code": code, "owner": owner,
            "is_public": bool(is_public),
            "members": members, "member_count": len(members),
            "user_is_owner": bool(user_is_owner),
        })
    return groups


def all_groups():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, access_code, owner, is_public FROM leaderboards ORDER BY name"
        ).fetchall()
    groups = []
    for lid, name, code, owner, is_public in rows:
        members = group_members(lid)
        groups.append({
            "id": lid, "name": name, "access_code": code, "owner": owner,
            "is_public": bool(is_public),
            "members": members, "member_count": len(members),
        })
    return groups


def rename_group(lid, new_name, actor):
    if not new_name:
        return False, "name_empty"
    if not can_manage_group(lid, actor):
        return False, "not_allowed"
    with get_db() as conn:
        if conn.execute(
            "SELECT 1 FROM leaderboards WHERE name = ? AND id != ?", (new_name, lid)
        ).fetchone():
            return False, "group_exists"
        conn.execute("UPDATE leaderboards SET name = ? WHERE id = ?", (new_name, lid))
    return True, "group_renamed"


def change_access_code(lid, new_code, actor):
    new_code = new_code.strip()
    if not new_code:
        return False, "code_empty"
    if not can_manage_group(lid, actor):
        return False, "not_allowed"
    with get_db() as conn:
        conn.execute("UPDATE leaderboards SET access_code = ? WHERE id = ?", (new_code, lid))
    return True, "code_changed"


def rename_user(old, new):
    """Rename an account, moving its data and group memberships."""
    if old.strip() == ADMIN_USER:
        return False, "cannot_rename_admin"
    if not new.strip():
        return False, "username_empty"
    if old == new:
        return True, "username_changed"
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE username = ?", (old,)).fetchone():
            return False, "user_not_found"
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (new,)).fetchone():
            return False, "username_exists"
        conn.execute("UPDATE users SET username = ? WHERE username = ?", (new, old))
        conn.execute("UPDATE user_data SET username = ? WHERE username = ?", (new, old))
        conn.execute("UPDATE memberships SET username = ? WHERE username = ?", (new, old))
        conn.execute("UPDATE leaderboards SET owner = ? WHERE owner = ?", (new, old))
    return True, "username_changed"


def rank_users(usernames):
    """Rank members by combined diet score as of today."""
    board = []
    today = date.today()
    for user in usernames:
        data = load_user_data(user)
        day_s, week_s, month_s = streaks_with_carry(data, today)
        board.append((user, day_s, week_s, month_s, diet_score(day_s, week_s, month_s)))
    board.sort(key=lambda r: r[4], reverse=True)
    return board


def admin_password():
    try:
        return st.secrets.get("admin_password") or "admin123"
    except Exception:
        return os.environ.get("ADMIN_PASSWORD") or "admin123"


def ensure_admin():
    """Create the reserved admin account on first start."""
    if ADMIN_USER in all_usernames():
        return
    salt = os.urandom(16).hex()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (username, salt, hash) VALUES (?, ?, ?)",
            (ADMIN_USER, salt, hash_password(admin_password(), salt)),
        )


def all_usernames():
    with get_db() as conn:
        return [r[0] for r in conn.execute("SELECT username FROM users ORDER BY username").fetchall()]


def default_data():
    return {
        "diet_categories": {"calories": {"name": "Calories", "unit": "kcal", "limit": 2000}},
        "days": {},
        "budget_period": "month",
        "budget_limit": 8000,
        "spends": {},
        "streak_carry": {},
        "budget_carry": {},
        "period_log": {},
    }


def load_user_data(username):
    with get_db() as conn:
        row = conn.execute(
            "SELECT json FROM user_data WHERE username = ?", (username,)
        ).fetchone()
    if row:
        try:
            data = json.loads(row[0])
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            data.setdefault("diet_categories", {})
            data["diet_categories"].setdefault(
                "calories", {"name": "Calories", "unit": "kcal", "limit": 2000}
            )
            data.setdefault("days", {})
            data.setdefault("spends", {})
            data.setdefault("budget_period", "month")
            data.setdefault("budget_limit", 8000)
            data.setdefault("streak_carry", {})
            data.setdefault("budget_carry", {})
            if "period_pending" in data:
                data.pop("period_pending", None)
                data.setdefault("period_log", {})
            data.setdefault("period_log", {})
            return data
    return default_data()


def save_user_data(username, data):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO user_data (username, json) VALUES (?, ?) "
            "ON CONFLICT(username) DO UPDATE SET json = excluded.json",
            (username, json.dumps(data)),
        )


# ------------------------------------------------ storage limit + streaks

def stored_day_count(data):
    """Distinct dates that store any diet or budget data."""
    days = {k for k, v in (data.get("days") or {}).items() if v}
    spends = {k for k, v in (data.get("spends") or {}).items() if v}
    return len(days | spends)


def storage_full(data):
    return stored_day_count(data) >= MAX_DAYS


def storage_blocker(data, day):
    """True when `day` is brand new (still no data) and storage is full."""
    if not storage_full(data):
        return False
    iso = day.isoformat()
    return not ((data.get("days", {}).get(iso)) or (data.get("spends", {}).get(iso)))


def _ordered_stored_dates(data):
    keys = {k for k, v in (data.get("days") or {}).items() if v}
    keys |= {k for k, v in (data.get("spends") or {}).items() if v}
    return sorted(keys)


def _new_period_log(kind, start):
    """Fresh incremental tracker for the boundary week/month.

    `dates` lists the ISO dates dropped while they belonged to this period (in
    chronological order); `ok` records that every dropped diet day was
    compliant; `spent`/`has_entries` accumulate the dropped spend."""
    total = 7 if kind == "week" else calendar.monthrange(start.year, start.month)[1]
    return {"start": start.isoformat(), "total": total,
            "dates": [], "ok": True, "spent": 0, "has_entries": False}


def _log_complete(lg):
    return lg is not None and len(lg.get("dates", ())) >= lg.get("total", 0) and lg["ok"]


def _refresh_carry_on_drop(data, d0, d1):
    """Bank streak counts before the oldest stored day `d0` is dropped.

    The new boundary is `d1` (next-oldest date, or None when nothing remains).
    A day carry grows by one when the dropped day was compliant and rows still
    in storage sit on the very next day; any gap or over-limit day resets it.
    Week/month carries are banked from an incremental period log that records
    every day as it drops out, so a period counts even when the storage window
    can never hold it whole. Streaks are added back only onto an unbroken run.
    """
    days = build_all_days(data)
    cats = diet_categories(data)
    spends = spends_objects(data)
    base = data["budget_period"]
    limit = int(data["budget_limit"])

    sc = dict(data.get("streak_carry") or {})
    bc = dict(data.get("budget_carry") or {})
    log = dict(data.get("period_log") or {})

    def reset_period_log(kind, key, d):
        log[key] = _new_period_log(kind, period_start_of(kind, d))

    if d1 is None:
        data["streak_carry"] = {}
        data["budget_carry"] = {}
        data["period_log"] = {}
        return

    if d0.isoformat() in (data.get("days") or {}):
        d_ok = d0 in days and days[d0].entries and categories_satisfied(days[d0], cats)
        sc["day"] = (sc.get("day", 0) + 1) if (d1 == d0 + timedelta(days=1) and d_ok) else 0

        for kind, key in (("week", "dweek"), ("month", "dmonth")):
            p0, p1 = period_start_of(kind, d0), period_start_of(kind, d1)
            lg = log.get(key)
            if not lg or lg.get("start") != p0.isoformat():
                lg = _new_period_log(kind, p0)
                log[key] = lg
            lg["dates"].append(d0.isoformat())
            lg["ok"] = lg["ok"] and d_ok
            if p1 == p0:
                log[key] = lg
            elif p1 == next_period_start(kind, p0):
                if _log_complete(lg):
                    sc[kind] = sc.get(kind, 0) + 1
                else:
                    sc[kind] = 0
                reset_period_log(kind, key, d1)
            else:
                sc[kind] = 0
                reset_period_log(kind, key, d1)

    if d0.isoformat() in (data.get("spends") or {}):
        for kind in ("day", "week", "month"):
            if budget_allowance_factor(base, kind, d0) is None:
                continue
            p0, p1 = period_start_of(kind, d0), period_start_of(kind, d1)
            if kind == "day":
                expenses = period_expenses(spends, kind, d0)
                comp = bool(expenses) and sum(int(e.price.amount) for e in expenses) <= \
                    limit * budget_allowance_factor(base, kind, d0)
                bc[kind] = (bc.get(kind, 0) + 1) if (p1 == next_period_start(kind, p0) and comp) else 0
                continue
            key = "b" + kind
            lg = log.get(key)
            if not lg or lg.get("start") != p0.isoformat():
                lg = _new_period_log(kind, p0)
                log[key] = lg
            exp = period_expenses(spends, kind, d0)
            spent = sum(int(e.price.amount) for e in exp)
            lg["dates"].append(d0.isoformat())
            lg["spent"] = lg.get("spent", 0) + spent
            lg["has_entries"] = lg.get("has_entries", False) or bool(exp)
            if p1 == p0:
                log[key] = lg
            elif p1 == next_period_start(kind, p0):
                if (_log_complete(lg) and lg["has_entries"]
                        and lg["spent"] <= limit * budget_allowance_factor(base, kind, d0)):
                    bc[kind] = bc.get(kind, 0) + 1
                else:
                    bc[kind] = 0
                reset_period_log(kind, key, d1)
            else:
                bc[kind] = 0
                reset_period_log(kind, key, d1)

    data["streak_carry"] = {k: v for k, v in sc.items() if v}
    data["budget_carry"] = {k: v for k, v in bc.items() if v}
    data["period_log"] = log


def drop_oldest_day(data):
    """Remove the single oldest stored day, banking streaks first."""
    keys = _ordered_stored_dates(data)
    if not keys:
        return False
    d0 = date.fromisoformat(keys[0])
    d1 = date.fromisoformat(keys[1]) if len(keys) > 1 else None
    _refresh_carry_on_drop(data, d0, d1)
    data.get("days", {}).pop(keys[0], None)
    data.get("spends", {}).pop(keys[0], None)
    return True


def drop_n_oldest(data, n):
    for _ in range(int(n)):
        if not drop_oldest_day(data):
            break


def streaks_with_carry(data, ref_date):
    days = build_all_days(data)
    log = data.get("period_log") or {}
    return compute_streaks(days, diet_categories(data), ref_date,
                           data.get("streak_carry") or {}, log)


def budget_streaks_with_carry(data, ref_date):
    spends = spends_objects(data)
    log = data.get("period_log") or {}
    return compute_budget_streaks(spends, data["budget_period"],
                                  int(data["budget_limit"]), ref_date,
                                  data.get("budget_carry") or {}, log)


# ------------------------------------------------------------ data helpers

def diet_categories(data):
    return {k: CategoryLimit(c["name"], c["unit"], c["limit"])
            for k, c in data["diet_categories"].items()}


def build_day(data, day):
    day_obj = DietDay(day)
    for e in data["days"].get(day.isoformat(), []):
        amount = Value(*e["amount"]) if e.get("amount") else None
        extras = {k: Value(*v) for k, v in e.get("extras", {}).items()}
        day_obj.add_entry(
            FoodEntry(e["name"], e["meal"], Value(e["calories"], "kcal"), amount, extras)
        )
    return day_obj


def build_all_days(data):
    days = {}
    for iso in data["days"]:
        try:
            d = date.fromisoformat(iso)
        except ValueError:
            continue
        days[d] = build_day(data, d)
    return days


def spends_objects(data):
    result = {}
    for iso, entries in data["spends"].items():
        try:
            d = date.fromisoformat(iso)
        except ValueError:
            continue
        result[d] = [
            SpendingEntry(e["name"], e["category"], Value(e["price"], "HKD"))
            for e in entries
        ]
    return result


def format_date(d):
    if st.session_state.lang == "zh":
        return f"{d.year}年{d.month}月{d.day}日 星期{tr('weekdays')[d.weekday()]}"
    return d.strftime("%A, %d %B %Y")


# --------------------------------------------------------------- calendar

def calendar_widget(prefix, status_fn):
    st.session_state.setdefault(f"{prefix}_selected", date.today())
    st.session_state.setdefault(f"{prefix}_month", date.today().replace(day=1))
    month = st.session_state[f"{prefix}_month"]

    c1, c2, c3 = st.columns([1, 3, 1])
    with c1:
        if st.button("◀", key=f"{prefix}_prev"):
            y, m = month.year, month.month - 1
            if m == 0:
                y, m = y - 1, 12
            st.session_state[f"{prefix}_month"] = date(y, m, 1)
            st.rerun()
    with c2:
        st.markdown(
            f"<div style='text-align:center'><b>{tr('months')[month.month - 1]} {month.year}</b></div>",
            unsafe_allow_html=True,
        )
    with c3:
        if st.button("▶", key=f"{prefix}_next"):
            y, m = month.year, month.month + 1
            if m == 13:
                y, m = y + 1, 1
            st.session_state[f"{prefix}_month"] = date(y, m, 1)
            st.rerun()

    cols = st.columns(7)
    for i, wd in enumerate(tr("weekdays")):
        cols[i].markdown(
            f"<div style='text-align:center'><b>{wd}</b></div>",
            unsafe_allow_html=True,
        )

    weeks = calendar.Calendar(firstweekday=calendar.MONDAY).monthdayscalendar(
        month.year, month.month
    )
    for week in weeks:
        cols = st.columns(7)
        for i, daynum in enumerate(week):
            if daynum == 0:
                continue
            d = date(month.year, month.month, daynum)
            diet, budget = status_fn(d)
            def dot(s):
                return {"ok": "🟢", "exceeded": "🔴", "none": "·"}[s]
            marks = f"{dot(diet)}{dot(budget)}"
            is_selected = d == st.session_state[f"{prefix}_selected"]
            label = (f"▶ {marks} {daynum}" if is_selected else f"{marks} {daynum}")
            if cols[i].button(label, key=f"{prefix}_day_{d.isoformat()}"):
                st.session_state[f"{prefix}_selected"] = d
                st.rerun()

    return st.session_state[f"{prefix}_selected"]


# -------------------------------------------------------------- status

def diet_status(data, d):
    if not data["days"].get(d.isoformat()):
        return "none"
    return "ok" if categories_satisfied(build_day(data, d), diet_categories(data)) else "exceeded"


def budget_status(data, d):
    if not data["spends"].get(d.isoformat()):
        return "none"
    spends = spends_objects(data)
    total = sum(int(e.price.amount) for e in period_expenses(spends, data["budget_period"], d))
    return "ok" if total <= data["budget_limit"] else "exceeded"


def day_status(data, d):
    diet = diet_status(data, d)
    budget = budget_status(data, d)
    if diet == "none" and budget == "none":
        return "none"
    if diet == "exceeded" or budget == "exceeded":
        return "exceeded"
    return "ok"


# ------------------------------------------------------------------ diet

def food_form(data, day):
    """Add a new entry, or edit the one chosen via its row's Edit button."""
    iso = day.isoformat()
    entries = data["days"].get(iso, [])
    cats = diet_categories(data)
    meal_labels = [tr(m) for m in MEALS]
    unit_labels = [unit_display(u) for u in UNITS]

    def clear_keys(extra_keys):
        for k in [f"fd_{iso}_name", f"fd_{iso}_meal", f"fd_{iso}_cal",
                  f"fd_{iso}_amt", f"fd_{iso}_unit"] + extra_keys:
            st.session_state.pop(k, None)

    editing = st.session_state.get(f"food_edit_{iso}")
    is_edit = editing is not None and 0 <= editing < len(entries)
    entry = entries[editing] if is_edit else None

    if is_edit:
        st.markdown(f"**{tr('edit')}: {entry['name']}**")
    with st.form(key=f"food_form_{iso}_{'e' if is_edit else 'n'}"):
        name = st.text_input(tr("food_name"), value=entry["name"] if entry else "",
                             key=f"fd_{iso}_name")
        meal = st.selectbox(tr("meal_type"), meal_labels,
                            index=MEALS.index(entry["meal"]) if entry else 0,
                            key=f"fd_{iso}_meal")
        calories = st.number_input(tr("calories"), min_value=0, step=10,
                                   value=int(entry["calories"]) if entry else 0,
                                   key=f"fd_{iso}_cal")
        amount = st.number_input(tr("amount"), min_value=0.0,
                                 value=float(entry["amount"][0]) if entry and entry["amount"] else 0.0,
                                 step=0.5, key=f"fd_{iso}_amt")
        unit = st.selectbox(
            tr("unit"), unit_labels,
            index=UNIT_INDEX(entry["amount"][1]) if entry and entry["amount"] and entry["amount"][1] in UNITS else 0,
            key=f"fd_{iso}_unit",
        )
        extras = {}
        for key, cat in cats.items():
            if key == "calories":
                continue
            cur = entry["extras"].get(key, [0, cat.unit])[0] if entry else 0
            extras[key] = st.number_input(
                f"{cat.name} ({unit_display(cat.unit)})", min_value=0.0,
                value=float(cur), step=0.5, key=f"fd_{iso}_ext_{key}")
        if st.form_submit_button(tr("save") if is_edit else tr("add")):
            if not name.strip():
                st.error(tr("name_empty"))
            else:
                new_entry = {
                    "name": name.strip(),
                    "meal": MEALS[meal_labels.index(meal)],
                    "calories": int(calories),
                    "amount": [float(amount), UNITS[unit_labels.index(unit)]] if amount > 0 else None,
                    "extras": {k: [float(v), cats[k].unit] for k, v in extras.items() if v > 0},
                }
                if is_edit:
                    entries[editing] = new_entry
                else:
                    data["days"].setdefault(iso, []).append(new_entry)
                st.session_state.pop(f"food_edit_{iso}", None)
                if is_edit:
                    st.session_state[f"diet_view_{iso}"] = "list"
                clear_keys([f"fd_{iso}_ext_{k}" for k in cats if k != "calories"])
                st.session_state.data = data
                save_user_data(st.session_state.user, data)
                st.rerun()
    if is_edit:
        if st.button(tr("cancel"), key=f"food_edit_cancel_{iso}"):
            clear_keys([f"fd_{iso}_ext_{k}" for k in cats if k != "calories"])
            st.session_state.pop(f"food_edit_{iso}", None)
            st.session_state[f"diet_view_{iso}"] = "list"
            st.rerun()


def food_row_text(e, cats):
    parts = [f"**{e['name']}**", tr(e["meal"])]
    if e.get("amount"):
        parts.append(f"{e['amount'][0]:g} {unit_display(e['amount'][1])}")
    parts.append(f"{e['calories']} kcal")
    for key, cat in cats.items():
        if key == "calories":
            continue
        val = e.get("extras", {}).get(key)
        if val:
            parts.append(f"{cat.name}: {val[0]:g} {unit_display(val[1])}")
    return " · ".join(parts)


def food_table(data, day, editable=True):
    entries = data["days"].get(day.isoformat(), [])
    if not entries:
        st.info(tr("no_food"))
        return
    cats = diet_categories(data)
    if not editable:
        rows = []
        for i, e in enumerate(entries, start=1):
            row = {"#": i, tr("food"): e["name"], tr("meal"): tr(e["meal"])}
            if e.get("amount"):
                amt_v, amt_u = e["amount"]
                row[tr("amount")] = f"{amt_v:g} {unit_display(amt_u)}"
            extras = e.get("extras") or {}
            for key, cat in cats.items():
                if key == "calories":
                    row[cat.name] = f"{e['calories']:g} {cat.unit}"
                elif key in extras:
                    v, u = extras[key]
                    row[cat.name] = f"{v:g} {unit_display(u)}"
            rows.append(row)
        st.table(rows)
        return

    iso = day.isoformat()
    for i, e in enumerate(entries):
        c1, c2, c3 = st.columns([8, 1, 1])
        with c1:
            st.markdown(food_row_text(e, cats))
        with c2:
            if st.button(tr("edit"), key=f"food_edit_btn_{iso}_{i}"):
                for k in [f"fd_{iso}_name", f"fd_{iso}_meal", f"fd_{iso}_cal",
                          f"fd_{iso}_amt", f"fd_{iso}_unit"]:
                    st.session_state.pop(k, None)
                st.session_state[f"food_edit_{iso}"] = i
                st.session_state[f"diet_view_{iso}"] = "add"
                st.rerun()
        with c3:
            if st.button(tr("remove"), key=f"food_rm_btn_{iso}_{i}"):
                st.session_state[f"food_rm_{iso}"] = i
                st.rerun()

    rm_i = st.session_state.get(f"food_rm_{iso}")
    if rm_i is not None and 0 <= rm_i < len(entries):
        st.warning(f"{tr('delete_warning')} **{entries[rm_i]['name']}**")
        c1, c2 = st.columns(2)
        with c1:
            if st.button(tr("cancel"), key=f"food_rm_no_{iso}"):
                st.session_state.pop(f"food_rm_{iso}", None)
                st.rerun()
        with c2:
            if st.button(tr("confirm"), key=f"food_rm_yes_{iso}"):
                entries.pop(rm_i)
                if not entries:
                    del data["days"][iso]
                st.session_state.pop(f"food_rm_{iso}", None)
                st.session_state.pop(f"food_edit_{iso}", None)
                st.session_state.data = data
                save_user_data(st.session_state.user, data)
                st.rerun()


def categories_manager(data):
    with st.expander(tr("category_limits")):
        st.write(tr("current_categories"))
        for key, c in data["diet_categories"].items():
            st.write(f"- {c['name']} ({unit_display(c['unit'])}): {c['limit']} {tr('per_day')}")

        cal_limit = st.number_input(tr("calorie_limit"), min_value=0, step=50,
                                    value=int(data["diet_categories"]["calories"]["limit"]),
                                    key="cal_limit_input")
        if st.button(tr("update_calorie_limit")):
            data["diet_categories"]["calories"]["limit"] = int(cal_limit)
            st.session_state.data = data
            save_user_data(st.session_state.user, data)
            st.rerun()

        with st.form("add_category"):
            cname = st.text_input(tr("category_name"), key="ac_name")
            cunit = st.text_input(tr("unit"), value="g", key="ac_unit")
            climit = st.number_input(tr("daily_limit"), min_value=0, step=1, value=10, key="ac_limit")
            if st.form_submit_button(tr("add_category")):
                if not cname.strip():
                    st.error(tr("name_empty"))
                elif cname.strip().lower() in data["diet_categories"]:
                    st.error(tr("category_exists"))
                else:
                    data["diet_categories"][cname.strip().lower()] = {
                        "name": cname.strip(), "unit": cunit.strip() or "g", "limit": int(climit),
                    }
                    for k in ("ac_name", "ac_unit", "ac_limit"):
                        st.session_state.pop(k, None)
                    st.session_state.data = data
                    save_user_data(st.session_state.user, data)
                    st.rerun()

        removable = [k for k in data["diet_categories"] if k != "calories"]
        editable = list(data["diet_categories"].keys())
        with st.form("edit_category"):
            to_edit = st.selectbox(tr("category"), editable, key="ec_sel")
            current = data["diet_categories"][to_edit]
            new_name = st.text_input(tr("category_name"), value=current["name"], key="ec_name")
            new_unit = st.text_input(tr("unit"), value=current["unit"], key="ec_unit")
            new_limit = st.number_input(tr("daily_limit"), min_value=0, step=1,
                                        value=int(current["limit"]), key="ec_limit")
            if st.form_submit_button(tr("edit_category")):
                if not new_name.strip():
                    st.error(tr("name_empty"))
                elif to_edit == "calories":
                    edited = data["diet_categories"]["calories"]
                    edited["unit"] = new_unit.strip() or "kcal"
                    edited["limit"] = int(new_limit)
                    for k in ("ec_name", "ec_unit", "ec_limit"):
                        st.session_state.pop(k, None)
                    st.session_state.data = data
                    save_user_data(st.session_state.user, data)
                    st.rerun()
                else:
                    new_key = new_name.strip().lower()
                    if new_key != to_edit and new_key in data["diet_categories"]:
                        st.error(tr("category_exists"))
                    else:
                        if new_key != to_edit:
                            data["diet_categories"][new_key] = data["diet_categories"].pop(to_edit)
                            for iso, entries in data["days"].items():
                                for e in entries:
                                    if to_edit in e.get("extras", {}):
                                        e["extras"][new_key] = e["extras"].pop(to_edit)
                        edited = data["diet_categories"][new_key]
                        edited["name"] = new_name.strip()
                        edited["unit"] = new_unit.strip() or "g"
                        edited["limit"] = int(new_limit)
                        for k in ("ec_name", "ec_unit", "ec_limit"):
                            st.session_state.pop(k, None)
                        st.session_state.data = data
                        save_user_data(st.session_state.user, data)
                        st.rerun()

        removable = [k for k in data["diet_categories"] if k != "calories"]
        if removable:
            to_rm = st.selectbox(tr("remove_category"), removable, key="rm_category")
            if st.button(tr("remove_category")):
                del data["diet_categories"][to_rm]
                for iso, entries in data["days"].items():
                    for e in entries:
                        e.get("extras", {}).pop(to_rm, None)
                st.session_state.data = data
                save_user_data(st.session_state.user, data)
                st.rerun()


# ---------------------------------------------------------------- budget

def spending_form(data, day):
    """Add a new spending entry, or edit the one chosen via its row's Edit button."""
    iso = day.isoformat()
    entries = data["spends"].get(iso, [])
    cat_labels = [budget_cat_display(c) for c in CATEGORIES]

    def clear_keys():
        for k in [f"sp_{iso}_name", f"sp_{iso}_cat", f"sp_{iso}_price"]:
            st.session_state.pop(k, None)

    editing = st.session_state.get(f"spend_edit_{iso}")
    is_edit = editing is not None and 0 <= editing < len(entries)
    entry = entries[editing] if is_edit else None

    if is_edit:
        st.markdown(f"**{tr('edit')}: {entry['name']}**")
    with st.form(key=f"spend_form_{iso}_{'e' if is_edit else 'n'}"):
        name = st.text_input(tr("spending_name"), value=entry["name"] if entry else "",
                             key=f"sp_{iso}_name")
        category = st.selectbox(
            tr("category"), cat_labels,
            index=CATEGORIES.index(entry["category"]) if entry and entry["category"] in CATEGORIES else 0,
            key=f"sp_{iso}_cat",
        )
        price = st.number_input(tr("price"), min_value=0.0,
                                value=float(entry["price"]) if entry else 0.0,
                                step=1.0, key=f"sp_{iso}_price")
        if st.form_submit_button(tr("save") if is_edit else tr("add")):
            if not name.strip():
                st.error(tr("name_empty"))
            else:
                new_entry = {
                    "name": name.strip(),
                    "category": CATEGORIES[cat_labels.index(category)],
                    "price": float(price),
                }
                if is_edit:
                    entries[editing] = new_entry
                else:
                    data["spends"].setdefault(iso, []).append(new_entry)
                st.session_state.pop(f"spend_edit_{iso}", None)
                if is_edit:
                    st.session_state[f"budget_view_{iso}"] = "list"
                clear_keys()
                st.session_state.data = data
                save_user_data(st.session_state.user, data)
                st.rerun()
    if is_edit:
        if st.button(tr("cancel"), key=f"spend_edit_cancel_{iso}"):
            clear_keys()
            st.session_state.pop(f"spend_edit_{iso}", None)
            st.session_state[f"budget_view_{iso}"] = "list"
            st.rerun()


def spending_table(data, day, editable=True):
    entries = data["spends"].get(day.isoformat(), [])
    if not entries:
        st.info(tr("no_spending"))
        return
    if not editable:
        rows = [
            {"#": i, tr("spending"): e["name"], tr("category"): budget_cat_display(e["category"]),
             tr("price_col"): f"{e['price']:g} HKD"} for i, e in enumerate(entries, start=1)
        ]
        st.table(rows)
        return

    iso = day.isoformat()
    for i, e in enumerate(entries):
        c1, c2, c3 = st.columns([8, 1, 1])
        with c1:
            st.markdown(f"**{e['name']}** · {budget_cat_display(e['category'])} · {e['price']:g} HKD")
        with c2:
            if st.button(tr("edit"), key=f"spend_edit_btn_{iso}_{i}"):
                for k in [f"sp_{iso}_name", f"sp_{iso}_cat", f"sp_{iso}_price"]:
                    st.session_state.pop(k, None)
                st.session_state[f"spend_edit_{iso}"] = i
                st.session_state[f"budget_view_{iso}"] = "add"
                st.rerun()
        with c3:
            if st.button(tr("remove"), key=f"spend_rm_btn_{iso}_{i}"):
                st.session_state[f"spend_rm_{iso}"] = i
                st.rerun()

    rm_i = st.session_state.get(f"spend_rm_{iso}")
    if rm_i is not None and 0 <= rm_i < len(entries):
        st.warning(f"{tr('delete_warning')} **{entries[rm_i]['name']}**")
        c1, c2 = st.columns(2)
        with c1:
            if st.button(tr("cancel"), key=f"spend_rm_no_{iso}"):
                st.session_state.pop(f"spend_rm_{iso}", None)
                st.rerun()
        with c2:
            if st.button(tr("confirm"), key=f"spend_rm_yes_{iso}"):
                entries.pop(rm_i)
                if not entries:
                    del data["spends"][iso]
                st.session_state.pop(f"spend_rm_{iso}", None)
                st.session_state.pop(f"spend_edit_{iso}", None)
                st.session_state.data = data
                save_user_data(st.session_state.user, data)
                st.rerun()


# ------------------------------------------------------------- combined

def storage_prompt(data):
    """Shown when storage is full and the selected day is brand new: the user
    must delete old day(s) before adding data to a new day."""
    used = stored_day_count(data)
    st.warning(tr("day_limit_reached").format(max=MAX_DAYS))
    st.caption(tr("streak_preserved_note"))
    c1, c2 = st.columns([1, 2])
    with c1:
        n = st.number_input(tr("days_to_delete"), min_value=1, max_value=used,
                            value=1, key="st_del_n")
    with c2:
        if st.button(tr("delete_oldest_day"), key="st_del_btn"):
            st.session_state["st_del_conf"] = True
            st.rerun()
    if st.session_state.get("st_del_conf"):
        st.warning(tr("delete_oldest_confirm"))
        d1, d2 = st.columns(2)
        with d1:
            if st.button(tr("confirm"), key="st_del_yes"):
                drop_n_oldest(data, int(n))
                st.session_state.pop("st_del_conf", None)
                st.session_state.data = data
                save_user_data(st.session_state.user, data)
                st.rerun()
        with d2:
            if st.button(tr("cancel"), key="st_del_no"):
                st.session_state.pop("st_del_conf", None)
                st.rerun()


def render_diet_section(data, selected):
    st.markdown(f"#### {tr('diet')}")
    with st.expander(tr("category_limits")):
        categories_manager(data)

    iso = selected.isoformat()
    view = st.session_state.setdefault(f"diet_view_{iso}", "list")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("➕ " + tr("add_item"), key=f"diet_go_add_{iso}",
                     type="primary" if view == "add" else "secondary"):
            st.session_state[f"diet_view_{iso}"] = "add"
            st.rerun()
    with c2:
        if st.button("📝 " + tr("display_edit"), key=f"diet_go_list_{iso}",
                     type="primary" if view == "list" else "secondary"):
            st.session_state[f"diet_view_{iso}"] = "list"
            st.rerun()

    if view == "add":
        if storage_blocker(data, selected):
            storage_prompt(data)
        else:
            food_form(data, selected)
    else:
        food_table(data, selected)

    day = build_day(data, selected)
    cats = diet_categories(data)
    st.markdown("##### " + tr("day_total"))
    over = False
    if day.entries:
        for key, cat in cats.items():
            total = day.sum_of(key, cat.unit)
            if total.amount > cat.limit:
                over = True
            flag = " 🔴 " + tr("over_limit") if total.amount > cat.limit else " ✅"
            st.write(f"{cat.name}: **{total.amount:g} {unit_display(total.unit)}**{flag}")
    else:
        st.write(tr("no_entries"))

    st.markdown("##### " + tr("streaks"))
    day_s, week_s, month_s = streaks_with_carry(data, selected)
    st.write(f"{tr('day')}: {day_s}  |  {tr('week')}: {week_s}  |  {tr('month')}: {month_s}")

    rank_key, score = diet_rank(day_s, week_s, month_s)
    st.markdown(f"##### 🏆 {tr(rank_key)}")
    st.write(tr("rank_label").format(tr(rank_key), score))


def render_budget_section(data, selected):
    st.markdown(f"#### {tr('budget')}")
    with st.expander(tr("settings")):
        period_labels = [tr(p) for p in PERIODS]
        period = st.selectbox(tr("period"), period_labels,
                              index=PERIODS.index(data["budget_period"]), key="b_period")
        limit = st.number_input(tr("limit_hkd"), min_value=0, step=100,
                                value=int(data["budget_limit"]), key="b_limit")
        if st.button(tr("save_settings")):
            data["budget_period"] = PERIODS[period_labels.index(period)]
            data["budget_limit"] = int(limit)
            st.session_state.data = data
            save_user_data(st.session_state.user, data)
            st.rerun()

    iso = selected.isoformat()
    view = st.session_state.setdefault(f"budget_view_{iso}", "list")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("➕ " + tr("add_item"), key=f"budget_go_add_{iso}",
                     type="primary" if view == "add" else "secondary"):
            st.session_state[f"budget_view_{iso}"] = "add"
            st.rerun()
    with c2:
        if st.button("📝 " + tr("display_edit"), key=f"budget_go_list_{iso}",
                     type="primary" if view == "list" else "secondary"):
            st.session_state[f"budget_view_{iso}"] = "list"
            st.rerun()

    if view == "add":
        if storage_blocker(data, selected):
            storage_prompt(data)
        else:
            spending_form(data, selected)
    else:
        spending_table(data, selected)

    spends = spends_objects(data)
    period = data["budget_period"]
    limit = data["budget_limit"]
    expenses = period_expenses(spends, period, selected)
    total = sum(int(e.price.amount) for e in expenses)
    st.metric(f"{tr(period)} {tr('total')}", f"{total} HKD", f"{tr('limit_hkd')}: {limit}")
    st.write(tr("over_limit") if total > limit else tr("within_limit"))

    st.markdown("##### " + tr("streaks"))
    streaks = budget_streaks_with_carry(data, selected)
    labels = {"day": tr("day"), "week": tr("week"), "month": tr("month")}
    st.write("  |  ".join(f"{labels[k]}: {v}" for k, v in streaks.items()))


def diet_limits_table(data):
    """The member's diet category limits, as a table."""
    cats = diet_categories(data)
    rows = [{
        "#": i, tr("category_name"): cat.name,
        tr("daily_limit"): f"{cat.limit:g} {unit_display(cat.unit)}",
    } for i, cat in enumerate(cats.values(), start=1)]
    st.table(rows)


def member_diet_view(data, day):
    """The member's diet records for one day: totals, limits and item table."""
    day_obj = build_day(data, day)
    cats = diet_categories(data)
    parts = []
    for key, cat in cats.items():
        total = day_obj.sum_of(key, cat.unit)
        mark = " 🔴" if total.amount > cat.limit else " ✅"
        parts.append(f"{cat.name}: **{total.amount:g} {unit_display(total.unit)}**{mark}")
    if day_obj.entries:
        st.write(tr("day_total") + "  |  " + "  |  ".join(parts))
    else:
        st.write(tr("no_entries"))
    st.caption(tr("diet_limits"))
    diet_limits_table(data)
    food_table(data, day, False)


def member_budget_view(data, day):
    """The member's budget records for one day: total, limit and item table."""
    spends = spends_objects(data)
    period = data["budget_period"]
    limit = data["budget_limit"]
    total = sum(int(e.price.amount) for e in period_expenses(spends, period, day))
    flag = tr("over_limit") if total > limit else tr("within_limit")
    st.write(
        f"{tr('limit_hkd')}: **{limit:g} HKD** ({tr(period)})  |  "
        f"{tr(period)} {tr('total')}: **{total} HKD** {flag}"
    )
    spending_table(data, day, False)


def show_records(data, day, share="both"):
    """Read-only records of one user for a chosen day, honouring the sharing
    permission they chose for the group owner. Diet and budget are shown as
    tables, exactly the same presenter the owner's own view uses."""
    st.markdown(f"**🥗 {tr('diet')}**")
    if granted_share(share, "diet"):
        member_diet_view(data, day)
    else:
        st.info(tr("permission_not_granted"))

    st.markdown(f"**💰 {tr('budget')}**")
    if granted_share(share, "budget"):
        member_budget_view(data, day)
    else:
        st.info(tr("permission_not_granted"))


def share_display(share):
    return {
        "diet": tr("shares_diet"),
        "budget": tr("shares_budget"),
        "both": tr("shares_both"),
    }.get(_valid_share(share), tr("shares_none"))


def view_member_records(gid):
    """Group owners: read-only records of a chosen member, gated by the share
    permission that member chose when joining the group."""
    members = group_members(gid)
    usernames = [m["username"] for m in members]
    if not usernames:
        st.info(tr("no_members_yet"))
        return
    target = st.selectbox(tr("user"), usernames, key=f"grp_rec_sel_{gid}")
    data = load_user_data(target)
    share = member_share(gid, target)
    st.caption(f"🔒 {share_display(share)}")
    selected = calendar_widget(
        f"grp_{gid}_{target}", lambda d: (diet_status(data, d), budget_status(data, d))
    )
    st.subheader(f"{target} · {format_date(selected)}")
    show_records(data, selected, share)


def groups_section():
    """Create/join groups, view the group leaderboard, and manage owned groups."""
    st.markdown(f"### 🏆 {tr('groups')}")
    groups = my_groups(st.session_state.user)
    options = {
        "➕ " + tr("add_group"): ("form", "add"),
        "➕ " + tr("join_group"): ("form", "join"),
    }
    for g in groups:
        badge = tr("group_public") if g["is_public"] else tr("group_private")
        options[f"[{badge}] {g['name']} ({g['member_count']} {tr('members')})"] = ("group", g)
    labels = list(options)
    default = 2 if groups else 0
    choice = st.selectbox(tr("groups"), labels, index=default, key="grp_dd")
    kind, payload = options[choice]

    if kind == "form":
        if payload == "add":
            type_labels = [tr("group_private"), tr("group_public")]
            grp_public = st.radio(
                tr("group_type"), type_labels, index=0, horizontal=True, key="grp_type",
            ) == tr("group_public")
            with st.form("grp_create"):
                g_name = st.text_input(tr("group_name"), key="grp_name")
                if not grp_public:
                    g_code = st.text_input(tr("access_code"), type="password", key="grp_code")
                else:
                    g_code = ""
                    st.caption(tr("public_no_code"))
                if st.form_submit_button(tr("create_group")):
                    ok, key = create_group(
                        g_name.strip(), (g_code or "").strip(), st.session_state.user,
                        is_public=grp_public,
                    )
                    if ok:
                        for k in ("grp_name", "grp_code"):
                            st.session_state.pop(k, None)
                        st.success(tr(key))
                        st.rerun()
                    else:
                        st.error(tr(key))
        else:
            with st.form("grp_join"):
                jg_name = st.text_input(tr("group_name"), key="jg_name")
                jg_code = st.text_input(tr("access_code"), type="password", key="jg_code")
                st.caption(tr("join_hint"))
                share_labels = [tr("diet"), tr("budget"), tr("share_both")]
                share_choice = st.radio(
                    tr("share_with_owner"), share_labels, index=2, key="jg_share",
                    horizontal=True,
                )
                st.caption(tr("sharing_info"))
                if st.form_submit_button(tr("join_group")):
                    share = SHARE_OPTIONS[share_labels.index(share_choice)]
                    ok, key = join_group(
                        jg_name.strip(), jg_code.strip(), st.session_state.user, share
                    )
                    if ok:
                        for k in ("jg_name", "jg_code"):
                            st.session_state.pop(k, None)
                        st.session_state.pop("jg_share", None)
                        st.success(tr(key))
                        st.rerun()
                    else:
                        st.error(tr(key))
        return

    group = payload
    me = st.session_state.user
    owner_names = [m["username"] for m in group["members"] if m["is_owner"]]
    st.caption(f"{tr('owner')}: {', '.join(owner_names) or '—'}")
    rows = []
    for place, (user, d, w, m, score) in enumerate(
        rank_users([x["username"] for x in group["members"]]), start=1
    ):
        mark = " ★" if user == me else ""
        rank_key, _ = diet_rank(d, w, m)
        rows.append({
            tr("rank_title"): place,
            tr("user"): user + mark,
            tr("day"): d,
            tr("week"): w,
            tr("month"): m,
            tr("score"): score,
            tr("tier"): tr(rank_key),
        })
    with st.container(height=400):
        if rows:
            st.table(rows)
        else:
            st.info(tr("no_members_yet"))

    st.divider()
    st.markdown(f"##### 🔒 {tr('sharing')}")
    st.caption(tr("sharing_info"))
    share_labels = [tr("diet"), tr("budget"), tr("share_both")]
    my_share = _valid_share(member_share(group["id"], me))
    chosen = st.radio(
        tr("share_with_owner"), share_labels,
        index=SHARE_OPTIONS.index(my_share), key=f"my_share_{group['id']}", horizontal=True,
    )
    if st.button(tr("update_sharing"), key=f"my_share_btn_{group['id']}"):
        set_member_share(group["id"], me, SHARE_OPTIONS[share_labels.index(chosen)])
        st.success(tr("sharing_updated"))
        st.rerun()

    if group["user_is_owner"]:
        st.divider()
        st.markdown(f"##### 👑 {tr('group_management')}")
        for m in group["members"]:
            badge = " 👑" if m["is_owner"] else ""
            if m["username"] == me:
                st.write(f"**{m['username']}**{badge} ★")
                continue
            c1, c2, c3 = st.columns([6, 1, 1])
            c1.write(f"**{m['username']}**{badge}")
            if m["is_owner"]:
                if c2.button(tr("demote"), key=f"g_demote_{group['id']}_{m['username']}"):
                    demote_owner(group["id"], m["username"], me)
                    st.success(tr("owner_demoted"))
                    st.rerun()
            else:
                if c2.button(tr("promote"), key=f"g_promote_{group['id']}_{m['username']}"):
                    promote_owner(group["id"], m["username"], me)
                    st.success(tr("owner_promoted"))
                    st.rerun()
            if c3.button(tr("kick"), key=f"g_kick_{group['id']}_{m['username']}"):
                st.session_state[f"g_kick_conf_{group['id']}_{m['username']}"] = True
                st.rerun()
            if st.session_state.get(f"g_kick_conf_{group['id']}_{m['username']}"):
                st.warning(tr("kick_confirm").format(name=m["username"]))
                k1, k2 = st.columns(2)
                with k1:
                    if st.button(tr("confirm"), key=f"g_kick_yes_{group['id']}_{m['username']}"):
                        kick_member(group["id"], m["username"], me)
                        st.session_state.pop(f"g_kick_conf_{group['id']}_{m['username']}", None)
                        st.success(tr("member_kicked"))
                        st.rerun()
                with k2:
                    if st.button(tr("cancel"), key=f"g_kick_no_{group['id']}_{m['username']}"):
                        st.session_state.pop(f"g_kick_conf_{group['id']}_{m['username']}", None)
                        st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            with st.form(f"g_name_{group['id']}"):
                new_name = st.text_input(tr("group_name"), value=group["name"],
                                         key=f"gn_{group['id']}")
                if st.form_submit_button(tr("change_name")):
                    ok, key = rename_group(group["id"], new_name.strip(), me)
                    if ok:
                        st.success(tr(key))
                        st.rerun()
                    else:
                        st.error(tr(key))
        with c2:
            if group["is_public"]:
                st.caption(tr("public_no_code"))
            else:
                with st.form(f"g_code_{group['id']}"):
                    new_code = st.text_input(tr("access_code"), value=group["access_code"],
                                             key=f"gc_{group['id']}")
                    if st.form_submit_button(tr("change_code")):
                        ok, key = change_access_code(group["id"], new_code.strip(), me)
                        if ok:
                            st.success(tr(key))
                            st.rerun()
                        else:
                            st.error(tr(key))

        if st.button(tr("remove_group"), key=f"g_del_btn_{group['id']}"):
            st.session_state[f"g_del_conf_{group['id']}"] = True
            st.rerun()
        if st.session_state.get(f"g_del_conf_{group['id']}"):
            st.warning(tr("delete_warning"))
            d1, d2 = st.columns(2)
            with d1:
                if st.button(tr("confirm"), key=f"g_del_yes_{group['id']}"):
                    delete_group(group["id"], me)
                    st.session_state.pop(f"g_del_conf_{group['id']}", None)
                    st.session_state.pop("grp_dd", None)
                    st.success(tr("group_removed"))
                    st.rerun()
            with d2:
                if st.button(tr("cancel"), key=f"g_del_no_{group['id']}"):
                    st.session_state.pop(f"g_del_conf_{group['id']}", None)
                    st.rerun()

        st.divider()
        st.markdown(f"##### {tr('view_member_records')}")
        view_member_records(group["id"])
    else:
        st.divider()
        if st.session_state.get(f"g_leave_conf_{group['id']}"):
            st.warning(tr("leave_confirm"))
            c1, c2 = st.columns(2)
            with c1:
                if st.button(tr("confirm"), key=f"g_leave_yes_{group['id']}"):
                    leave_group(group["id"], me)
                    st.session_state.pop(f"g_leave_conf_{group['id']}", None)
                    st.session_state.pop("grp_dd", None)
                    st.success(tr("group_left"))
                    st.rerun()
            with c2:
                if st.button(tr("cancel"), key=f"g_leave_no_{group['id']}"):
                    st.session_state.pop(f"g_leave_conf_{group['id']}", None)
                    st.rerun()
        else:
            if st.button(tr("leave_group"), key=f"g_leave_{group['id']}"):
                st.session_state[f"g_leave_conf_{group['id']}"] = True
                st.rerun()


def admin_panel():
    """Account management only — no access to any diet/budget data."""
    users = all_usernames()
    query = st.text_input(tr("search_users"), key="adm_search").strip().lower()
    matches = [u for u in users if query in u.lower()] if query else users
    if not matches:
        st.info(tr("no_users_match"))
        return
    st.selectbox(tr("select_user"), matches, key="adm_target")
    target = st.session_state.get("adm_target")

    col_r, col_a, col_d = st.columns(3)
    with col_r:
        with st.form("adm_reset"):
            a_new = st.text_input(tr("new_password"), type="password", key="adm_new")
            a_conf = st.text_input(tr("confirm_password"), type="password", key="adm_conf")
            if st.form_submit_button(tr("reset_pw")):
                if a_new != a_conf:
                    st.error(tr("password_mismatch"))
                else:
                    ok, msg = reset_password(target, a_new)
                    if ok:
                        for k in ("adm_new", "adm_conf"):
                            st.session_state.pop(k, None)
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
    with col_a:
        with st.form("adm_add"):
            a_user = st.text_input(tr("username"), key="adm_add_user")
            a_pw = st.text_input(tr("password"), type="password", key="adm_add_pw")
            if st.form_submit_button(tr("add_account")):
                ok, msg = signup(a_user.strip(), a_pw)
                if ok:
                    save_user_data(a_user.strip(), default_data())
                    for k in ("adm_add_user", "adm_add_pw"):
                        st.session_state.pop(k, None)
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    with col_d:
        if target and target != ADMIN_USER:
            if st.button(tr("delete_account"), key="adm_del"):
                with get_db() as conn:
                    conn.execute("DELETE FROM users WHERE username = ?", (target,))
                    conn.execute("DELETE FROM user_data WHERE username = ?", (target,))
                st.success(tr("account_deleted"))
                st.rerun()
        else:
            st.caption(tr("admin"))

    st.divider()
    with st.form("adm_rename"):
        ren_old = st.text_input(tr("username"), key="ren_old")
        ren_new = st.text_input(tr("new_username"), key="ren_new")
        if st.form_submit_button(tr("rename_user")):
            ok, key = rename_user(ren_old.strip(), ren_new.strip())
            if ok:
                for k in ("ren_old", "ren_new"):
                    st.session_state.pop(k, None)
                st.success(tr(key))
                st.rerun()
            else:
                st.error(tr(key))


def admin_groups():
    """Admin view of public groups only: create, rename, remove, kick members.
    Private (user-created) groups are never shown or managed by the admin."""
    st.markdown(f"### 🏆 {tr('groups')}")
    with st.form("adm_grp_create"):
        ag_name = st.text_input(tr("group_name"), key="ag_name")
        st.caption(tr("admin_group_public"))
        if st.form_submit_button(tr("create_group")):
            ok, key = create_group(ag_name.strip(), "", None, is_public=True)
            if ok:
                st.session_state.pop("ag_name", None)
                st.success(tr(key))
                st.rerun()
            else:
                st.error(tr(key))
    st.divider()

    groups = [g for g in all_groups() if g["is_public"]]
    if not groups:
        st.info(tr("no_public_groups"))
        return
    st.caption(tr("all_groups"))
    with st.container(height=460):
        for g in groups:
            member_txt = ", ".join(m["username"] for m in g["members"]) or "—"
            st.write(
                f"**{g['name']}** (id {g['id']}) · {tr('public_group')} · "
                f"{tr('owner')}: {g['owner']} · {tr('members')}: {member_txt}"
            )
            c1, c2 = st.columns(2)
            with c1:
                with st.form(f"adm_grp_name_{g['id']}"):
                    new_name = st.text_input(tr("group_name"), value=g["name"],
                                             key=f"agn_{g['id']}")
                    if st.form_submit_button(tr("change_name")):
                        ok, key = rename_group(g["id"], new_name.strip(), ADMIN_USER)
                        if ok:
                            st.success(tr(key))
                            st.rerun()
                        else:
                            st.error(tr(key))
            with c2:
                if st.session_state.get(f"adm_gdel_{g['id']}"):
                    st.warning(tr("delete_warning"))
                    rc1, rc2 = st.columns(2)
                    with rc1:
                        if st.button(tr("confirm"), key=f"adm_gdel_yes_{g['id']}"):
                            delete_group(g["id"], ADMIN_USER)
                            st.session_state.pop(f"adm_gdel_{g['id']}", None)
                            st.success(tr("group_removed"))
                            st.rerun()
                    with rc2:
                        if st.button(tr("cancel"), key=f"adm_gdel_no_{g['id']}"):
                            st.session_state.pop(f"adm_gdel_{g['id']}", None)
                            st.rerun()
                else:
                    if st.button(tr("remove_group"), key=f"adm_gdel_btn_{g['id']}"):
                        st.session_state[f"adm_gdel_{g['id']}"] = True
                        st.rerun()
            if g["members"]:
                kick_sel = st.selectbox(
                    tr("kick_member"), [m["username"] for m in g["members"]],
                    key=f"adm_gkick_sel_{g['id']}",
                )
                if st.button(tr("kick"), key=f"adm_gkick_btn_{g['id']}"):
                    st.session_state[f"adm_gkick_conf_{g['id']}"] = kick_sel
                    st.rerun()
                target = st.session_state.get(f"adm_gkick_conf_{g['id']}")
                if target:
                    st.warning(tr("kick_confirm").format(name=target))
                    k1, k2 = st.columns(2)
                    with k1:
                        if st.button(tr("confirm"), key=f"adm_gkick_yes_{g['id']}"):
                            kick_member(g["id"], target, ADMIN_USER)
                            st.session_state.pop(f"adm_gkick_conf_{g['id']}", None)
                            st.session_state.pop(f"adm_gkick_sel_{g['id']}", None)
                            st.success(tr("member_kicked"))
                            st.rerun()
                    with k2:
                        if st.button(tr("cancel"), key=f"adm_gkick_no_{g['id']}"):
                            st.session_state.pop(f"adm_gkick_conf_{g['id']}", None)
                            st.rerun()
            st.divider()


def render_admin_view():
    with st.expander("🛡️ " + tr("admin_panel"), expanded=True):
        admin_panel()
    with st.expander("🏆 " + tr("groups")):
        admin_groups()


def render_app(data):
    if st.session_state.user == ADMIN_USER:
        render_admin_view()
        return
    groups_section()
    st.caption(tr("storage_usage").format(
        used=stored_day_count(data), max=MAX_DAYS))
    selected = calendar_widget(
        "global", lambda d: (diet_status(data, d), budget_status(data, d))
    )
    st.subheader(format_date(selected))
    st.markdown(
        f"🟢 {tr('within_limit')}　🔴 {tr('over_limit')}　· {tr('no_entries')}　"
        f"| {tr('diet_budget_legend')}"
    )

    tab_diet, tab_budget = st.tabs([tr("diet"), tr("budget")])
    with tab_diet:
        render_diet_section(data, selected)
    with tab_budget:
        render_budget_section(data, selected)


# ------------------------------------------------------------------ auth

def auth_screen():
    st.title(tr("app_title"))
    st.caption(tr("auth_caption"))
    tab_in, tab_up = st.tabs([tr("sign_in"), tr("sign_up")])
    with tab_in:
        with st.form("signin_form"):
            username = st.text_input(tr("username"), key="si_user")
            password = st.text_input(tr("password"), type="password", key="si_pass")
            if st.form_submit_button(tr("sign_in")):
                ok, msg = signin(username.strip(), password)
                if ok:
                    st.session_state.user = username.strip()
                    st.session_state.data = load_user_data(username.strip())
                    st.rerun()
                st.error(msg)
    with tab_up:
        with st.form("signup_form"):
            username = st.text_input(tr("username"), key="su_user")
            password = st.text_input(tr("password"), type="password", key="su_pass")
            if st.form_submit_button(tr("sign_up")):
                ok, msg = signup(username.strip(), password)
                if ok:
                    st.session_state.user = username.strip()
                    st.session_state.data = default_data()
                    save_user_data(username.strip(), st.session_state.data)
                    st.success(msg)
                    st.rerun()
                st.error(msg)


def inject_mobile_css():
    st.markdown(
        """
        <style>
        @media (max-width: 720px) {
            .block-container {
                padding-top: 2rem;
                padding-left: 0.6rem;
                padding-right: 0.6rem;
            }
            [data-testid="stTable"] {
                display: block;
                overflow-x: auto;
            }
            .stButton > button,
            .stFormSubmitButton > button {
                width: 100%;
                min-height: 2.5rem;
            }
            [data-testid="stMetric"] {
                padding: 0.5rem;
            }
        }
        .main .block-container {
            max-width: 64rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main():
    st.set_page_config(page_title=STRINGS["en"]["app_title"], layout="wide")
    init_db()
    ensure_admin()
    inject_mobile_css()

    st.session_state.setdefault("lang", "en")
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("data", default_data())

    if st.session_state.user is None:
        with st.sidebar:
            lang = st.selectbox(tr("language"), ["English", "中文"], key="lang_select")
            st.session_state.lang = "zh" if lang == "中文" else "en"
        auth_screen()
        return

    with st.sidebar:
        lang = st.selectbox(tr("language"), ["English", "中文"], key="lang_select")
        st.session_state.lang = "zh" if lang == "中文" else "en"
        st.write(f"{tr('signed_in_as')} **{st.session_state.user}**")
        if st.button(tr("sign_out")):
            st.session_state.user = None
            st.session_state.data = default_data()
            st.rerun()

        with st.expander(tr("delete_account")):
            if st.session_state.user == ADMIN_USER:
                st.caption(tr("admin"))
            else:
                conf = st.text_input(tr("confirm_username"))
                del_pw = st.text_input(tr("password"), type="password", key="del_pw")
                if st.button(tr("delete_account"), key="del_btn"):
                    if conf.strip() != st.session_state.user:
                        st.error(tr("username_mismatch"))
                    else:
                        ok, msg = delete_account(st.session_state.user, del_pw)
                        if ok:
                            st.success(msg)
                            st.session_state.user = None
                            st.session_state.data = default_data()
                            st.rerun()
                        else:
                            st.error(msg)

    st.title(tr("app_title"))
    render_app(st.session_state.data)


if __name__ == "__main__":
    main()
