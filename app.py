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
    period_expenses, diet_rank, diet_score, STRINGS, MEALS, CATEGORIES, PERIODS, LANGS,
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "streamlit_data.db")


def tr(key):
    lang = st.session_state.get("lang", "en")
    table = STRINGS.get(lang, STRINGS["en"])
    return table.get(key, key)


def budget_cat_display(c):
    """Translated label for a stored (English) budget category."""
    key = "budget_cat_" + c.lower().replace(" ", "_")
    return tr(key) if tr(key) != key else c


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
    entries = data["days"].get(day.isoformat(), [])
    options = [tr("add_new")] + [f"{i + 1}: {e['name']}" for i, e in enumerate(entries)]
    choice = st.selectbox(tr("entry"), options, key=f"food_choice_{day.isoformat()}")
    editing = choice != tr("add_new")
    entry = entries[int(choice.split(":")[0]) - 1] if editing else None
    cats = diet_categories(data)
    meal_labels = [tr(m) for m in MEALS]

    with st.form(key=f"food_form_{day.isoformat()}_{'e' if editing else 'n'}"):
        name = st.text_input(tr("food_name"), value=entry["name"] if entry else "")
        meal = st.selectbox(tr("meal_type"), meal_labels,
                            index=MEALS.index(entry["meal"]) if entry else 0)
        calories = st.number_input(tr("calories"), min_value=0, step=10,
                                   value=int(entry["calories"]) if entry else 0)
        amount = st.number_input(tr("amount"), min_value=0.0,
                                 value=float(entry["amount"][0]) if entry and entry["amount"] else 0.0,
                                 step=0.5)
        unit = st.selectbox(tr("unit"), ("g", "portions"),
                            index=0 if not (entry and entry["amount"] and entry["amount"][1] == "portions") else 1)
        extras = {}
        for key, cat in cats.items():
            if key == "calories":
                continue
            cur = entry["extras"].get(key, [0, cat.unit])[0] if entry else 0
            extras[key] = st.number_input(f"{cat.name} ({cat.unit})", min_value=0.0,
                                          value=float(cur), step=0.5)
        submitted = st.form_submit_button(tr("save"))

    if submitted:
        if not name.strip():
            st.error(tr("name_empty"))
            return
        new_entry = {
            "name": name.strip(),
            "meal": MEALS[meal_labels.index(meal)],
            "calories": int(calories),
            "amount": [float(amount), unit] if amount > 0 else None,
            "extras": {k: [float(v), cats[k].unit] for k, v in extras.items() if v > 0},
        }
        if editing:
            entries[int(choice.split(":")[0]) - 1] = new_entry
        else:
            data["days"].setdefault(day.isoformat(), []).append(new_entry)
        st.session_state.data = data
        save_user_data(st.session_state.user, data)
        st.rerun()


def remove_food_form(data, day):
    entries = data["days"].get(day.isoformat(), [])
    if not entries:
        return
    opts = {f"{i + 1}: {e['name']}": i for i, e in enumerate(entries)}
    target = st.selectbox(tr("remove_entry"), [tr("select")] + list(opts),
                          key=f"food_remove_{day.isoformat()}")
    if st.button(tr("remove"), key=f"food_remove_btn_{day.isoformat()}",
                 disabled=target == tr("select")):
        data["days"][day.isoformat()].pop(opts[target])
        if not data["days"][day.isoformat()]:
            del data["days"][day.isoformat()]
        st.session_state.data = data
        save_user_data(st.session_state.user, data)
        st.rerun()


def food_table(data, day):
    entries = data["days"].get(day.isoformat(), [])
    cats = diet_categories(data)
    rows = []
    for i, e in enumerate(entries, start=1):
        row = {"#": i, tr("food"): e["name"], tr("meal"): tr(e["meal"]),
               tr("amount"): f"{e['amount'][0]:g} {e['amount'][1]}" if e.get("amount") else ""}
        for key, cat in cats.items():
            if key == "calories":
                row[tr("calories")] = f"{e['calories']} kcal"
            else:
                val = e.get("extras", {}).get(key)
                row[cat.name] = f"{val[0]:g} {val[1]}" if val else ""
        rows.append(row)
    if rows:
        st.table(rows)
    else:
        st.info(tr("no_food"))


def categories_manager(data):
    with st.expander(tr("category_limits")):
        st.write(tr("current_categories"))
        for key, c in data["diet_categories"].items():
            st.write(f"- {c['name']} ({c['unit']}): {c['limit']} {tr('per_day')}")

        cal_limit = st.number_input(tr("calorie_limit"), min_value=0, step=50,
                                    value=int(data["diet_categories"]["calories"]["limit"]),
                                    key="cal_limit_input")
        if st.button(tr("update_calorie_limit")):
            data["diet_categories"]["calories"]["limit"] = int(cal_limit)
            st.session_state.data = data
            save_user_data(st.session_state.user, data)
            st.rerun()

        with st.form("add_category"):
            cname = st.text_input(tr("category_name"))
            cunit = st.text_input(tr("unit"), value="g")
            climit = st.number_input(tr("daily_limit"), min_value=0, step=1, value=10)
            if st.form_submit_button(tr("add_category")):
                if not cname.strip():
                    st.error(tr("name_empty"))
                elif cname.strip().lower() in data["diet_categories"]:
                    st.error(tr("category_exists"))
                else:
                    data["diet_categories"][cname.strip().lower()] = {
                        "name": cname.strip(), "unit": cunit.strip() or "g", "limit": int(climit),
                    }
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
    entries = data["spends"].get(day.isoformat(), [])
    options = [tr("add_new")] + [f"{i + 1}: {e['name']}" for i, e in enumerate(entries)]
    choice = st.selectbox(tr("entry"), options, key=f"spend_choice_{day.isoformat()}")
    editing = choice != tr("add_new")
    entry = entries[int(choice.split(":")[0]) - 1] if editing else None

    cat_labels = {c: budget_cat_display(c) for c in CATEGORIES}
    with st.form(key=f"spend_form_{day.isoformat()}_{'e' if editing else 'n'}"):
        name = st.text_input(tr("spending_name"), value=entry["name"] if entry else "")
        category_label = st.selectbox(
            tr("category"), list(cat_labels.values()),
            index=CATEGORIES.index(entry["category"]) if entry and entry["category"] in CATEGORIES else 0,
        )
        category = CATEGORIES[list(cat_labels.values()).index(category_label)]
        price = st.number_input(tr("price"), min_value=0.0,
                                value=float(entry["price"]) if entry else 0.0,
                                step=1.0)
        submitted = st.form_submit_button(tr("save"))

    if submitted:
        if not name.strip():
            st.error(tr("name_empty"))
            return
        new_entry = {"name": name.strip(), "category": category, "price": float(price)}
        if editing:
            entries[int(choice.split(":")[0]) - 1] = new_entry
        else:
            data["spends"].setdefault(day.isoformat(), []).append(new_entry)
        st.session_state.data = data
        save_user_data(st.session_state.user, data)
        st.rerun()


def remove_spending_form(data, day):
    entries = data["spends"].get(day.isoformat(), [])
    if not entries:
        return
    opts = {f"{i + 1}: {e['name']}": i for i, e in enumerate(entries)}
    target = st.selectbox(tr("remove_entry"), [tr("select")] + list(opts),
                          key=f"spend_remove_{day.isoformat()}")
    if st.button(tr("remove"), key=f"spend_remove_btn_{day.isoformat()}",
                 disabled=target == tr("select")):
        data["spends"][day.isoformat()].pop(opts[target])
        if not data["spends"][day.isoformat()]:
            del data["spends"][day.isoformat()]
        st.session_state.data = data
        save_user_data(st.session_state.user, data)
        st.rerun()


def spending_table(data, day):
    entries = data["spends"].get(day.isoformat(), [])
    rows = [{"#": i, tr("spending"): e["name"], tr("category"): budget_cat_display(e["category"]),
             tr("price_col"): f"{e['price']:g} HKD"} for i, e in enumerate(entries, start=1)]
    if rows:
        st.table(rows)
    else:
        st.info(tr("no_spending"))


# ------------------------------------------------------------- combined

def render_diet_section(data, selected):
    st.markdown(f"#### {tr('diet')}")
    with st.expander(tr("category_limits")):
        categories_manager(data)
    food_form(data, selected)
    remove_food_form(data, selected)
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
            st.write(f"{cat.name}: **{total}**{flag}")
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

    spending_form(data, selected)
    remove_spending_form(data, selected)
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


def leaderboard():
    """Rank every user by their combined diet score, as of today."""
    with get_db() as conn:
        rows = conn.execute("SELECT username, json FROM user_data").fetchall()
    board = []
    today = date.today()
    for user, json_str in rows:
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            continue
        day_s, week_s, month_s = compute_streaks(
            build_all_days(data), diet_categories(data), today
        )
        board.append((user, day_s, week_s, month_s, diet_score(day_s, week_s, month_s)))
    board.sort(key=lambda r: r[4], reverse=True)
    return board


def leaderboard_table():
    board = leaderboard()
    if not board:
        st.write(tr("no_users_yet"))
        return
    rows = []
    for place, (user, d, w, m, score) in enumerate(board, start=1):
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
    st.table(rows)


def render_app(data):
    with st.expander("🏆 " + tr("leaderboard")):
        leaderboard_table()
    selected = calendar_widget(
        "global", lambda d: (diet_status(data, d), budget_status(data, d))
    )
    st.subheader(format_date(selected))
    st.markdown(
        f"🟢 {tr('within_limit')}　🔴 {tr('over_limit')}　· {tr('no_entries')}　"
        f"| {tr('diet_budget_legend')}"
    )

    col_diet, col_budget = st.columns(2, gap="large")
    with col_diet:
        render_diet_section(data, selected)
    with col_budget:
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


def main():
    st.set_page_config(page_title=STRINGS["en"]["app_title"], layout="wide")
    init_db()

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
