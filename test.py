import calendar
import json
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from main import (
    Value, FoodEntry, DietDay, SpendingEntry, CategoryLimit,
    compute_streaks, compute_budget_streaks, categories_satisfied, diet_rank, diet_score,
)
from streamlit.testing.v1 import AppTest
import main as core
import app as webapp

APP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")

TMP_DATA = os.path.join(tempfile.gettempdir(), "diet_budget_test_data.json")

LIMIT = 2000


def cats(calories=LIMIT, sugar=None):
    result = {"calories": CategoryLimit("Calories", "kcal", calories)}
    if sugar is not None:
        result["sugar"] = CategoryLimit("Sugar", "g", sugar)
    return result


def make_days(calories_by_offset):
    days = {}
    ref = date(2026, 8, 17)
    for offset, kcal in calories_by_offset.items():
        d = ref + timedelta(days=offset)
        day = DietDay(d)
        if kcal is not None:
            day.add_entry(FoodEntry("Test Food", "lunch", Value(kcal, "kcal")))
        days[d] = day
    return days, ref


def fill_month(days, year, month, kcal):
    n = calendar.monthrange(year, month)[1]
    for d in range(1, n + 1):
        day = DietDay(date(year, month, d))
        day.add_entry(FoodEntry("F", "breakfast", Value(kcal, "kcal")))
        days[date(year, month, d)] = day


class TestValue(unittest.TestCase):
    def test_add(self):
        total = Value(300, "kcal") + Value(250, "kcal")
        self.assertEqual(total.amount, 550)
        self.assertEqual(total.unit, "kcal")

    def test_str(self):
        self.assertEqual(str(Value(500, "kcal")), "500 kcal")

    def test_str_float_formatting(self):
        self.assertEqual(str(Value(250.0, "g")), "250 g")
        self.assertEqual(str(Value(1.5, "portions")), "1.5 portions")

    def test_unit_mismatch_raises(self):
        with self.assertRaises(ValueError):
            Value(300, "kcal") + Value(10, "g")


class TestFoodEntry(unittest.TestCase):
    def test_amount_and_extras(self):
        entry = FoodEntry("Apple", "snack", Value(95, "kcal"), Value(150, "g"))
        self.assertEqual(entry.amount.amount, 150)
        self.assertEqual(entry.amount.unit, "g")
        entry.extras["sugar"] = Value(12, "g")
        self.assertEqual(entry.extras["sugar"].amount, 12)


class TestDietDay(unittest.TestCase):
    def test_sum_of_empty(self):
        day = DietDay(date(2026, 8, 17))
        self.assertEqual(day.sum_of("calories").amount, 0)

    def test_sum_remove_and_extras(self):
        day = DietDay(date(2026, 8, 17))
        day.add_entry(FoodEntry("A", "breakfast", Value(300, "kcal")))
        day.add_entry(FoodEntry("B", "dinner", Value(500, "kcal"), extras={"sugar": Value(10, "g")}))
        day.add_entry(FoodEntry("C", "snack", Value(100, "kcal"), extras={"sugar": Value(20, "g")}))
        self.assertEqual(day.sum_of("calories").amount, 900)
        self.assertEqual(day.sum_of("sugar", "g").amount, 30)
        day.remove_entry(0)
        self.assertEqual(day.sum_of("calories").amount, 600)
        self.assertEqual(day.sum_of("protein", "g").amount, 0)


class TestCategoriesSatisfied(unittest.TestCase):
    def test_all_categories_within_limit(self):
        day = DietDay(date(2026, 8, 17))
        day.add_entry(FoodEntry("A", "lunch", Value(1500, "kcal"), extras={"sugar": Value(30, "g")}))
        self.assertTrue(categories_satisfied(day, cats(2000, 50)))

    def test_one_category_over_limit(self):
        day = DietDay(date(2026, 8, 17))
        day.add_entry(FoodEntry("A", "lunch", Value(1500, "kcal"), extras={"sugar": Value(60, "g")}))
        self.assertFalse(categories_satisfied(day, cats(2000, 50)))


class TestDayStreak(unittest.TestCase):
    def test_consecutive_days_under_limit(self):
        days, ref = make_days({0: 1800, -1: 1900, -2: 2000, -3: 1800})
        self.assertEqual(compute_streaks(days, cats(), ref)[0], 4)

    def test_day_over_limit_breaks_streak(self):
        days, ref = make_days({0: 1800, -1: 2100, -2: 1800})
        self.assertEqual(compute_streaks(days, cats(), ref)[0], 1)

    def test_missing_day_breaks_streak(self):
        days, ref = make_days({0: 1800, -2: 1800, -3: 1800})
        self.assertEqual(compute_streaks(days, cats(), ref)[0], 1)

    def test_no_data_today(self):
        days, ref = make_days({-1: 1800})
        self.assertEqual(compute_streaks(days, cats(), ref)[0], 0)

    def test_extra_category_over_breaks_day_streak(self):
        days, ref = make_days({0: 1800, -1: 1500})
        days[ref].entries[0].extras["sugar"] = Value(40, "g")    # day 0 over sugar limit
        days[ref - timedelta(days=1)].entries[0].extras["sugar"] = Value(10, "g")
        self.assertEqual(compute_streaks(days, cats(2000, 30), ref)[0], 0)

    def test_extra_category_over_ends_streak_at_prior_day(self):
        days, ref = make_days({0: 1800, -1: 1500, -2: 1500})
        days[ref].entries[0].extras["sugar"] = Value(10, "g")
        days[ref - timedelta(days=1)].entries[0].extras["sugar"] = Value(40, "g")  # over
        days[ref - timedelta(days=2)].entries[0].extras["sugar"] = Value(10, "g")
        self.assertEqual(compute_streaks(days, cats(2000, 30), ref)[0], 1)


class TestWeekStreak(unittest.TestCase):
    def test_two_full_weeks_under_allowance(self):
        days, _ = make_days({})
        ref = date(2026, 8, 17)  # Monday
        for offset in range(7):
            days[ref + timedelta(days=offset)] = _logged(100)
        prev = ref - timedelta(days=7)
        for offset in range(7):
            days[prev + timedelta(days=offset)] = _logged(100)
        self.assertEqual(compute_streaks(days, cats(), ref)[1], 2)

    def test_over_week_breaks_streak(self):
        days, _ = make_days({})
        ref = date(2026, 8, 17)
        for offset in range(7):
            days[ref + timedelta(days=offset)] = _logged(100)
        prev = ref - timedelta(days=7)
        for offset in range(7):
            days[prev + timedelta(days=offset)] = _logged(3000)
        self.assertEqual(compute_streaks(days, cats(), ref)[1], 1)

    def test_partial_week_does_not_count(self):
        days, _ = make_days({})
        ref = date(2026, 8, 17)
        days[ref] = _logged(100)
        prev = ref - timedelta(days=7)
        for offset in range(7):
            days[prev + timedelta(days=offset)] = _logged(100)
        self.assertEqual(compute_streaks(days, cats(), ref)[1], 0)

    def test_empty_week_breaks_streak(self):
        days, _ = make_days({})
        ref = date(2026, 8, 17)
        for offset in range(7):
            days[ref + timedelta(days=offset)] = _logged(100)
        self.assertEqual(compute_streaks(days, cats(), ref)[1], 1)

    def test_category_exceeds_weekly_total_breaks_streak(self):
        days, _ = make_days({})
        ref = date(2026, 8, 17)
        for offset in range(7):
            days[ref + timedelta(days=offset)] = _logged(100, sugar=10)
        prev = ref - timedelta(days=7)
        for offset in range(7):
            # sugar totals 70 > 30 * 7? No: 10*7=70 <= 30*7=210 -> met; use 200
            days[prev + timedelta(days=offset)] = _logged(100, sugar=200)
        # current week sugar = 70 <= 210 met; prev sugar 1400 > 210 not met
        self.assertEqual(compute_streaks(days, cats(2000, 30), ref)[1], 1)


class TestMonthStreak(unittest.TestCase):
    def test_two_full_months_under_allowance(self):
        days = {}
        fill_month(days, 2026, 2, 100)
        fill_month(days, 2026, 1, 100)
        self.assertEqual(compute_streaks(days, cats(), date(2026, 2, 10))[2], 2)

    def test_over_month_breaks_streak(self):
        days = {}
        fill_month(days, 2026, 2, 100)
        fill_month(days, 2026, 1, 5000)
        self.assertEqual(compute_streaks(days, cats(), date(2026, 2, 10))[2], 1)

    def test_partial_month_does_not_count(self):
        days = {}
        for d in range(1, 6):
            day = DietDay(date(2026, 2, d))
            day.add_entry(FoodEntry("F", "breakfast", Value(100, "kcal")))
            days[date(2026, 2, d)] = day
        fill_month(days, 2026, 1, 100)
        self.assertEqual(compute_streaks(days, cats(), date(2026, 2, 10))[2], 0)

    def test_missing_month_breaks_streak(self):
        days = {}
        fill_month(days, 2026, 2, 100)
        self.assertEqual(compute_streaks(days, cats(), date(2026, 2, 10))[2], 1)


class TestDietRank(unittest.TestCase):
    def test_diet_score_weighs_streaks(self):
        self.assertEqual(diet_score(10, 2, 1), 10 + 14 + 30)
        self.assertEqual(diet_score(0, 0, 0), 0)

    def test_rank_thresholds(self):
        cases = [
            ((0, 0, 0), "rank_none"),           # score 0
            ((7, 0, 0), "rank_rookie"),          # score 7
            ((30, 0, 0), "rank_consistent"),     # score 30
            ((60, 0, 0), "rank_dedicated"),      # score 60
            ((120, 0, 0), "rank_marathoner"),    # score 120
            ((200, 0, 0), "rank_disciplined"),   # score 200
            ((365, 0, 0), "rank_legend"),        # score 365
            ((10, 3, 1), "rank_dedicated"),      # 10 + 21 + 30 = 61
            ((100, 5, 3), "rank_disciplined"),   # 100 + 35 + 90 = 225
            ((100, 10, 10), "rank_legend"),      # 100 + 70 + 300 = 470
        ]
        for streaks, expected in cases:
            self.assertEqual(diet_rank(*streaks)[0], expected, f"streaks={streaks}")

    def test_rank_returns_score(self):
        self.assertEqual(diet_rank(10, 2, 1)[1], 54)


class TestBudgetStreaks(unittest.TestCase):
    def test_month_limit_only_month_streak(self):
        spends = {date(2026, 2, 1): [SpendingEntry("Rent", "Utilities", Value(5000, "HKD"))],
                  date(2026, 1, 3): [SpendingEntry("Food", "Food", Value(800, "HKD"))]}
        self.assertEqual(compute_budget_streaks(spends, "month", 8000, date(2026, 2, 10)),
                         {"month": 2})

    def test_month_limit_over(self):
        spends = {date(2026, 2, 1): [SpendingEntry("Rent", "Utilities", Value(5000, "HKD"))],
                  date(2026, 1, 3): [SpendingEntry("Big", "Other", Value(30000, "HKD"))]}
        self.assertEqual(compute_budget_streaks(spends, "month", 8000, date(2026, 2, 10)),
                         {"month": 1})

    def test_month_limit_empty_previous(self):
        spends = {date(2026, 2, 1): [SpendingEntry("Rent", "Utilities", Value(5000, "HKD"))]}
        self.assertEqual(compute_budget_streaks(spends, "month", 8000, date(2026, 2, 10)),
                         {"month": 1})

    def test_week_limit_week_and_month_streaks(self):
        ref = date(2026, 8, 17)  # Monday
        spends = {ref: [SpendingEntry("A", "Food", Value(100, "HKD"))],
                  ref - timedelta(days=2): [SpendingEntry("B", "Food", Value(50, "HKD"))],
                  ref - timedelta(days=7): [SpendingEntry("C", "Food", Value(80, "HKD"))]}
        streaks = compute_budget_streaks(spends, "week", 3000, ref)
        self.assertEqual(streaks["week"], 2)
        self.assertEqual(streaks["month"], 1)
        self.assertNotIn("day", streaks)

    def test_week_limit_over(self):
        ref = date(2026, 8, 17)
        spends = {ref: [SpendingEntry("A", "Food", Value(100, "HKD"))],
                  ref - timedelta(days=7): [SpendingEntry("C", "Food", Value(5000, "HKD"))]}
        streaks = compute_budget_streaks(spends, "week", 3000, ref)
        self.assertEqual(streaks["week"], 1)
        self.assertEqual(streaks["month"], 1)

    def test_day_limit_all_streaks(self):
        ref = date(2026, 8, 17)  # Monday
        spends = {ref: [SpendingEntry("A", "Food", Value(100, "HKD"))],
                  ref - timedelta(days=1): [SpendingEntry("B", "Food", Value(50, "HKD"))],
                  ref - timedelta(days=2): [SpendingEntry("C", "Food", Value(80, "HKD"))]}
        streaks = compute_budget_streaks(spends, "day", 500, ref)
        self.assertEqual(streaks["day"], 3)
        self.assertEqual(streaks["week"], 2)
        self.assertEqual(streaks["month"], 1)

    def test_day_limit_over(self):
        ref = date(2026, 8, 17)
        spends = {ref: [SpendingEntry("A", "Food", Value(100, "HKD"))],
                  ref - timedelta(days=1): [SpendingEntry("B", "Food", Value(2000, "HKD"))]}
        streaks = compute_budget_streaks(spends, "day", 500, ref)
        self.assertEqual(streaks["day"], 1)
        self.assertEqual(streaks["week"], 2)
        self.assertEqual(streaks["month"], 1)


class TestPersistence(unittest.TestCase):
    def tearDown(self):
        if os.path.exists(TMP_DATA):
            os.remove(TMP_DATA)

    def test_json_round_trip(self):
        import main as m
        m.DATA_FILE = TMP_DATA

        app = m.DietTrackerApp.__new__(m.DietTrackerApp)
        app.diet_categories = {
            "calories": m.CategoryLimit("Calories", "kcal", 1800),
            "sugar": m.CategoryLimit("Sugar", "g", 30),
        }
        d = date(2026, 8, 17)
        day = m.DietDay(d)
        day.add_entry(m.FoodEntry("Apple", "lunch", m.Value(300, "kcal"),
                                  m.Value(150, "g"), {"sugar": m.Value(10, "g")}))
        day.add_entry(m.FoodEntry("Plain Rice", "dinner", m.Value(200, "kcal")))
        app.days = {d: day}
        app.spends = {d: [m.SpendingEntry("Rent", "Utilities", m.Value(5000, "HKD"))]}
        app.budget_period = "month"
        app.budget_limit = m.Value(9000, "HKD")
        app.save_data()

        loaded = m.DietTrackerApp.__new__(m.DietTrackerApp)
        loaded.load_data()

        self.assertEqual(loaded.diet_categories["calories"].limit, 1800)
        self.assertEqual(loaded.diet_categories["sugar"].unit, "g")
        self.assertEqual(loaded.diet_categories["sugar"].limit, 30)
        self.assertEqual(len(loaded.days[d].entries), 2)
        first = loaded.days[d].entries[0]
        self.assertEqual(first.name, "Apple")
        self.assertEqual(first.calories.amount, 300)
        self.assertEqual(first.amount.unit, "g")
        self.assertEqual(first.extras["sugar"].amount, 10)
        self.assertEqual(loaded.days[d].entries[1].extras, {})
        self.assertEqual(loaded.budget_period, "month")
        self.assertEqual(loaded.budget_limit.amount, 9000)
        self.assertEqual(loaded.spends[d][0].name, "Rent")
        self.assertEqual(str(loaded.spends[d][0].price), "5000 HKD")


def _logged(kcal, sugar=None):
    day = DietDay(date.today())
    extras = {"sugar": Value(sugar, "g")} if sugar is not None else {}
    day.add_entry(FoodEntry("Test Food", "lunch", Value(kcal, "kcal"), extras=extras))
    return day


class TestLeaderboards(unittest.TestCase):
    DB = os.path.join(tempfile.gettempdir(), "diet_budget_test_leaders.db")

    def setUp(self):
        webapp.DB_PATH = self.DB
        if os.path.exists(self.DB):
            os.remove(self.DB)
        webapp.init_db()

    def tearDown(self):
        if os.path.exists(self.DB):
            os.remove(self.DB)

    def add_user(self, name):
        salt = os.urandom(16).hex()
        with webapp.get_db() as conn:
            conn.execute("INSERT INTO users (username, salt, hash) VALUES (?,?,?)",
                         (name, salt, "0" * 64))
            conn.execute("INSERT INTO user_data (username, json) VALUES (?,?)",
                         (name, json.dumps(webapp.default_data())))

    def test_create_and_join(self):
        self.add_user("alice")
        self.add_user("bob")
        ok, key = webapp.create_leaderboard("Weight Loss", "abc123", "alice")
        self.assertTrue(ok)
        self.assertEqual(key, "leaderboard_created")
        my = webapp.my_leaderboards("alice")
        self.assertEqual(len(my), 1)
        self.assertEqual(my[0]["name"], "Weight Loss")
        self.assertEqual(my[0]["members"], ["alice"])

        ok, key = webapp.join_leaderboard("Weight Loss", "abc123", "bob")
        self.assertTrue(ok)
        self.assertEqual(webapp.all_leaderboards()[0]["members"], ["alice", "bob"])
        self.assertEqual(webapp.all_leaderboards()[0]["member_count"], 2)

    def test_wrong_code_or_name(self):
        self.add_user("alice")
        webapp.create_leaderboard("Weight Loss", "abc123", "alice")
        self.assertEqual(webapp.join_leaderboard("Weight Loss", "nope", "alice")[1],
                         "wrong_access_code")
        self.assertEqual(webapp.join_leaderboard("Nope", "abc123", "alice")[1],
                         "wrong_access_code")

    def test_create_without_member(self):
        ok, key = webapp.create_leaderboard("Admin Board", "code1", None)
        self.assertTrue(ok)
        self.assertEqual(key, "leaderboard_created")
        board = webapp.all_leaderboards()[0]
        self.assertEqual(board["name"], "Admin Board")
        self.assertEqual(board["members"], [])
        self.assertEqual(board["member_count"], 0)

    def test_delete_leaderboard(self):
        self.add_user("alice")
        webapp.create_leaderboard("A", "1", "alice")
        webapp.join_leaderboard("A", "1", "alice")
        lid = webapp.all_leaderboards()[0]["id"]
        ok, key = webapp.delete_leaderboard(lid)
        self.assertTrue(ok)
        self.assertEqual(key, "leaderboard_removed")
        self.assertEqual(webapp.all_leaderboards(), [])

    def test_delete_renumbers_ids_and_memberships(self):
        self.add_user("alice")
        webapp.create_leaderboard("A", "1", "alice")
        webapp.create_leaderboard("B", "2", None)
        webapp.create_leaderboard("C", "3", None)
        self.assertEqual([b["id"] for b in webapp.all_leaderboards()], [1, 2, 3])
        webapp.delete_leaderboard(2)
        boards = webapp.all_leaderboards()
        self.assertEqual([b["id"] for b in boards], [1, 2])
        self.assertEqual([b["name"] for b in boards], ["A", "C"])
        self.assertEqual([b for b in boards if b["name"] == "A"][0]["members"], ["alice"])
        webapp.create_leaderboard("D", "4", None)
        self.assertEqual([b["id"] for b in webapp.all_leaderboards()], [1, 2, 3])

    def test_duplicate_name_and_already_member(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_leaderboard("A", "1", "alice")
        self.assertEqual(webapp.create_leaderboard("A", "2", "bob")[0], False)
        self.assertEqual(webapp.join_leaderboard("A", "1", "alice")[1], "already_member")

    def test_leave_leaderboard_recomputes_ranks(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_leaderboard("A", "1", "alice")
        webapp.join_leaderboard("A", "1", "bob")
        today = date.today()
        entry = {"name": "Salad", "meal": "lunch", "calories": 100, "amount": None, "extras": {}}
        data = webapp.load_user_data("bob")
        data["days"][today.isoformat()] = [entry]
        webapp.save_user_data("bob", data)

        board = webapp.all_leaderboards()[0]
        self.assertEqual([r[0] for r in webapp.rank_users(board["members"])], ["bob", "alice"])
        ok, key = webapp.leave_leaderboard(board["id"], "bob")
        self.assertTrue(ok)
        self.assertEqual(key, "leaderboard_left")
        board = webapp.all_leaderboards()[0]
        self.assertEqual(board["members"], ["alice"])
        self.assertEqual([r[0] for r in webapp.rank_users(board["members"])], ["alice"])
        self.assertEqual(webapp.my_leaderboards("bob"), [])
        self.assertEqual(webapp.my_leaderboards("alice")[0]["name"], "A")

    def test_kick_member(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_leaderboard("A", "1", "alice")
        webapp.join_leaderboard("A", "1", "bob")
        ok, key = webapp.kick_member(webapp.all_leaderboards()[0]["id"], "bob")
        self.assertTrue(ok)
        self.assertEqual(key, "member_kicked")
        self.assertEqual(webapp.all_leaderboards()[0]["members"], ["alice"])
        self.assertEqual(webapp.my_leaderboards("bob"), [])

    def test_rename_and_change_code(self):
        self.add_user("alice")
        ok, _ = webapp.create_leaderboard("A", "1", "alice")
        self.assertTrue(ok)
        lid = webapp.all_leaderboards()[0]["id"]
        webapp.rename_leaderboard(lid, "B")
        webapp.change_access_code(lid, "2")
        board = webapp.all_leaderboards()[0]
        self.assertEqual(board["name"], "B")
        self.assertEqual(board["access_code"], "2")

    def test_rename_user(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_leaderboard("A", "1", "alice")
        webapp.join_leaderboard("A", "1", "bob")

        ok, key = webapp.rename_user("alice", "alice2")
        self.assertTrue(ok)
        self.assertEqual(key, "username_changed")
        self.assertIn("alice2", webapp.all_usernames())
        self.assertNotIn("alice", webapp.all_usernames())
        members = webapp.all_leaderboards()[0]["members"]
        self.assertIn("alice2", members)
        self.assertIn("bob", members)

        self.assertEqual(webapp.rename_user("ghost", "x")[1], "user_not_found")
        self.assertEqual(webapp.rename_user("alice2", "bob")[1], "username_exists")
        self.assertEqual(webapp.rename_user("bob", "   ")[1], "username_empty")

    def test_rename_to_same_is_noop(self):
        self.add_user("alice")
        ok, _ = webapp.rename_user("alice", "alice")
        self.assertTrue(ok)

    def test_rename_admin_blocked(self):
        self.add_user("alice")
        ok, key = webapp.rename_user(webapp.ADMIN_USER, "root")
        self.assertFalse(ok)
        self.assertEqual(key, "cannot_rename_admin")
        self.assertNotIn("root", webapp.all_usernames())
        self.assertIn("alice", webapp.all_usernames())

    def test_rank_users_orders_by_score(self):
        for name in ("alice", "bob"):
            self.add_user(name)
        today = date.today()
        entry = {"name": "Salad", "meal": "lunch", "calories": 100, "amount": None, "extras": {}}
        data = webapp.load_user_data("alice")
        data["days"][today.isoformat()] = [entry]
        data["days"][(today - timedelta(days=1)).isoformat()] = [entry]
        webapp.save_user_data("alice", data)

        ranked = webapp.rank_users(["bob", "alice"])
        self.assertEqual(ranked[0][0], "alice")
        self.assertEqual(ranked[0][4], webapp.diet_score(2, 0, 0))
        self.assertEqual(ranked[-1][0], "bob")


class TestAdminRestrictions(unittest.TestCase):
    """Admin sees users + leaderboard settings only: no diet/budget add,
    no leaderboard create/join forms."""

    DB = os.path.join(os.path.dirname(os.path.abspath(webapp.__file__)), "streamlit_data.db")

    def setUp(self):
        webapp.DB_PATH = self.DB
        if os.path.exists(self.DB):
            os.remove(self.DB)
        webapp.init_db()
        webapp.ensure_admin()
        self.at = AppTest.from_file(APP_PATH)
        self.at.run(timeout=60)
        self.at.session_state["user"] = webapp.ADMIN_USER
        self.at.session_state["data"] = webapp.default_data()
        self.at.run(timeout=60)

    def tearDown(self):
        if os.path.exists(self.DB):
            os.remove(self.DB)

    def boot(self, user):
        at = AppTest.from_file(APP_PATH)
        at.run(timeout=60)
        at.session_state["user"] = user
        at.session_state["data"] = webapp.default_data()
        at.run(timeout=60)
        return at

    def test_admin_has_no_diet_budget_tabs(self):
        labels = [tab.label for tab in self.at.tabs]
        self.assertNotIn("Diet", labels)
        self.assertNotIn("Budget", labels)

    def test_admin_has_no_add_buttons(self):
        for b in self.at.button:
            self.assertNotEqual(b.label.strip().lower(), "add")

    def test_admin_has_no_leaderboard_forms(self):
        keys = {t.key for t in self.at.text_input}
        self.assertFalse(keys & {"lb_name", "lb_code", "jb_name", "jb_code"})

    def test_admin_has_admin_panels(self):
        labels = [e.label for e in self.at.expander]
        self.assertTrue(any("Admin panel" in l for l in labels))
        self.assertTrue(any("Leaderboards" in l for l in labels))

    def test_admin_can_manage_but_not_join(self):
        webapp.create_leaderboard("Board", "x1", None)
        self.at.run(timeout=60)
        keys = {t.key for t in self.at.text_input}
        self.assertTrue({"alb_name", "alb_code"} <= keys)
        self.assertTrue(any("Remove leaderboard" in b.label for b in self.at.button))
        self.assertFalse(keys & {"lb_name", "lb_code", "jb_name", "jb_code"})

    def test_admin_can_kick_member(self):
        salt = os.urandom(16).hex()
        with webapp.get_db() as conn:
            conn.execute("INSERT INTO users (username, salt, hash) VALUES (?,?,?)",
                         ("bob", salt, webapp.hash_password("pw", salt)))
        webapp.create_leaderboard("Team", "x", "bob")
        self.at.run(timeout=60)
        kick_sel = [s for s in self.at.selectbox if s.key == "adm_kick_sel_1"][0]
        self.assertEqual(kick_sel.options, ["bob"])
        kick_sel.set_value("bob")
        [b for b in self.at.button if b.key == "adm_kick_btn_1"][0].click()
        self.at.run(timeout=60)
        self.assertTrue(any("Remove bob from this leaderboard" in w.value for w in self.at.warning))
        [b for b in self.at.button if b.key == "adm_kick_yes_1"][0].click()
        self.at.run(timeout=60)
        self.assertEqual(webapp.all_leaderboards()[0]["members"], [])

    def test_normal_user_still_has_everything(self):
        salt = os.urandom(16).hex()
        with webapp.get_db() as conn:
            conn.execute("INSERT INTO users (username, salt, hash) VALUES (?,?,?)",
                         ("bob", salt, webapp.hash_password("pw", salt)))
        at = self.boot("bob")
        tab_labels = [tab.label for tab in at.tabs]
        self.assertIn("Diet", tab_labels)
        self.assertIn("Budget", tab_labels)
        keys = {t.key for t in at.text_input}
        self.assertTrue(keys & {"lb_name", "lb_code", "jb_name", "jb_code"})
        self.assertTrue(any("Add item" in b.label for b in at.button))
        self.assertFalse(any("Admin panel" in e.label for e in at.expander))


class TestUserLeaderboardUI(unittest.TestCase):
    """User leaderboards are a dropdown listing joined boards + Add/Join actions."""

    DB = os.path.join(os.path.dirname(os.path.abspath(webapp.__file__)), "streamlit_data.db")

    def setUp(self):
        webapp.DB_PATH = self.DB
        if os.path.exists(self.DB):
            os.remove(self.DB)
        webapp.init_db()
        webapp.ensure_admin()
        salt = os.urandom(16).hex()
        with webapp.get_db() as conn:
            conn.execute("INSERT INTO users (username, salt, hash) VALUES (?,?,?)",
                         ("bob", salt, webapp.hash_password("pw", salt)))
        self.at = AppTest.from_file(APP_PATH)
        self.at.run(timeout=60)
        self.at.session_state["user"] = "bob"
        self.at.session_state["data"] = webapp.default_data()
        self.at.run(timeout=60)

    def tearDown(self):
        if os.path.exists(self.DB):
            os.remove(self.DB)

    def test_dropdown_contains_add_join_and_joined_boards(self):
        webapp.create_leaderboard("Team A", "x", "bob")
        self.at.run(timeout=60)
        dd = [s for s in self.at.selectbox if s.key == "lb_dd"][0]
        self.assertTrue(any(o.startswith("➕") and "Add" in o for o in dd.options))
        self.assertTrue(any(o.startswith("➕") and "Join" in o for o in dd.options))
        self.assertTrue(any("Team A" in o for o in dd.options))

    def test_default_is_add_form_when_no_boards(self):
        dd = [s for s in self.at.selectbox if s.key == "lb_dd"][0]
        self.assertEqual(dd.index, 0)
        keys = {t.key for t in self.at.text_input}
        self.assertIn("lb_name", keys)

    def test_join_action_shows_join_form(self):
        webapp.create_leaderboard("Team A", "x", None)
        self.at.run(timeout=60)
        dd = [s for s in self.at.selectbox if s.key == "lb_dd"][0]
        join_opt = [o for o in dd.options if "Join" in o][0]
        dd.set_value(join_opt)
        self.at.run(timeout=60)
        keys = {t.key for t in self.at.text_input}
        self.assertIn("jb_name", keys)
        self.assertIn("jb_code", keys)

    def test_selecting_joined_board_shows_rank_table(self):
        webapp.create_leaderboard("Team A", "x", "bob")
        self.at.run(timeout=60)
        dd = [s for s in self.at.selectbox if s.key == "lb_dd"][0]
        team_opt = [o for o in dd.options if "Team A" in o][0]
        dd.set_value(team_opt)
        self.at.run(timeout=60)
        self.assertGreaterEqual(len(self.at.table), 1)
        self.assertIn("bob", str(self.at.table[0].value))

    def test_leave_leaderboard_flow(self):
        webapp.create_leaderboard("Team A", "x", "bob")
        self.at.run(timeout=60)
        dd = [s for s in self.at.selectbox if s.key == "lb_dd"][0]
        team_opt = [o for o in dd.options if "Team A" in o][0]
        dd.set_value(team_opt)
        self.at.run(timeout=60)
        self.assertTrue(any("Leave leaderboard" in b.label for b in self.at.button))
        [b for b in self.at.button if b.key == "lb_leave_1"][0].click()
        self.at.run(timeout=60)
        self.assertTrue(any("Leave this leaderboard" in w.value for w in self.at.warning))
        [b for b in self.at.button if b.key == "lb_leave_yes_1"][0].click()
        self.at.run(timeout=60)
        self.assertEqual(webapp.my_leaderboards("bob"), [])
        dd = [s for s in self.at.selectbox if s.key == "lb_dd"][0]
        self.assertFalse(any("Team A" in o for o in dd.options))
        self.assertEqual(dd.index, 0)


class TestTranslationCoverage(unittest.TestCase):
    """Every tr(...) key used in app.py must exist in both languages."""

    def test_all_tr_keys_covered_in_both_langs(self):
        src = open(APP_PATH, encoding="utf-8").read()
        keys = set(re.findall(r'tr\(["\']([^"\']+)["\']\)', src))
        self.assertTrue(keys)
        missing_en = {k for k in keys if k not in core.STRINGS["en"]}
        missing_zh = {k for k in keys if k not in core.STRINGS["zh"]}
        self.assertEqual(missing_en, set(), f"missing EN keys: {sorted(missing_en)}")
        self.assertEqual(missing_zh, set(), f"missing ZH keys: {sorted(missing_zh)}")

    def test_dicts_are_symmetric(self):
        self.assertEqual(set(core.STRINGS["en"]), set(core.STRINGS["zh"]))


if __name__ == "__main__":
    unittest.main()