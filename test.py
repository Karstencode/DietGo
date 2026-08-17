import calendar
import os
import tempfile
import unittest
from datetime import date, timedelta
from main import (
    Value, FoodEntry, DietDay, SpendingEntry, CategoryLimit,
    compute_streaks, compute_budget_streaks, categories_satisfied, diet_rank, diet_score,
)

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


if __name__ == "__main__":
    unittest.main()