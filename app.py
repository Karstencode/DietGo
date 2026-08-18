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
    period_expenses, diet_rank, diet_score, STRINGS, MEALS, CATEGORIES, PERIODS, UNITS, LANGS,
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "streamlit_data.db")

ADMIN_USER = "admin"


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
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, access_code TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memberships "
            "(leaderboard_id INTEGER NOT NULL, username TEXT NOT NULL, "
            "PRIMARY KEY (leaderboard_id, username))"
        )


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


# ---------------------------------------------------------- leaderboards

def create_leaderboard(name, code, username=None):
    """Create a leaderboard. `username` (optional) becomes its first member."""
    if not name or not code:
        return False, "name_empty"
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM leaderboards WHERE name = ?", (name,)).fetchone():
            return False, "leaderboard_exists"
        cur = conn.execute(
            "INSERT INTO leaderboards (name, access_code) VALUES (?, ?)", (name, code)
        )
        if username:
            conn.execute(
                "INSERT INTO memberships (leaderboard_id, username) VALUES (?, ?)",
                (cur.lastrowid, username),
            )
    return True, "leaderboard_created"


def join_leaderboard(name, code, username):
    """Join an existing leaderboard by name + access code."""
    if not name or not code:
        return False, "wrong_access_code"
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM leaderboards WHERE name = ? AND access_code = ?", (name, code)
        ).fetchone()
        if not row:
            return False, "wrong_access_code"
        lid = row[0]
        if conn.execute(
            "SELECT 1 FROM memberships WHERE leaderboard_id = ? AND username = ?",
            (lid, username),
        ).fetchone():
            return False, "already_member"
        conn.execute(
            "INSERT INTO memberships (leaderboard_id, username) VALUES (?, ?)", (lid, username)
        )
    return True, "leaderboard_joined"


def leaderboard_members(lid):
    with get_db() as conn:
        return [r[0] for r in conn.execute(
            "SELECT username FROM memberships WHERE leaderboard_id = ? ORDER BY username", (lid,)
        ).fetchall()]


def delete_leaderboard(lid):
    """Delete a leaderboard and all its memberships, renumbering the rest so ids stay 1..N."""
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
    return True, "leaderboard_removed"


def my_leaderboards(username):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT l.id, l.name, l.access_code FROM leaderboards l "
            "JOIN memberships m ON m.leaderboard_id = l.id "
            "WHERE m.username = ? ORDER BY l.name",
            (username,),
        ).fetchall()
    boards = []
    for lid, name, code in rows:
        members = leaderboard_members(lid)
        boards.append({"id": lid, "name": name, "access_code": code,
                       "members": members, "member_count": len(members)})
    return boards


def all_leaderboards():
    with get_db() as conn:
        rows = conn.execute("SELECT id, name, access_code FROM leaderboards ORDER BY name").fetchall()
    boards = []
    for lid, name, code in rows:
        members = leaderboard_members(lid)
        boards.append({"id": lid, "name": name, "access_code": code,
                       "members": members, "member_count": len(members)})
    return boards


def rename_leaderboard(lid, new_name):
    if not new_name:
        return False, "name_empty"
    with get_db() as conn:
        conn.execute("UPDATE leaderboards SET name = ? WHERE id = ?", (new_name, lid))
    return True, "leaderboard_created"


def change_access_code(lid, new_code):
    if not new_code:
        return False, "name_empty"
    with get_db() as conn:
        conn.execute("UPDATE leaderboards SET access_code = ? WHERE id = ?", (new_code, lid))
    return True, "leaderboard_created"


def rename_user(old, new):
    """Rename an account, moving its data and leaderboard memberships."""
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
    return True, "username_changed"


def rank_users(usernames):
    """Rank members by combined diet score as of today."""
    board = []
    today = date.today()
    for user in usernames:
        data = load_user_data(user)
        day_s, week_s, month_s = compute_streaks(
            build_all_days(data), diet_categories(data), today
        )
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
            return data
    return default_data()


def save_user_data(username, data):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO user_data (username, json) VALUES (?, ?) "
            "ON CONFLICT(username) DO UPDATE SET json = excluded.json",
            (username, json.dumps(data)),
        )


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
        rows = [
            {"#": i, tr("food"): e["name"], tr("meal"): tr(e["meal"]),
             tr("amount"): f"{e['amount'][0]:g} {unit_display(e['amount'][1])}" if e.get("amount") else ""}
            for i, e in enumerate(entries, start=1)
        ]
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
    day_s, week_s, month_s = compute_streaks(build_all_days(data), cats, selected)
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
    streaks = compute_budget_streaks(spends, period, limit, selected)
    labels = {"day": tr("day"), "week": tr("week"), "month": tr("month")}
    st.write("  |  ".join(f"{labels[k]}: {v}" for k, v in streaks.items()))


def leaderboards_section():
    """Create/join leaderboards and show rankings of the boards you're in."""
    st.markdown(f"### 🏆 {tr('leaderboards')}")
    boards = my_leaderboards(st.session_state.user)
    options = {
        "➕ " + tr("add_leaderboard"): ("form", "add"),
        "➕ " + tr("join_leaderboard"): ("form", "join"),
    }
    for b in boards:
        options[f"{b['name']} ({b['member_count']} {tr('members')})"] = ("board", b)
    labels = list(options)
    default = 2 if boards else 0
    choice = st.selectbox(tr("leaderboards"), labels, index=default, key="lb_dd")
    kind, payload = options[choice]

    if kind == "form":
        if payload == "add":
            with st.form("lb_create"):
                lb_name = st.text_input(tr("leaderboard_name"), key="lb_name")
                lb_code = st.text_input(tr("access_code"), type="password", key="lb_code")
                if st.form_submit_button(tr("create_leaderboard")):
                    ok, key = create_leaderboard(lb_name.strip(), lb_code.strip(), st.session_state.user)
                    if ok:
                        for k in ("lb_name", "lb_code"):
                            st.session_state.pop(k, None)
                        st.success(tr(key))
                        st.rerun()
                    else:
                        st.error(tr(key))
        else:
            with st.form("lb_join"):
                jb_name = st.text_input(tr("leaderboard_name"), key="jb_name")
                jb_code = st.text_input(tr("access_code"), type="password", key="jb_code")
                if st.form_submit_button(tr("join_leaderboard")):
                    ok, key = join_leaderboard(jb_name.strip(), jb_code.strip(), st.session_state.user)
                    if ok:
                        for k in ("jb_name", "jb_code"):
                            st.session_state.pop(k, None)
                        st.success(tr(key))
                        st.rerun()
                    else:
                        st.error(tr(key))
        return

    board = payload
    rows = []
    for place, (user, d, w, m, score) in enumerate(rank_users(board["members"]), start=1):
        mark = " ★" if user == st.session_state.user else ""
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
    st.caption(f"{tr('members')}: {', '.join(board['members']) or '—'}")
    with st.container(height=460):
        if rows:
            st.table(rows)
        else:
            st.info(tr("no_members_yet"))


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


def admin_leaderboards():
    """Admin view of every leaderboard: create, rename, change its access code, or remove it."""
    st.markdown(f"### 🏆 {tr('leaderboards')}")
    with st.form("adm_lb_create"):
        c1, c2 = st.columns(2)
        with c1:
            alb_name = st.text_input(tr("leaderboard_name"), key="alb_name")
        with c2:
            alb_code = st.text_input(tr("access_code"), type="password", key="alb_code")
        if st.form_submit_button(tr("create_leaderboard")):
            ok, key = create_leaderboard(alb_name.strip(), alb_code.strip(), None)
            if ok:
                for k in ("alb_name", "alb_code"):
                    st.session_state.pop(k, None)
                st.success(tr(key))
                st.rerun()
            else:
                st.error(tr(key))
    st.divider()

    boards = all_leaderboards()
    if not boards:
        st.info(tr("no_leaderboards"))
        return
    st.caption(tr("all_leaderboards"))
    with st.container(height=460):
        for b in boards:
            st.write(
                f"**{b['name']}** (id {b['id']}) · {tr('access_code')}: `{b['access_code']}` · "
                f"{tr('members')}: {', '.join(b['members']) or '—'}"
            )
            c1, c2, c3 = st.columns(3)
            with c1:
                with st.form(f"adm_lb_name_{b['id']}"):
                    new_name = st.text_input(tr("leaderboard_name"), value=b["name"],
                                             key=f"lbn_{b['id']}")
                    if st.form_submit_button(tr("change_name")):
                        rename_leaderboard(b["id"], new_name.strip())
                        st.rerun()
            with c2:
                with st.form(f"adm_lb_code_{b['id']}"):
                    new_code = st.text_input(tr("access_code"), value=b["access_code"],
                                             key=f"lbc_{b['id']}")
                    if st.form_submit_button(tr("change_code")):
                        change_access_code(b["id"], new_code.strip())
                        st.rerun()
            with c3:
                if st.session_state.get(f"adm_lb_del_{b['id']}"):
                    st.warning(tr("delete_warning"))
                    rc1, rc2 = st.columns(2)
                    with rc1:
                        if st.button(tr("confirm"), key=f"adm_lb_del_yes_{b['id']}"):
                            delete_leaderboard(b["id"])
                            st.session_state.pop(f"adm_lb_del_{b['id']}", None)
                            st.success(tr("leaderboard_removed"))
                            st.rerun()
                    with rc2:
                        if st.button(tr("cancel"), key=f"adm_lb_del_no_{b['id']}"):
                            st.session_state.pop(f"adm_lb_del_{b['id']}", None)
                            st.rerun()
                else:
                    if st.button(tr("remove_leaderboard"), key=f"adm_lb_del_btn_{b['id']}"):
                        st.session_state[f"adm_lb_del_{b['id']}"] = True
                        st.rerun()


def admin_show_date(data, day):
    """Read-only view of one user's diet/budget records for a chosen day."""
    day_obj = build_day(data, day)
    cats = diet_categories(data)
    st.markdown(f"**{tr('diet')}**")
    if day_obj.entries:
        parts = []
        for key, cat in cats.items():
            total = day_obj.sum_of(key, cat.unit)
            parts.append(f"{cat.name}: {total.amount:g} {unit_display(total.unit)}" + (" 🔴" if total.amount > cat.limit else " ✅"))
        st.write("  |  ".join(parts))
    else:
        st.write(tr("no_entries"))
    food_table(data, day, False)

    st.markdown(f"**{tr('budget')}**")
    spends = spends_objects(data)
    period = data["budget_period"]
    limit = data["budget_limit"]
    total = sum(int(e.price.amount) for e in period_expenses(spends, period, day))
    flag = tr("over_limit") if total > limit else tr("within_limit")
    st.write(f"{tr(period)} {tr('total')}: {total} HKD / {tr('limit_hkd')}: {limit} | {flag}")
    spending_table(data, day, False)


def render_admin_view():
    with st.expander("🛡️ " + tr("admin_panel"), expanded=True):
        admin_panel()
    with st.expander("🏆 " + tr("leaderboards")):
        admin_leaderboards()
    target = st.session_state.get("adm_target")
    query = (st.session_state.get("adm_search") or "").strip().lower()
    if not target or (query and query not in target.lower()):
        return
    data = load_user_data(target)
    cats = diet_categories(data)
    ctext = ", ".join(f"{c['name']} ({unit_display(c['unit'])}): {c['limit']}" for c in data["diet_categories"].values())
    st.write(f"{tr('category_limits')}: {ctext}")
    today = date.today()
    day_s, week_s, month_s = compute_streaks(build_all_days(data), cats, today)
    rank_key, score = diet_rank(day_s, week_s, month_s)
    st.write(
        f"{tr('streaks')}: {tr('day')} {day_s} | {tr('week')} {week_s} | "
        f"{tr('month')} {month_s} | 🏆 {tr(rank_key)} ({score})"
    )

    st.markdown(f"### {tr('view_records')} · {target}")
    selected = calendar_widget(
        "admin_" + target, lambda d: (diet_status(data, d), budget_status(data, d))
    )
    st.subheader(format_date(selected))
    admin_show_date(data, selected)
    st.divider()


def render_app(data):
    if st.session_state.user == ADMIN_USER:
        render_admin_view()
        return
    leaderboards_section()
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
