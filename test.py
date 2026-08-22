import calendar
import json
import os
import re
import sqlite3
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


class TestGroups(unittest.TestCase):
    """Group lifecycle: create/join/membership roles, owner management, permissions."""
    DB = os.path.join(tempfile.gettempdir(), "diet_budget_test_groups.db")

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

    def member_names(self, gid):
        return [m["username"] for m in webapp.group_members(gid)]

    def test_create_and_join(self):
        self.add_user("alice")
        self.add_user("bob")
        ok, key = webapp.create_group("Weight Loss", "abc123", "alice")
        self.assertTrue(ok)
        self.assertEqual(key, "group_created")
        my = webapp.my_groups("alice")
        self.assertEqual(len(my), 1)
        self.assertEqual(my[0]["name"], "Weight Loss")
        self.assertEqual(my[0]["members"], [{"username": "alice", "is_owner": True, "share": "both"}])
        self.assertEqual(my[0]["owner"], "alice")
        self.assertTrue(my[0]["user_is_owner"])

        ok, key = webapp.join_group("Weight Loss", "abc123", "bob")
        self.assertTrue(ok)
        self.assertEqual(key, "group_joined")
        self.assertEqual(self.member_names(webapp.all_groups()[0]["id"]), ["alice", "bob"])
        self.assertEqual(webapp.all_groups()[0]["member_count"], 2)
        self.assertFalse(webapp.my_groups("bob")[0]["user_is_owner"])

    def test_wrong_code_or_name(self):
        self.add_user("alice")
        webapp.create_group("Weight Loss", "abc123", "alice")
        self.assertEqual(webapp.join_group("Weight Loss", "nope", "alice")[1],
                         "wrong_access_code")
        self.assertEqual(webapp.join_group("Nope", "abc123", "alice")[1],
                         "wrong_access_code")

    def test_create_without_member(self):
        ok, key = webapp.create_group("Admin Group", "code1", None)
        self.assertTrue(ok)
        self.assertEqual(key, "group_created")
        group = webapp.all_groups()[0]
        self.assertEqual(group["name"], "Admin Group")
        self.assertEqual(group["owner"], webapp.ADMIN_USER)
        self.assertEqual(group["members"], [])
        self.assertEqual(group["member_count"], 0)
        self.assertTrue(group["is_public"])  # admin-created groups are public

    def test_delete_group_only_by_owner_or_admin(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_group("A", "1", "alice")
        webapp.join_group("A", "1", "bob")
        lid = webapp.all_groups()[0]["id"]
        self.assertEqual(webapp.delete_group(lid, "bob")[1], "not_allowed")
        ok, key = webapp.delete_group(lid, "alice")
        self.assertTrue(ok)
        self.assertEqual(key, "group_removed")
        self.assertEqual(webapp.all_groups(), [])
        # admin cannot delete a private (user-created) group
        webapp.create_group("A", "1", "alice")
        self.assertEqual(
            webapp.delete_group(webapp.all_groups()[0]["id"], webapp.ADMIN_USER)[0], False
        )
        # admin can delete its own public group
        webapp.create_group("Admin A", "ignored", None)
        admin_lid = [g for g in webapp.all_groups() if g["name"] == "Admin A"][0]["id"]
        self.assertEqual(webapp.delete_group(admin_lid, webapp.ADMIN_USER)[0], True)

    def test_delete_renumbers_ids_and_memberships(self):
        self.add_user("alice")
        webapp.create_group("A", "1", "alice")
        webapp.create_group("B", "2", None)
        webapp.create_group("C", "3", None)
        self.assertEqual([g["id"] for g in webapp.all_groups()], [1, 2, 3])
        webapp.delete_group(2, webapp.ADMIN_USER)
        groups = webapp.all_groups()
        self.assertEqual([g["id"] for g in groups], [1, 2])
        self.assertEqual([g["name"] for g in groups], ["A", "C"])
        webapp.create_group("D", "4", None)
        self.assertEqual([g["id"] for g in webapp.all_groups()], [1, 2, 3])

    def test_duplicate_name_and_already_member(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_group("A", "1", "alice")
        self.assertEqual(webapp.create_group("A", "2", "bob")[0], False)
        self.assertEqual(webapp.join_group("A", "1", "alice")[1], "already_member")

    def test_leave_group_recomputes_ranks(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_group("A", "1", "alice")
        webapp.join_group("A", "1", "bob")
        today = date.today()
        entry = {"name": "Salad", "meal": "lunch", "calories": 100, "amount": None, "extras": {}}
        data = webapp.load_user_data("bob")
        data["days"][today.isoformat()] = [entry]
        webapp.save_user_data("bob", data)

        group = webapp.all_groups()[0]
        names = self.member_names(group["id"])
        self.assertEqual([r[0] for r in webapp.rank_users(names)], ["bob", "alice"])
        ok, key = webapp.leave_group(group["id"], "bob")
        self.assertTrue(ok)
        self.assertEqual(key, "group_left")
        group = webapp.all_groups()[0]
        self.assertEqual(self.member_names(group["id"]), ["alice"])
        self.assertEqual([r[0] for r in webapp.rank_users(self.member_names(group["id"]))], ["alice"])
        self.assertEqual(webapp.my_groups("bob"), [])

    def test_kick_requires_owner(self):
        self.add_user("alice")
        self.add_user("bob")
        self.add_user("carol")
        webapp.create_group("A", "1", "alice")
        webapp.join_group("A", "1", "bob")
        webapp.join_group("A", "1", "carol")
        lid = webapp.all_groups()[0]["id"]
        self.assertEqual(webapp.kick_member(lid, "carol", "bob")[1], "not_allowed")
        ok, key = webapp.kick_member(lid, "carol", "alice")
        self.assertTrue(ok)
        self.assertEqual(key, "member_kicked")
        self.assertEqual(self.member_names(lid), ["alice", "bob"])
        self.assertEqual(webapp.my_groups("carol"), [])

    def test_promote_and_demote_owner(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_group("A", "1", "alice")
        webapp.join_group("A", "1", "bob")
        lid = webapp.all_groups()[0]["id"]

        self.assertEqual(webapp.promote_owner(lid, "bob", "bob")[1], "not_allowed")
        ok, key = webapp.promote_owner(lid, "bob", "alice")
        self.assertTrue(ok)
        self.assertEqual(key, "owner_promoted")
        self.assertTrue(webapp.is_group_owner(lid, "bob"))
        self.assertTrue(webapp.my_groups("bob")[0]["user_is_owner"])

        self.assertEqual(webapp.demote_owner(lid, "alice", "alice")[1], "not_allowed")
        ok, key = webapp.demote_owner(lid, "bob", "alice")
        self.assertTrue(ok)
        self.assertEqual(key, "owner_demoted")
        self.assertFalse(webapp.is_group_owner(lid, "bob"))
        self.assertFalse(webapp.my_groups("bob")[0]["user_is_owner"])

        self.assertEqual(webapp.promote_owner(lid, "ghost", "alice")[1], "not_a_member")
        self.assertEqual(webapp.demote_owner(lid, "bob", "alice")[1], "not_a_member")

    def test_owner_can_manage_group(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_group("A", "1", "alice")
        webapp.join_group("A", "1", "bob")
        lid = webapp.all_groups()[0]["id"]
        # non-owner cannot rename / change code
        self.assertEqual(webapp.rename_group(lid, "B", "bob")[1], "not_allowed")
        self.assertEqual(webapp.change_access_code(lid, "9", "bob")[1], "not_allowed")
        # owner can
        ok, key = webapp.rename_group(lid, "B", "alice")
        self.assertTrue(ok)
        self.assertEqual(key, "group_renamed")
        ok, key = webapp.change_access_code(lid, "9", "alice")
        self.assertTrue(ok)
        self.assertEqual(key, "code_changed")
        group = webapp.all_groups()[0]
        self.assertEqual(group["name"], "B")
        self.assertEqual(group["access_code"], "9")
        # duplicate name rejected
        webapp.create_group("New", "3", "alice")
        self.assertEqual(webapp.rename_group(webapp.all_groups()[0]["id"], "New", "alice")[0], False)
        # empty code rejected
        self.assertEqual(webapp.change_access_code(lid, "   ", "alice")[1], "code_empty")

    def test_private_group_requires_code(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_group("A", "1", "alice")
        self.assertFalse(webapp.all_groups()[0]["is_public"])
        self.assertEqual(webapp.join_group("A", "nope", "bob")[1], "wrong_access_code")
        self.assertEqual(webapp.join_group("A", "", "bob")[1], "wrong_access_code")
        ok, key = webapp.join_group("A", "1", "bob")
        self.assertTrue(ok)
        self.assertEqual(key, "group_joined")

    def test_public_group_joins_without_code(self):
        self.add_user("alice")
        self.add_user("bob")
        self.add_user("carol")
        webapp.create_group("Open", "irrelevant", "alice", is_public=True)
        self.assertTrue(webapp.all_groups()[0]["is_public"])
        ok, key = webapp.join_group("Open", "", "bob")
        self.assertTrue(ok)
        self.assertEqual(key, "group_joined")
        ok, key = webapp.join_group("Open", "wrong", "carol")
        self.assertTrue(ok)
        self.assertEqual(key, "group_joined")

    def test_admin_created_group_is_public_and_code_free(self):
        self.add_user("alice")
        webapp.create_group("Staff", "secret", None)
        g = webapp.all_groups()[0]
        self.assertTrue(g["is_public"])
        ok, key = webapp.join_group("Staff", "", "alice")
        self.assertTrue(ok)
        self.assertEqual(key, "group_joined")

    def test_admin_cannot_access_private_groups(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_group("Secret", "1", "alice")
        webapp.join_group("Secret", "1", "bob")
        lid = webapp.all_groups()[0]["id"]
        self.assertFalse(webapp.can_manage_group(lid, webapp.ADMIN_USER))
        self.assertEqual(webapp.kick_member(lid, "bob", webapp.ADMIN_USER)[1], "not_allowed")
        self.assertEqual(webapp.rename_group(lid, "X", webapp.ADMIN_USER)[1], "not_allowed")
        self.assertEqual(webapp.change_access_code(lid, "2", webapp.ADMIN_USER)[1], "not_allowed")
        self.assertEqual(webapp.delete_group(lid, webapp.ADMIN_USER)[1], "not_allowed")

    def test_admin_manages_only_own_groups_members(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_group("User Group", "1", "alice")
        webapp.join_group("User Group", "1", "bob")
        user_group = webapp.all_groups()[0]
        self.assertEqual(user_group["owner"], "alice")
        self.assertTrue(any(m["username"] == "bob" and not m["is_owner"] for m in user_group["members"]))
        # admin cannot kick in a user-created group
        self.assertEqual(webapp.kick_member(user_group["id"], "bob", webapp.ADMIN_USER)[1], "not_allowed")
        # admin creates a group -> can kick there
        webapp.create_group("Admin Group", "2", None)
        admin_group = [g for g in webapp.all_groups() if g["name"] == "Admin Group"][0]
        webapp.join_group("Admin Group", "2", "bob")
        ok, key = webapp.kick_member(admin_group["id"], "bob", webapp.ADMIN_USER)
        self.assertTrue(ok)
        self.assertEqual(key, "member_kicked")

    def test_rename_user(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_group("A", "1", "alice")
        webapp.join_group("A", "1", "bob")

        ok, key = webapp.rename_user("alice", "alice2")
        self.assertTrue(ok)
        self.assertEqual(key, "username_changed")
        self.assertIn("alice2", webapp.all_usernames())
        self.assertNotIn("alice", webapp.all_usernames())
        group = webapp.all_groups()[0]
        self.assertIn("alice2", self.member_names(group["id"]))
        self.assertIn("bob", self.member_names(group["id"]))
        self.assertEqual(group["owner"], "alice2")

        self.assertEqual(webapp.rename_user("ghost", "x")[1], "user_not_found")
        self.assertEqual(webapp.rename_user("alice2", "bob")[1], "username_exists")
        self.assertEqual(webapp.rename_user("bob", "   ")[1], "username_empty")

    def test_rename_to_same_is_noop(self):
        self.add_user("alice")
        ok, _ = webapp.rename_user("alice", "alice")
        self.assertTrue(ok)

    def test_join_share_permission(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_group("A", "1", "alice")
        webapp.join_group("A", "1", "bob", "budget")
        members = {m["username"]: m["share"] for m in webapp.group_members(1)}
        self.assertEqual(members["alice"], "both")  # owner always shares
        self.assertEqual(members["bob"], "budget")
        self.assertTrue(webapp.granted_share("budget", "budget"))
        self.assertFalse(webapp.granted_share("budget", "diet"))
        self.assertTrue(webapp.granted_share("both", "diet"))
        self.assertTrue(webapp.granted_share("both", "budget"))
        self.assertTrue(webapp.granted_share("diet", "diet"))

    def test_set_member_share_and_invalid_default(self):
        self.add_user("alice")
        self.add_user("bob")
        webapp.create_group("A", "1", "alice")
        webapp.join_group("A", "1", "bob", "diet")
        self.assertEqual(webapp.member_share(1, "bob"), "diet")
        self.assertTrue(webapp.set_member_share(1, "bob", "both"))
        self.assertEqual(webapp.member_share(1, "bob"), "both")
        self.assertFalse(webapp.set_member_share(1, "ghost", "diet"))
        self.add_user("carol")
        webapp.join_group("A", "1", "carol", "bogus")
        self.assertEqual(webapp.member_share(1, "carol"), "both")

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
    """Admin sees account management + their own groups only: no diet/budget
    data, no user group forms, no joining, no member records."""

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

    def test_admin_has_no_user_group_forms(self):
        keys = {t.key for t in self.at.text_input}
        self.assertFalse(keys & {"grp_name", "grp_code", "jg_name", "jg_code"})

    def test_admin_has_admin_panels(self):
        labels = [e.label for e in self.at.expander]
        self.assertTrue(any("Admin panel" in l for l in labels))
        self.assertTrue(any("Groups" in l for l in labels))

    def test_admin_sees_user_manual(self):
        labels = [e.label for e in self.at.expander]
        self.assertTrue(any("User manual" in l for l in labels))

    def test_admin_can_create_manage_but_not_join(self):
        self.at.run(timeout=60)
        keys = {t.key for t in self.at.text_input}
        self.assertIn("ag_name", keys)
        self.assertNotIn("ag_code", keys)  # admin groups are public: name only
        self.assertTrue(any("Create group" in b.label for b in self.at.button))
        self.assertFalse(keys & {"grp_name", "grp_code", "jg_name", "jg_code"})

    def test_admin_can_kick_member_of_own_group(self):
        salt = os.urandom(16).hex()
        with webapp.get_db() as conn:
            conn.execute("INSERT INTO users (username, salt, hash) VALUES (?,?,?)",
                         ("bob", salt, webapp.hash_password("pw", salt)))
        webapp.create_group("Team", "x", None)
        webapp.join_group("Team", "x", "bob")
        self.at.run(timeout=60)
        kick_sel = [s for s in self.at.selectbox if s.key == "adm_gkick_sel_1"][0]
        self.assertEqual(kick_sel.options, ["bob"])
        kick_sel.set_value("bob")
        [b for b in self.at.button if b.key == "adm_gkick_btn_1"][0].click()
        self.at.run(timeout=60)
        self.assertTrue(any("Remove bob from this group" in w.value for w in self.at.warning))
        [b for b in self.at.button if b.key == "adm_gkick_yes_1"][0].click()
        self.at.run(timeout=60)
        self.assertEqual(webapp.all_groups()[0]["members"], [])

    def test_admin_cannot_kick_in_user_group(self):
        salt = os.urandom(16).hex()
        with webapp.get_db() as conn:
            conn.execute("INSERT INTO users (username, salt, hash) VALUES (?,?,?)",
                         ("bob", salt, webapp.hash_password("pw", salt)))
        webapp.create_group("Team", "x", "bob")
        self.at.run(timeout=60)
        # private user groups are not shown or manageable by the admin at all
        self.assertEqual([s for s in self.at.selectbox if s.key == "adm_gkick_sel_1"], [])
        self.assertFalse(any("—" in m.value for m in self.at.markdown))
        self.assertFalse(any("Remove group" in b.label for b in self.at.button))

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
        self.assertTrue({"grp_name", "grp_code"} <= keys)
        self.assertTrue(any("Add item" in b.label for b in at.button))
        self.assertFalse(any("Admin panel" in e.label for e in at.expander))


class TestGroupUI(unittest.TestCase):
    """User groups: dropdown options, add/join forms, owner management, leave."""

    DB = os.path.join(os.path.dirname(os.path.abspath(webapp.__file__)), "streamlit_data.db")

    def setUp(self):
        webapp.DB_PATH = self.DB
        if os.path.exists(self.DB):
            os.remove(self.DB)
        webapp.init_db()
        webapp.ensure_admin()
        self.add_user("bob")
        self.add_user("alice")
        self.at = AppTest.from_file(APP_PATH)
        self.at.run(timeout=60)
        self.at.session_state["user"] = "bob"
        self.at.session_state["data"] = webapp.default_data()
        self.at.run(timeout=60)

    def tearDown(self):
        if os.path.exists(self.DB):
            os.remove(self.DB)

    def add_user(self, name):
        salt = os.urandom(16).hex()
        with webapp.get_db() as conn:
            conn.execute("INSERT INTO users (username, salt, hash) VALUES (?,?,?)",
                         (name, salt, webapp.hash_password("pw", salt)))

    def select_group(self, label_fragment):
        dd = [s for s in self.at.selectbox if s.key == "grp_dd"][0]
        opt = [o for o in dd.options if label_fragment in o][0]
        dd.set_value(opt)
        self.at.run(timeout=60)

    def test_dropdown_contains_add_join_and_joined_groups(self):
        webapp.create_group("Team A", "x", "bob")
        self.at.run(timeout=60)
        dd = [s for s in self.at.selectbox if s.key == "grp_dd"][0]
        self.assertTrue(any(o.startswith("➕") and "Add" in o for o in dd.options))
        self.assertTrue(any(o.startswith("➕") and "Join" in o for o in dd.options))
        self.assertTrue(any("Team A" in o for o in dd.options))

    def test_default_is_add_form_when_no_groups(self):
        dd = [s for s in self.at.selectbox if s.key == "grp_dd"][0]
        self.assertEqual(dd.index, 0)
        keys = {t.key for t in self.at.text_input}
        self.assertIn("grp_name", keys)

    def test_user_manual_present(self):
        labels = [e.label for e in self.at.expander]
        self.assertTrue(any("User manual" in l for l in labels))

    def test_join_action_shows_join_form(self):
        webapp.create_group("Team A", "x", None)
        self.at.run(timeout=60)
        dd = [s for s in self.at.selectbox if s.key == "grp_dd"][0]
        join_opt = [o for o in dd.options if "Join" in o][0]
        dd.set_value(join_opt)
        self.at.run(timeout=60)
        keys = {t.key for t in self.at.text_input}
        self.assertIn("jg_name", keys)
        self.assertIn("jg_code", keys)

    def test_selecting_group_shows_rank_table(self):
        webapp.create_group("Team A", "x", "bob")
        self.at.run(timeout=60)
        self.select_group("Team A")
        self.assertGreaterEqual(len(self.at.table), 1)
        self.assertIn("bob", str(self.at.table[0].value))

    def test_owner_sees_management_and_member_records(self):
        webapp.create_group("Team A", "x", "bob")
        webapp.join_group("Team A", "x", "alice")
        self.at.run(timeout=60)
        self.select_group("Team A")
        keys = {b.key for b in self.at.button}
        self.assertIn("g_promote_1_alice", keys)
        self.assertIn("g_kick_1_alice", keys)
        self.assertIn("g_del_btn_1", keys)
        sel = [s for s in self.at.selectbox if s.key == "grp_rec_sel_1"][0]
        self.assertEqual(sel.options, ["alice", "bob"])
        self.assertNotIn("g_leave_1", keys)

    def test_owner_promote_and_demote(self):
        webapp.create_group("Team A", "x", "bob")
        webapp.join_group("Team A", "x", "alice")
        self.at.run(timeout=60)
        self.select_group("Team A")
        [b for b in self.at.button if b.key == "g_promote_1_alice"][0].click()
        self.at.run(timeout=60)
        self.assertTrue(webapp.is_group_owner(1, "alice"))
        [b for b in self.at.button if b.key == "g_demote_1_alice"][0].click()
        self.at.run(timeout=60)
        self.assertFalse(webapp.is_group_owner(1, "alice"))

    def test_owner_kick_flow(self):
        webapp.create_group("Team A", "x", "bob")
        webapp.join_group("Team A", "x", "alice")
        self.at.run(timeout=60)
        self.select_group("Team A")
        [b for b in self.at.button if b.key == "g_kick_1_alice"][0].click()
        self.at.run(timeout=60)
        self.assertTrue(any("Remove alice from this group" in w.value for w in self.at.warning))
        [b for b in self.at.button if b.key == "g_kick_yes_1_alice"][0].click()
        self.at.run(timeout=60)
        self.assertEqual(webapp.my_groups("alice"), [])
        self.assertEqual(len(webapp.my_groups("bob")[0]["members"]), 1)

    def test_non_owner_only_leaves(self):
        webapp.create_group("Team A", "x", "alice")
        webapp.join_group("Team A", "x", "bob")
        self.at.run(timeout=60)
        self.select_group("Team A")
        keys = {b.key for b in self.at.button}
        self.assertIn("g_leave_1", keys)
        self.assertNotIn("g_promote_1_alice", keys)
        self.assertNotIn("g_del_btn_1", keys)

    def test_leave_group_flow(self):
        webapp.create_group("Team A", "x", "alice")
        webapp.join_group("Team A", "x", "bob")
        self.at.run(timeout=60)
        self.select_group("Team A")
        [b for b in self.at.button if b.key == "g_leave_1"][0].click()
        self.at.run(timeout=60)
        self.assertTrue(any("Leave this group" in w.value for w in self.at.warning))
        [b for b in self.at.button if b.key == "g_leave_yes_1"][0].click()
        self.at.run(timeout=60)
        self.assertEqual(webapp.my_groups("bob"), [])
        dd = [s for s in self.at.selectbox if s.key == "grp_dd"][0]
        self.assertFalse(any("Team A" in o for o in dd.options))
        self.assertEqual(dd.index, 0)

    def test_owner_member_view_default_shares_both(self):
        webapp.create_group("Team A", "x", "bob")
        webapp.join_group("Team A", "x", "alice")
        data = webapp.default_data()
        today = date.today()
        data["days"][today.isoformat()] = [diet_entry(150)]
        data["spends"][today.isoformat()] = [spend_entry(25)]
        webapp.save_user_data("alice", data)
        self.at.run(timeout=60)
        self.select_group("Team A")
        sel = [s for s in self.at.selectbox if s.key == "grp_rec_sel_1"][0]
        sel.set_value("alice")
        self.at.run(timeout=60)
        self.assertFalse(any("Permission not granted" in i.value for i in self.at.info))
        table_text = " | ".join(str(t.value) for t in self.at.table)
        self.assertIn("150 kcal", table_text)
        self.assertIn("lunch", table_text)
        self.assertIn("25 HKD", table_text)

    def test_owner_member_view_gates_budget_only(self):
        webapp.create_group("Team A", "x", "bob")
        webapp.join_group("Team A", "x", "alice", "budget")
        data = webapp.default_data()
        today = date.today()
        data["days"][today.isoformat()] = [diet_entry(150)]
        data["spends"][today.isoformat()] = [spend_entry(25)]
        webapp.save_user_data("alice", data)
        self.at.run(timeout=60)
        self.select_group("Team A")
        sel = [s for s in self.at.selectbox if s.key == "grp_rec_sel_1"][0]
        sel.set_value("alice")
        self.at.run(timeout=60)
        self.assertGreaterEqual(
            sum(1 for i in self.at.info if "Permission not granted" in i.value), 1)
        table_text = " | ".join(str(t.value) for t in self.at.table)
        self.assertIn("lunch", table_text)
        self.assertNotIn("150 kcal", table_text)

    def test_owner_member_view_gates_diet_only(self):
        webapp.create_group("Team A", "x", "bob")
        webapp.join_group("Team A", "x", "alice", "diet")
        data = webapp.default_data()
        today = date.today()
        data["days"][today.isoformat()] = [diet_entry(150)]
        data["spends"][today.isoformat()] = [spend_entry(25)]
        webapp.save_user_data("alice", data)
        self.at.run(timeout=60)
        self.select_group("Team A")
        sel = [s for s in self.at.selectbox if s.key == "grp_rec_sel_1"][0]
        sel.set_value("alice")
        self.at.run(timeout=60)
        self.assertGreaterEqual(
            sum(1 for i in self.at.info if "Permission not granted" in i.value), 1)
        table_text = " | ".join(str(t.value) for t in self.at.table)
        self.assertIn("150 kcal", table_text)
        self.assertNotIn("lunch", table_text)

    def test_create_public_group_skips_code(self):
        radio = [r for r in self.at.radio if r.key == "grp_type"][0]
        radio.set_value("Public")
        self.at.run(timeout=60)
        keys = {t.key for t in self.at.text_input}
        self.assertNotIn("grp_code", keys)
        self.at.text_input(key="grp_name").set_value("Open Group")
        [b for b in self.at.button if b.label.strip() == "Create group"][0].click()
        self.at.run(timeout=60)
        groups = webapp.my_groups("bob")
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["name"], "Open Group")
        self.assertTrue(groups[0]["is_public"])

    def test_join_public_group_without_code(self):
        webapp.create_group("Open Team", "x", None)
        self.at.run(timeout=60)
        dd = [s for s in self.at.selectbox if s.key == "grp_dd"][0]
        join_opt = [o for o in dd.options if "Join" in o][0]
        dd.set_value(join_opt)
        self.at.run(timeout=60)
        self.at.text_input(key="jg_name").set_value("Open Team")
        self.at.text_input(key="jg_code").set_value("")
        [b for b in self.at.button if b.label.strip() == "Join group"][0].click()
        self.at.run(timeout=60)
        members = webapp.my_groups("bob")[0]["members"]
        self.assertTrue(any(m["username"] == "bob" and not m["is_owner"] for m in members))


def diet_entry(calories=100, name="Salad"):
    return {"name": name, "meal": "lunch", "calories": calories, "amount": None, "extras": {}}


def spend_entry(price=50):
    return {"name": "lunch", "category": "Food", "price": price}


class _NoPRAGMAConn:
    """Wraps a sqlite connection but refuses PRAGMA, mimicking remote drivers."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, *args):
        if sql.strip().upper().startswith("PRAGMA"):
            raise RuntimeError("PRAGMA not supported")
        return self._conn.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._conn, name)


class TestDatabaseBackend(unittest.TestCase):
    """Local sqlite stays the default; Turso config is picked up from the
    environment; schema migration is portable across drivers."""

    def test_default_backend_is_local_sqlite(self):
        conn = webapp.get_db()
        self.assertIsInstance(conn, sqlite3.Connection)
        conn.close()

    def test_remote_config_read_from_env(self):
        old = {k: os.environ.get(k) for k in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")}
        try:
            os.environ["TURSO_DATABASE_URL"] = "libsql://test.example"
            os.environ["TURSO_AUTH_TOKEN"] = "tok"
            self.assertEqual(
                webapp.remote_db_config(), ("libsql://test.example", "tok"))
        finally:
            for key, val in old.items():
                if val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = val

    def _tmp_db(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        return path

    def test_add_column_idempotent(self):
        path = self._tmp_db()
        try:
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE t (a TEXT)")
            webapp._add_column(conn, "t", "b", "TEXT DEFAULT 'x'")
            webapp._add_column(conn, "t", "b", "TEXT DEFAULT 'x'")  # no-op
            cols = [r[1] for r in conn.execute("PRAGMA table_info(t)").fetchall()]
            self.assertEqual(cols, ["a", "b"])
            conn.close()
        finally:
            os.remove(path)

    def test_add_column_without_pragma_support(self):
        path = self._tmp_db()
        try:
            inner = sqlite3.connect(path)
            inner.execute("CREATE TABLE t (a TEXT)")
            inner.execute("INSERT INTO t VALUES ('v')")
            inner.commit()
            outer = _NoPRAGMAConn(inner)  # introspection must not be required
            webapp._add_column(outer, "t", "b", "TEXT DEFAULT 'x'")
            cols = [r[1] for r in inner.execute("PRAGMA table_info(t)").fetchall()]
            self.assertIn("b", cols)
            self.assertEqual(inner.execute("SELECT a, b FROM t").fetchone(), ("v", "x"))
            inner.close()
        finally:
            os.remove(path)


class TestStorageLimit(unittest.TestCase):
    """Only 30 days of diet/budget data may be stored; new days are blocked
    until old data is removed."""

    def test_count_and_full(self):
        data = webapp.default_data()
        start = date(2026, 5, 1)
        for i in range(webapp.MAX_DAYS - 1):
            data["days"][(start + timedelta(days=i)).isoformat()] = [diet_entry()]
        self.assertEqual(webapp.stored_day_count(data), webapp.MAX_DAYS - 1)
        self.assertFalse(webapp.storage_full(data))
        data["spends"][(start + timedelta(days=webapp.MAX_DAYS - 1)).isoformat()] = [spend_entry()]
        self.assertEqual(webapp.stored_day_count(data), webapp.MAX_DAYS)
        self.assertTrue(webapp.storage_full(data))

    def test_blocker_only_covers_new_days(self):
        data = webapp.default_data()
        start = date(2026, 5, 1)
        for i in range(webapp.MAX_DAYS):
            data["days"][(start + timedelta(days=i)).isoformat()] = [diet_entry()]
        self.assertFalse(webapp.storage_blocker(data, start))
        self.assertTrue(
            webapp.storage_blocker(data, start + timedelta(days=webapp.MAX_DAYS)))
        self.assertFalse(webapp.storage_blocker(data, start + timedelta(days=1)))

    def test_drop_oldest_day_removes_data(self):
        data = webapp.default_data()
        for i in range(5):
            d = date(2026, 5, 1) + timedelta(days=i)
            data["days"][d.isoformat()] = [diet_entry()]
            data["spends"][d.isoformat()] = [spend_entry()]
        iso = date(2026, 5, 1).isoformat()
        self.assertTrue(webapp.drop_oldest_day(data))
        self.assertEqual(webapp.stored_day_count(data), 4)
        self.assertNotIn(iso, data["days"])
        self.assertNotIn(iso, data["spends"])
        self.assertIn("streak_carry", data)
        self.assertIn("budget_carry", data)
        self.assertFalse(webapp.drop_oldest_day(webapp.default_data()))


class TestStreakCarry(unittest.TestCase):
    """Deleting old days must bank streaks so they keep building seamlessly."""

    START = date(2026, 5, 4)  # a Monday, so completed weeks align cleanly

    def build(self, days, over_days=(), calories=100):
        data = webapp.default_data()
        for i in range(days):
            c = 10_000 if i in over_days else calories
            data["days"][(self.START + timedelta(days=i)).isoformat()] = [diet_entry(c)]
        return data

    def stream(self, data, steps):
        """Log `steps` more days, dropping the oldest each day (as the storage
        cap would)."""
        ref = date.fromisoformat(max(data["days"]))
        for _ in range(steps):
            ref += timedelta(days=1)
            webapp.drop_oldest_day(data)
            data["days"][ref.isoformat()] = [diet_entry()]
        return ref

    def test_day_streak_builds_seamlessly(self):
        data = self.build(30)
        ref = self.START + timedelta(days=29)
        self.assertEqual(webapp.streaks_with_carry(data, ref)[0], 30)
        ref = self.stream(data, 40)
        self.assertEqual(webapp.stored_day_count(data), 30)
        self.assertEqual(webapp.streaks_with_carry(data, ref)[0], 70)

    def test_week_streak_builds_seamlessly(self):
        data = self.build(30)
        ref = self.START + timedelta(days=29)  # a Tuesday
        while ref.weekday() != 6:  # advance to a fully-logged Sunday
            ref = self.stream(data, 1)
        week = webapp.streaks_with_carry(data, ref)[1]
        self.assertGreaterEqual(week, 4)
        ref = self.stream(data, 4 * 7)
        self.assertEqual(webapp.streaks_with_carry(data, ref)[1], week + 4)

    def test_month_streak_builds_seamlessly(self):
        data = webapp.default_data()
        start = date(2025, 6, 1)
        end = date(2026, 3, 31)
        d = start
        while d <= end:
            data["days"][d.isoformat()] = [diet_entry()]
            if webapp.stored_day_count(data) > webapp.MAX_DAYS:
                webapp.drop_oldest_day(data)
            d += timedelta(days=1)
        self.assertEqual(webapp.streaks_with_carry(data, end)[2], 10)

    def test_missing_day_breaks_streak(self):
        data = self.build(40)
        last = date.fromisoformat(max(data["days"]))
        skip = last + timedelta(days=1)  # never logged
        ref = last + timedelta(days=2)
        webapp.drop_oldest_day(data)
        webapp.drop_oldest_day(data)
        webapp.drop_oldest_day(data)
        data["days"][ref.isoformat()] = [diet_entry()]
        self.assertNotIn(skip.isoformat(), data["days"])
        self.assertEqual(webapp.streaks_with_carry(data, ref)[0], 1)

    def test_over_limit_dropped_day_breaks_streak(self):
        data = self.build(60, over_days=(30,))
        ref = self.stream(data, 35)
        # days past the last over-limit day (offset 31..59) + the 35 streamed
        self.assertEqual(webapp.streaks_with_carry(data, ref)[0], 29 + 35)

    def test_compute_streaks_carry_needs_unbroken_run(self):
        data = self.build(30)
        days = webapp.build_all_days(data)
        cats = webapp.diet_categories(data)
        ref = max(days)
        self.assertEqual(core.compute_streaks(days, cats, ref, {"day": 10})[0], 40)
        mid = ref - timedelta(days=3)
        data["days"].pop(mid.isoformat())
        days2 = webapp.build_all_days(data)
        self.assertEqual(core.compute_streaks(days2, cats, ref, {"day": 10})[0], 3)

    def test_budget_day_streak_builds_seamlessly(self):
        data = webapp.default_data()
        data["budget_period"] = "day"
        data["budget_limit"] = 1000
        for i in range(30):
            data["spends"][(self.START + timedelta(days=i)).isoformat()] = [spend_entry()]
        ref = self.START + timedelta(days=29)
        self.assertEqual(webapp.budget_streaks_with_carry(data, ref)["day"], 30)
        for _ in range(20):
            ref += timedelta(days=1)
            webapp.drop_oldest_day(data)
            data["spends"][ref.isoformat()] = [spend_entry()]
        self.assertEqual(webapp.budget_streaks_with_carry(data, ref)["day"], 50)

    def test_budget_gap_breaks_streak(self):
        data = webapp.default_data()
        data["budget_period"] = "day"
        data["budget_limit"] = 1000
        for i in range(30):
            data["spends"][(self.START + timedelta(days=i)).isoformat()] = [spend_entry()]
        ref = self.START + timedelta(days=29) + timedelta(days=1)
        webapp.drop_oldest_day(data)
        webapp.drop_oldest_day(data)
        ref = ref + timedelta(days=1)  # one empty day
        data["spends"][ref.isoformat()] = [spend_entry()]
        self.assertEqual(webapp.budget_streaks_with_carry(data, ref)["day"], 1)


class TestStorageUI(unittest.TestCase):
    """The 30-day cap shows a prompt and lets the user free a slot by deleting
    the oldest day, without losing their streak."""

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

    def tearDown(self):
        if os.path.exists(self.DB):
            os.remove(self.DB)

    def boot(self, data):
        webapp.save_user_data("bob", data)
        at = AppTest.from_file(APP_PATH)
        at.run(timeout=60)
        at.session_state["user"] = "bob"
        at.session_state["data"] = webapp.load_user_data("bob")
        at.run(timeout=60)
        return at

    def test_new_day_blocked_until_old_day_deleted(self):
        data = webapp.default_data()
        today = date.today()
        for i in range(1, webapp.MAX_DAYS + 1):
            data["days"][(today - timedelta(days=i)).isoformat()] = [diet_entry()]
        at = self.boot(data)
        add_btn = [b for b in at.button if b.key == f"diet_go_add_{today.isoformat()}"][0]
        add_btn.click()
        at.run(timeout=60)
        self.assertTrue(any("Storage full" in w.value for w in at.warning))
        self.assertFalse(any(k.startswith("fd_") for k in {t.key for t in at.text_input if t.key}))
        self.assertTrue(any("Delete oldest day" in b.label for b in at.button))
        at.number_input(key="st_del_n").set_value(1)
        [b for b in at.button if b.key == "st_del_btn"][0].click()
        at.run(timeout=60)
        [b for b in at.button if b.key == "st_del_yes"][0].click()
        at.run(timeout=60)
        data2 = webapp.load_user_data("bob")
        self.assertEqual(webapp.stored_day_count(data2), webapp.MAX_DAYS - 1)
        self.assertTrue(any(k.startswith("fd_") for k in {t.key for t in at.text_input if t.key}))
        self.assertGreaterEqual(webapp.streaks_with_carry(data2, today - timedelta(days=1))[0],
                                webapp.MAX_DAYS - 1)

    def test_existing_day_still_editable_when_full(self):
        data = webapp.default_data()
        today = date.today()
        for i in range(webapp.MAX_DAYS):
            data["days"][(today - timedelta(days=i)).isoformat()] = [diet_entry()]
        at = self.boot(data)
        add_btn = [b for b in at.button if b.key == f"diet_go_add_{today.isoformat()}"][0]
        add_btn.click()
        at.run(timeout=60)
        self.assertFalse(any("Storage full" in w.value for w in at.warning))
        self.assertTrue(any(k.startswith("fd_") for k in {t.key for t in at.text_input if t.key}))


class TestTranslationCoverage(unittest.TestCase):
    """Every tr(...) key used in app.py must exist in both languages."""

    def test_all_tr_keys_covered_in_both_langs(self):
        with open(APP_PATH, encoding="utf-8") as f:
            src = f.read()
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