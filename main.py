import calendar
import json
import os
from datetime import date, timedelta

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    tk = ttk = messagebox = None

MEALS = ("breakfast", "lunch", "dinner", "other")
CATEGORIES = ("Food", "Transport", "Entertainment", "Utilities", "Clothing", "Other")
PERIODS = ("day", "week", "month")
UNITS = ("g", "ml", "portions", "servings", "pieces", "kcal")
LANGS = ("en", "zh")
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")

STRINGS = {
    "en": {
        "app_title": "Diet & Budget Diary",
        "language": "Language",
        "diet": "Diet",
        "budget": "Budget",
        "create": "Create",
        "edit": "Edit",
        "remove": "Remove",
        "save": "Save",
        "cancel": "Cancel",
        "add": "Add",
        "set": "Set",
        "calorie_limit": "Calorie limit",
        "daily_limit": "Daily limit",
        "category_limits": "Category limits",
        "add_category": "Add category",
        "edit_category": "Edit category",
        "remove_category": "Remove category",
        "category_name": "Category name",
        "unit": "Unit",
        "food_name": "Food name",
        "meal_type": "Meal type",
        "calories": "Calories (kcal)",
        "amount": "Amount",
        "spending_name": "Spending name",
        "category": "Category",
        "budget_cat_food": "Food",
        "budget_cat_transport": "Transport",
        "budget_cat_entertainment": "Entertainment",
        "budget_cat_utilities": "Utilities",
        "budget_cat_clothing": "Clothing",
        "budget_cat_other": "Other",
        "diet_budget_legend": "left = diet, right = budget",
        "price": "Price (HKD)",
        "limit_hkd": "Limit (HKD)",
        "period": "Limit period",
        "day": "Day",
        "week": "Week",
        "month": "Month",
        "total": "total",
        "day_total": "Day total",
        "over_limit": "(over limit!)",
        "within_limit": "(within limit)",
        "no_entries": "No entries for this day",
        "streaks": "Streaks",
        "food": "Food",
        "meal": "Meal",
        "spending": "Spending",
        "price_col": "Price",
        "breakfast": "Breakfast",
        "lunch": "Lunch",
        "dinner": "Dinner",
        "other": "Other",
        "adding_to": "Adding to: {}",
        "spending_on": "Spending on: {}",
        "username": "Username",
        "password": "Password",
        "sign_in": "Sign in",
        "sign_up": "Sign up",
        "sign_out": "Sign out",
        "signed_in_as": "Signed in as",
        "auth_caption": "Sign in or create an account. Your data is stored per account.",
        "username_empty": "Username cannot be empty.",
        "password_short": "Password must be at least 4 characters.",
        "username_exists": "Username already exists.",
        "user_not_found": "Username not found.",
        "wrong_password": "Incorrect password.",
        "account_created": "Account created.",
        "signed_in": "Signed in.",
        "delete_account": "Delete account",
        "confirm_username": "Type your username to confirm",
        "username_mismatch": "Username does not match.",
        "account_deleted": "Account deleted.",
        "new_password": "New password",
        "confirm_password": "Confirm password",
        "password_mismatch": "Passwords do not match.",
        "password_reset": "Password reset. You can now sign in.",
        "admin": "Administrator",
        "admin_panel": "Admin panel",
        "search_users": "Search users",
        "select_user": "Select user",
        "no_users_match": "No matching users.",
        "view_records": "Records",
        "add_account": "Add account",
        "reset_pw": "Reset password",
        "date": "Date",
        "add_new": "— add new —",
        "entry": "Entry",
        "remove_entry": "Remove entry",
        "select": "— select —",
        "name_empty": "Name cannot be empty.",
        "no_food": "No food logged for this day.",
        "no_spending": "No spending logged for this day.",
        "unit_g": "g",
        "unit_ml": "ml",
        "unit_portions": "portions",
        "unit_servings": "servings",
        "unit_pieces": "pieces",
        "unit_kcal": "kcal",
        "unit_mg": "mg",
        "confirm": "Confirm",
        "delete_warning": "This action is permanent and cannot be undone.",
        "current_categories": "Current categories:",
        "per_day": "per day",
        "update_calorie_limit": "Update calorie limit",
        "category_exists": "That category already exists.",
        "settings": "Budget settings",
        "save_settings": "Save settings",
        "err_invalid_number": "Invalid number.",
        "err_negative": "Value cannot be negative.",
        "err_already_exists": "That already exists.",
        "warn_select": "Please make a selection.",
        "warn_no_remove_calories": "The Calories category cannot be removed.",
        "err_invalid_calories": "Invalid calories.",
        "err_invalid_amount": "Invalid amount.",
        "err_invalid_price": "Invalid price.",
        "rank_label": "Diet rank: {0} (score {1})",
        "rank_none": "No streak",
        "rank_rookie": "Rookie",
        "rank_consistent": "Consistent",
        "rank_dedicated": "Dedicated",
        "rank_marathoner": "Marathoner",
        "rank_disciplined": "Disciplined",
        "rank_legend": "Legend",
        "leaderboard": "Leaderboard",
        "leaderboards": "Leaderboards",
        "create_leaderboard": "Create leaderboard",
        "join_leaderboard": "Join leaderboard",
        "add_leaderboard": "Add leaderboard",
        "leaderboard_name": "Leaderboard name",
        "access_code": "Access code",
        "leaderboard_created": "Leaderboard created.",
        "leaderboard_exists": "A leaderboard with this name already exists.",
        "leaderboard_joined": "Joined leaderboard.",
        "already_member": "You are already in this leaderboard.",
        "wrong_access_code": "Leaderboard not found or wrong access code.",
        "no_leaderboards": "You haven't joined any leaderboards yet.",
        "members": "Members",
        "change_name": "Change name",
        "change_code": "Change access code",
        "remove_leaderboard": "Remove leaderboard",
        "leaderboard_removed": "Leaderboard removed.",
        "all_leaderboards": "All leaderboards",
        "no_members_yet": "No members in this leaderboard yet.",
        "leave_leaderboard": "Leave leaderboard",
        "leaderboard_left": "You left the leaderboard.",
        "leave_confirm": "Leave this leaderboard? You can rejoin later with its access code.",
        "kick_member": "Kick member",
        "kick": "Kick",
        "member_kicked": "Member removed from leaderboard.",
        "kick_confirm": "Remove {name} from this leaderboard?",
        "new_username": "New username",
        "rename_user": "Rename user",
        "username_changed": "Username updated.",
        "cannot_rename_admin": "The admin account cannot be renamed.",
        "add_item": "Add item",
        "display_edit": "Display / edit",
        "back_to_list": "Back to list",
        "user": "User",
        "score": "Score",
        "rank_title": "Rank",
        "tier": "Tier",
        "no_users_yet": "No users yet.",
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "months": ["January", "February", "March", "April", "May", "June", "July",
                   "August", "September", "October", "November", "December"],
    },
    "zh": {
        "app_title": "飲食與預算日記",
        "language": "語言",
        "diet": "飲食",
        "budget": "預算",
        "create": "新增",
        "edit": "編輯",
        "remove": "刪除",
        "save": "儲存",
        "cancel": "取消",
        "add": "添加",
        "set": "設定",
        "calorie_limit": "卡路里限制",
        "daily_limit": "每日限制",
        "category_limits": "類別限制",
        "add_category": "新增類別",
        "edit_category": "編輯類別",
        "remove_category": "移除類別",
        "category_name": "類別名稱",
        "unit": "單位",
        "food_name": "食物名稱",
        "meal_type": "餐次",
        "calories": "卡路里（千卡）",
        "amount": "份量",
        "spending_name": "支出名稱",
        "category": "類別",
        "budget_cat_food": "食物",
        "budget_cat_transport": "交通",
        "budget_cat_entertainment": "娛樂",
        "budget_cat_utilities": "水電雜費",
        "budget_cat_clothing": "服飾",
        "budget_cat_other": "其他",
        "diet_budget_legend": "左＝飲食，右＝預算",
        "price": "價格（港元）",
        "limit_hkd": "限額（港元）",
        "period": "限額週期",
        "day": "日",
        "week": "週",
        "month": "月",
        "total": "總計",
        "day_total": "當日總計",
        "over_limit": "（超出限額！）",
        "within_limit": "（限額內）",
        "no_entries": "當天沒有記錄",
        "streaks": "連續記錄",
        "food": "食物",
        "meal": "餐次",
        "spending": "支出",
        "price_col": "價格",
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
        "other": "其他",
        "adding_to": "記錄日期：{}",
        "spending_on": "支出日期：{}",
        "username": "用戶名",
        "password": "密碼",
        "sign_in": "登入",
        "sign_up": "註冊",
        "sign_out": "登出",
        "signed_in_as": "已登入為",
        "auth_caption": "登入或建立帳戶。資料會按帳戶儲存。",
        "username_empty": "用戶名不能為空。",
        "password_short": "密碼至少需要4個字元。",
        "username_exists": "用戶名已存在。",
        "user_not_found": "用戶不存在。",
        "wrong_password": "密碼錯誤。",
        "account_created": "帳戶已建立。",
        "signed_in": "已登入。",
        "delete_account": "刪除帳戶",
        "confirm_username": "輸入用戶名以確認",
        "username_mismatch": "用戶名不匹配。",
        "account_deleted": "帳戶已刪除。",
        "new_password": "新密碼",
        "confirm_password": "確認密碼",
        "password_mismatch": "兩次輸入的密碼不一致。",
        "password_reset": "密碼已重設，請重新登入。",
        "admin": "管理員",
        "admin_panel": "管理員面板",
        "search_users": "搜尋用戶",
        "select_user": "選擇用戶",
        "no_users_match": "沒有符合的用戶。",
        "view_records": "記錄",
        "add_account": "新增帳戶",
        "reset_pw": "重設密碼",
        "date": "日期",
        "add_new": "— 新增 —",
        "entry": "記錄",
        "remove_entry": "刪除記錄",
        "select": "— 選擇 —",
        "name_empty": "名稱不能為空。",
        "no_food": "當天沒有飲食記錄。",
        "no_spending": "當天沒有支出記錄。",
        "unit_g": "公克",
        "unit_ml": "毫升",
        "unit_portions": "份",
        "unit_servings": "份量",
        "unit_pieces": "個",
        "unit_kcal": "千卡",
        "unit_mg": "毫克",
        "confirm": "確認",
        "delete_warning": "此操作為永久刪除，無法復原。",
        "current_categories": "目前類別：",
        "per_day": "每日",
        "update_calorie_limit": "更新卡路里限制",
        "category_exists": "該類別已存在。",
        "settings": "預算設定",
        "save_settings": "儲存設定",
        "err_invalid_number": "無效的數字。",
        "err_negative": "數值不能為負數。",
        "err_already_exists": "該項目已存在。",
        "warn_select": "請先選擇一項。",
        "warn_no_remove_calories": "無法移除卡路里類別。",
        "err_invalid_calories": "無效的卡路里。",
        "err_invalid_amount": "無效的份量。",
        "err_invalid_price": "無效的價格。",
        "rank_label": "飲食排名：{0}（積分 {1}）",
        "rank_none": "尚未開始",
        "rank_rookie": "新手",
        "rank_consistent": "穩定",
        "rank_dedicated": "專注",
        "rank_marathoner": "馬拉松",
        "rank_disciplined": "自律",
        "rank_legend": "傳奇",
        "leaderboard": "排行榜",
        "leaderboards": "排行榜",
        "create_leaderboard": "建立排行榜",
        "join_leaderboard": "加入排行榜",
        "add_leaderboard": "新增排行榜",
        "leaderboard_name": "排行榜名稱",
        "access_code": "存取碼",
        "leaderboard_created": "排行榜已建立。",
        "leaderboard_exists": "已有同名排行榜。",
        "leaderboard_joined": "已加入排行榜。",
        "already_member": "你已在此排行榜中。",
        "wrong_access_code": "排行榜不存在或存取碼錯誤。",
        "no_leaderboards": "你尚未加入任何排行榜。",
        "members": "成員",
        "change_name": "更改名稱",
        "change_code": "更改存取碼",
        "remove_leaderboard": "移除排行榜",
        "leaderboard_removed": "排行榜已移除。",
        "all_leaderboards": "所有排行榜",
        "no_members_yet": "此排行榜尚無成員。",
        "leave_leaderboard": "退出排行榜",
        "leaderboard_left": "你已退出排行榜。",
        "leave_confirm": "退出此排行榜？你可以之後用存取碼重新加入。",
        "kick_member": "踢除成員",
        "kick": "踢出",
        "member_kicked": "成員已被移出排行榜。",
        "kick_confirm": "將 {name} 移出此排行榜？",
        "new_username": "新用戶名",
        "rename_user": "更改用戶名",
        "username_changed": "用戶名已更新。",
        "cannot_rename_admin": "無法更改管理員帳戶。",
        "add_item": "新增項目",
        "display_edit": "顯示／編輯",
        "back_to_list": "返回列表",
        "user": "用戶",
        "score": "積分",
        "rank_title": "排名",
        "tier": "階級",
        "no_users_yet": "尚無用戶。",
        "weekdays": ["一", "二", "三", "四", "五", "六", "日"],
        "months": ["一月", "二月", "三月", "四月", "五月", "六月", "七月",
                   "八月", "九月", "十月", "十一月", "十二月"],
    },
}

def diet_score(day, week, month):
    """Composite diet score weighting day/week/month streaks by days."""
    return day + week * 7 + month * 30


DIET_RANK_TIERS = [
    (365, "rank_legend"),
    (200, "rank_disciplined"),
    (120, "rank_marathoner"),
    (60, "rank_dedicated"),
    (30, "rank_consistent"),
    (7, "rank_rookie"),
    (0, "rank_none"),
]


def diet_rank(day, week, month):
    """Return (rank_key, score) combining the diet streaks."""
    score = diet_score(day, week, month)
    for threshold, rank_key in DIET_RANK_TIERS:
        if score >= threshold:
            return rank_key, score
    return "rank_none", score


class Value:
    def __init__(self, amount, unit):
        self.amount = amount
        self.unit = unit

    def __add__(self, other):
        if not isinstance(other, Value):
            return NotImplemented
        if self.unit != other.unit:
            raise ValueError(f"Cannot sum units '{self.unit}' and '{other.unit}'")
        return Value(self.amount + other.amount, self.unit)

    def __str__(self):
        amount = self.amount
        if isinstance(amount, float) and amount.is_integer():
            amount = int(amount)
        return f"{amount} {self.unit}"

    def __repr__(self):
        return f"Value({self.amount}, {self.unit!r})"


class CategoryLimit:
    def __init__(self, name, unit, limit):
        self.name = name
        self.unit = unit
        self.limit = limit


class FoodEntry:
    def __init__(self, name, meal, calories, amount=None, extras=None):
        self.name = name
        self.meal = meal
        self.calories = calories  # Value in kcal
        self.amount = amount      # Value in g or portions, optional
        self.extras = dict(extras) if extras else {}  # category key -> Value


class DietDay:
    def __init__(self, date_obj):
        self.date = date_obj
        self.entries = []

    def add_entry(self, entry):
        self.entries.append(entry)

    def remove_entry(self, index):
        del self.entries[index]

    def sum_of(self, category, default_unit="kcal"):
        if category == "calories":
            values = [entry.calories for entry in self.entries]
        else:
            values = [entry.extras[category] for entry in self.entries if category in entry.extras]
        if not values:
            return Value(0, default_unit)
        total = Value(0, values[0].unit)
        for value in values:
            total = total + value
        return total


class SpendingEntry:
    def __init__(self, name, category, price):
        self.name = name
        self.category = category
        self.price = price  # Value in HKD


def categories_satisfied(day_obj, categories):
    for key, cat in categories.items():
        if day_obj.sum_of(key, cat.unit).amount > cat.limit:
            return False
    return True


def compute_streaks(days, categories, ref_date):
    """Return (day_streak, week_streak, month_streak).

    A day counts when it is logged and every category is at or below its daily
    limit. Week/month: a period counts only after every day in the period has
    been logged, and only if every category's period total is at or below its
    daily limit times the number of days in the period.
    """
    def period_met(dates, allowance_days):
        if not all(d in days and days[d].entries for d in dates):
            return False
        for key, cat in categories.items():
            total = sum(int(days[d].sum_of(key, cat.unit).amount) for d in dates)
            if total > cat.limit * allowance_days:
                return False
        return True

    day_streak = 0
    cursor = ref_date
    while cursor in days and days[cursor].entries and categories_satisfied(days[cursor], categories):
        day_streak += 1
        cursor -= timedelta(days=1)

    week_streak = 0
    cursor = ref_date
    while True:
        week_start = cursor - timedelta(days=cursor.weekday())
        week_days = [week_start + timedelta(days=i) for i in range(7)]
        if not period_met(week_days, 7):
            break
        week_streak += 1
        cursor = week_start - timedelta(days=1)

    month_streak = 0
    year, month = ref_date.year, ref_date.month
    while True:
        n_days = calendar.monthrange(year, month)[1]
        month_days = [date(year, month, d) for d in range(1, n_days + 1)]
        if not period_met(month_days, n_days):
            break
        month_streak += 1
        month -= 1
        if month == 0:
            year, month = year - 1, 12

    return day_streak, week_streak, month_streak


def period_expenses(spends, period, ref_date):
    """Return spending entries for the period ('day'|'week'|'month')
    containing ref_date."""
    if period == "day":
        dates = [ref_date]
    elif period == "week":
        start = ref_date - timedelta(days=ref_date.weekday())
        dates = [start + timedelta(days=i) for i in range(7)]
    else:
        dates = [
            date(ref_date.year, ref_date.month, d)
            for d in range(1, calendar.monthrange(ref_date.year, ref_date.month)[1] + 1)
        ]
    return [e for d in dates for e in spends.get(d, ())]


def weeks_in_month(year, month):
    """Number of calendar weeks (Mon-Sun) intersecting the month."""
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    start = first - timedelta(days=first.weekday())
    end = last - timedelta(days=last.weekday())
    return (end - start).days // 7 + 1


def budget_allowance_factor(base, kind, ref_date):
    """How many times the base-period limit is allowed in the given period
    kind, or None if that streak is not available for this base period."""
    if base == "day":
        if kind == "day":
            return 1
        if kind == "week":
            return 7
        if kind == "month":
            return calendar.monthrange(ref_date.year, ref_date.month)[1]
    elif base == "week":
        if kind == "week":
            return 1
        if kind == "month":
            return weeks_in_month(ref_date.year, ref_date.month)
    elif base == "month":
        if kind == "month":
            return 1
    return None


def previous_period_start(kind, cursor):
    if kind == "day":
        return cursor - timedelta(days=1)
    if kind == "week":
        return cursor - timedelta(days=cursor.weekday()) - timedelta(days=1)
    year, month = cursor.year, cursor.month - 1
    if month == 0:
        year, month = year - 1, 12
    return date(year, month, 1)


def compute_budget_streaks(spends, base, limit_amount, ref_date):
    """Streaks for each period available for the base limit period.

    day limit -> day, week, month streaks
    week limit -> week, month streaks
    month limit -> month streak only
    """
    streaks = {}
    for kind in ("day", "week", "month"):
        if budget_allowance_factor(base, kind, ref_date) is None:
            continue
        streak = 0
        cursor = ref_date
        while True:
            expenses = period_expenses(spends, kind, cursor)
            if not expenses:
                break
            allowance = limit_amount * budget_allowance_factor(base, kind, cursor)
            if sum(int(e.price.amount) for e in expenses) > allowance:
                break
            streak += 1
            cursor = previous_period_start(kind, cursor)
        streaks[kind] = streak
    return streaks


_BASE_FRAME = tk.Frame if tk is not None else object


class Calendar(_BASE_FRAME):
    def __init__(self, parent, status_fn, on_select, weekday_names=None, format_month=None):
        super().__init__(parent)
        self.status_fn = status_fn
        self.on_select = on_select
        self.weekday_names = weekday_names or ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        self.format_month = format_month or (lambda d: d.strftime("%B %Y"))
        self.current = date.today().replace(day=1)
        self.selected = date.today()
        self.day_cells = {}

        self.build_nav()
        self.build_header()
        self.grid_frame = tk.Frame(self)
        self.grid_frame.pack()
        self.draw_month()

    def build_nav(self):
        nav = tk.Frame(self)
        nav.pack(pady=4)
        tk.Button(nav, text="◀", width=2, command=self.prev_month).pack(side="left")
        self.month_label = tk.Label(nav, text="", font=("Arial", 10, "bold"), width=12)
        self.month_label.pack(side="left")
        tk.Button(nav, text="▶", width=2, command=self.next_month).pack(side="left")

    def build_header(self):
        header = tk.Frame(self)
        header.pack()
        for i, wd in enumerate(self.weekday_names):
            tk.Label(header, text=wd, width=4, font=("Arial", 9, "bold")).grid(row=0, column=i)

    def prev_month(self):
        year, month = self.current.year, self.current.month
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        self.current = date(year, month, 1)
        self.draw_month()

    def next_month(self):
        year, month = self.current.year, self.current.month
        month += 1
        if month == 13:
            year, month = year + 1, 1
        self.current = date(year, month, 1)
        self.draw_month()

    def draw_month(self):
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        self.day_cells = {}
        self.month_label.config(text=self.format_month(self.current))

        weeks = calendar.Calendar(firstweekday=calendar.MONDAY).monthdayscalendar(
            self.current.year, self.current.month
        )
        for r, week in enumerate(weeks):
            for c, daynum in enumerate(week):
                if daynum == 0:
                    continue
                day = date(self.current.year, self.current.month, daynum)
                cell = tk.Label(
                    self.grid_frame, text=str(daynum), width=4, bd=1,
                    relief="groove", bg="#f0f0f0", font=("Arial", 10),
                )
                cell.grid(row=r, column=c, padx=1, pady=1)
                cell.bind("<Button-1>", lambda _e, d=day: self.select(d))
                self.day_cells[day] = cell
        self.refresh()

    def select(self, day):
        self.selected = day
        self.refresh()
        self.on_select(day)

    def refresh(self):
        for day, cell in self.day_cells.items():
            status = self.status_fn(day)
            colors = {"none": "#f0f0f0", "ok": "#c8f7c5", "exceeded": "#ffb3b3"}
            bg = colors.get(status, "#f0f0f0")
            if day == self.selected:
                cell.config(bg="#90caf9", font=("Arial", 10, "bold"))
            else:
                cell.config(bg=bg, font=("Arial", 10))


class DietTrackerApp:
    def __init__(self, root):
        self.root = root
        self.lang = "en"

        self.days = {}
        self.diet_categories = {"calories": CategoryLimit("Calories", "kcal", 2000)}
        self.selected_date = date.today()

        self.spends = {}
        self.budget_limit = Value(8000, "HKD")
        self.budget_period = "month"

        self.load_data()

        self.root.title(self.tr("app_title"))
        self.root.geometry("1060x640")

        top = tk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(top, text=self.tr("app_title"), font=("Arial", 14, "bold")).pack(side="left")
        tk.Label(top, text=self.tr("language") + ":").pack(side="right")
        self.lang_combo = ttk.Combobox(top, state="readonly", width=8, values=["English", "中文"])
        self.lang_combo.pack(side="right", padx=(4, 0))
        self.lang_combo.set("English")
        self.lang_combo.bind("<<ComboboxSelected>>", self.on_lang_change)

        self.main_container = tk.Frame(self.root)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)
        self.build_ui()
        self.refresh_all()

    # ------------------------------------------------------------- i18n

    def tr(self, key):
        return STRINGS[self.lang][key]

    def unit_display(self, unit):
        key = "unit_" + str(unit).lower()
        table = STRINGS[self.lang]
        return table[key] if key in table else str(unit)

    def unit_from_label(self, label):
        for u in ("g", "portions", "kcal", "mg"):
            if self.unit_display(u) == label:
                return u
        return label

    def on_lang_change(self, _event=None):
        self.lang = "zh" if self.lang_combo.get() == "中文" else "en"
        self.root.title(self.tr("app_title"))
        for widget in self.main_container.winfo_children():
            widget.destroy()
        self.build_ui()
        self.refresh_all()

    def format_date(self, d):
        if self.lang == "zh":
            return f"{d.year}年{d.month}月{d.day}日 星期{self.tr('weekdays')[d.weekday()]}"
        return d.strftime("%A, %d %B %Y")

    # ------------------------------------------------------------- UI

    def build_ui(self):
        main = self.main_container

        left = tk.Frame(main)
        left.pack(side="left", fill="y", padx=(0, 10))

        self.calendar = Calendar(
            left, self.day_status, self.on_date_selected,
            weekday_names=self.tr("weekdays"),
            format_month=lambda d: f"{self.tr('months')[d.month - 1]} {d.year}",
        )
        self.calendar.pack()

        limit_frame = tk.Frame(left)
        limit_frame.pack(pady=(12, 0))
        tk.Label(limit_frame, text=self.tr("calorie_limit") + ":").pack(side="left")
        self.limit_var = tk.StringVar(value=str(self.diet_categories["calories"].limit))
        tk.Entry(limit_frame, textvariable=self.limit_var, width=8).pack(side="left", padx=4)
        tk.Button(limit_frame, text=self.tr("set"), command=self.set_limit).pack(side="left")

        cat_frame = tk.Frame(left)
        cat_frame.pack(fill="x", pady=(10, 0))
        tk.Label(cat_frame, text=self.tr("category_limits") + ":").pack(anchor="w")
        self.category_list = tk.Listbox(cat_frame, height=4)
        self.category_list.pack(fill="x")
        cat_row = tk.Frame(cat_frame)
        cat_row.pack(fill="x", pady=(4, 0))
        tk.Button(cat_row, text=self.tr("add_category"), command=self.add_category).pack(side="left")
        tk.Button(cat_row, text=self.tr("edit_category"), command=self.edit_category).pack(side="left", padx=4)
        tk.Button(cat_row, text=self.tr("remove_category"), command=self.remove_category).pack(side="left", padx=4)

        self.date_label = tk.Label(left, text="", font=("Arial", 11, "bold"), pady=10)
        self.date_label.pack()

        right = tk.Frame(main)
        right.pack(side="left", fill="both", expand=True)

        diet_panel = tk.LabelFrame(right, text=self.tr("diet"), padx=8, pady=6)
        diet_panel.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.build_diet_panel(diet_panel)

        budget_panel = tk.LabelFrame(right, text=self.tr("budget"), padx=8, pady=6)
        budget_panel.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self.build_budget_panel(budget_panel)

    def build_diet_panel(self, parent):
        row = tk.Frame(parent)
        row.pack(fill="x", pady=(0, 6))
        tk.Button(row, text=self.tr("create"), command=self.open_entry_dialog).pack(side="left")
        tk.Button(row, text=self.tr("edit"), command=self.edit_selected).pack(side="left", padx=4)
        tk.Button(row, text=self.tr("remove"), command=self.remove_selected).pack(side="left")

        self.tree = ttk.Treeview(
            parent, columns=("name", "meal", "amount", "calories"),
            show="headings", selectmode="browse",
        )
        self.tree.heading("name", text=self.tr("food"))
        self.tree.heading("meal", text=self.tr("meal"))
        self.tree.heading("amount", text=self.tr("amount"))
        self.tree.heading("calories", text=self.tr("calories"))
        self.tree.column("name", width=160)
        self.tree.column("meal", width=80)
        self.tree.column("amount", width=80)
        self.tree.column("calories", width=80)
        self.tree.pack(fill="both", expand=True)

        self.diet_total_label = tk.Label(parent, text="", font=("Arial", 11, "bold"), pady=6)
        self.diet_total_label.pack()

        self.diet_streak_label = tk.Label(parent, text="", font=("Arial", 10), fg="#1565c0")
        self.diet_streak_label.pack()

        self.diet_rank_label = tk.Label(parent, text="", font=("Arial", 11, "bold"),
                                        fg="#e65100", pady=(4, 0))
        self.diet_rank_label.pack()

    def build_budget_panel(self, parent):
        lim = tk.Frame(parent)
        lim.pack(fill="x", pady=(0, 6))
        tk.Label(lim, text=self.tr("limit_hkd") + ":").pack(side="left")
        self.budget_limit_var = tk.StringVar(value=str(self.budget_limit.amount))
        tk.Entry(lim, textvariable=self.budget_limit_var, width=7).pack(side="left", padx=3)
        period_labels = [self.tr(p) for p in PERIODS]
        self.budget_period_combo = ttk.Combobox(lim, values=period_labels, state="readonly", width=8)
        self.budget_period_combo.pack(side="left", padx=3)
        self.budget_period_combo.current(PERIODS.index(self.budget_period))
        tk.Button(lim, text=self.tr("set"), command=self.set_budget_limit).pack(side="left")

        row = tk.Frame(parent)
        row.pack(fill="x", pady=(0, 6))
        tk.Button(row, text=self.tr("create"), command=self.open_spending_dialog).pack(side="left")
        tk.Button(row, text=self.tr("edit"), command=self.edit_budget_selected).pack(side="left", padx=4)
        tk.Button(row, text=self.tr("remove"), command=self.remove_budget_selected).pack(side="left")

        self.budget_tree = ttk.Treeview(
            parent, columns=("name", "category", "price"),
            show="headings", selectmode="browse",
        )
        self.budget_tree.heading("name", text=self.tr("spending"))
        self.budget_tree.heading("category", text=self.tr("category"))
        self.budget_tree.heading("price", text=self.tr("price_col"))
        self.budget_tree.column("name", width=150)
        self.budget_tree.column("category", width=90)
        self.budget_tree.column("price", width=80)
        self.budget_tree.pack(fill="both", expand=True)

        self.budget_total_label = tk.Label(parent, text="", font=("Arial", 11, "bold"), pady=6)
        self.budget_total_label.pack()

        self.budget_streak_label = tk.Label(parent, text="", font=("Arial", 10), fg="#1565c0")
        self.budget_streak_label.pack()

    # ---------------------------------------------------------- status

    def get_day(self, day):
        return self.days.setdefault(day, DietDay(day))

    def diet_status(self, day):
        day_obj = self.days.get(day)
        if not day_obj or not day_obj.entries:
            return "none"
        return "ok" if categories_satisfied(day_obj, self.diet_categories) else "exceeded"

    def budget_status(self, day):
        if not self.spends.get(day):
            return "none"
        expenses = period_expenses(self.spends, self.budget_period, day)
        total = sum(int(e.price.amount) for e in expenses)
        return "ok" if total <= self.budget_limit.amount else "exceeded"

    def day_status(self, day):
        diet = self.diet_status(day)
        budget = self.budget_status(day)
        if diet == "none" and budget == "none":
            return "none"
        if diet == "exceeded" or budget == "exceeded":
            return "exceeded"
        return "ok"

    def on_date_selected(self, day):
        self.selected_date = day
        self.refresh_all()

    def refresh_all(self):
        self.date_label.config(text=self.format_date(self.selected_date))
        self.refresh_categories_list()
        self.refresh_diet()
        self.refresh_budget()
        self.calendar.refresh()

    # ------------------------------------------------------------ diet

    def set_limit(self):
        try:
            kcal = int(self.limit_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", self.tr("err_invalid_number"))
            return
        if kcal < 0:
            messagebox.showerror("Error", self.tr("err_negative"))
            return
        self.diet_categories["calories"].limit = kcal
        self.refresh_all()

    def refresh_categories_list(self):
        self.category_keys = list(self.diet_categories)
        self.category_list.delete(0, tk.END)
        for key in self.category_keys:
            cat = self.diet_categories[key]
            self.category_list.insert(tk.END, f"{cat.name} ({self.unit_display(cat.unit)}): limit {cat.limit}")

    def add_category(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(self.tr("add_category"))
        dialog.geometry("320x180")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = tk.Frame(dialog)
        frame.pack(fill="both", expand=True, padx=14, pady=10)

        tk.Label(frame, text=self.tr("category_name") + ":").grid(row=0, column=0, sticky="w")
        name_var = tk.StringVar()
        tk.Entry(frame, textvariable=name_var).grid(row=0, column=1, sticky="we", pady=3)

        tk.Label(frame, text=self.tr("unit") + ":").grid(row=1, column=0, sticky="w")
        unit_var = tk.StringVar(value=self.unit_display("g"))
        ttk.Combobox(frame, textvariable=unit_var,
                     values=[self.unit_display(u) for u in ("g", "portions", "kcal", "mg")]).grid(
            row=1, column=1, sticky="we", pady=3
        )

        tk.Label(frame, text=self.tr("daily_limit") + ":").grid(row=2, column=0, sticky="w")
        limit_var = tk.StringVar()
        tk.Entry(frame, textvariable=limit_var).grid(row=2, column=1, sticky="we", pady=3)

        def save(_event=None):
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("Error", self.tr("name_empty"), parent=dialog)
                return
            key = name.lower()
            if key in self.diet_categories:
                messagebox.showerror("Error", self.tr("err_already_exists"), parent=dialog)
                return
            try:
                limit = int(limit_var.get().strip())
            except ValueError:
                messagebox.showerror("Error", self.tr("err_invalid_number"), parent=dialog)
                return
            self.diet_categories[key] = CategoryLimit(name, self.unit_from_label(unit_var.get().strip()) or "g", limit)
            self.refresh_all()
            dialog.destroy()

        frame.columnconfigure(1, weight=1)
        buttons = tk.Frame(dialog)
        buttons.pack(pady=(0, 10))
        tk.Button(buttons, text=self.tr("add"), command=save).pack(side="left")
        tk.Button(buttons, text=self.tr("cancel"), command=dialog.destroy).pack(side="left", padx=8)
        dialog.bind("<Return>", save)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

    def edit_category(self):
        selection = self.category_list.curselection()
        if not selection:
            messagebox.showwarning("Warning", self.tr("warn_select"))
            return
        key = self.category_keys[selection[0]]
        cat = self.diet_categories[key]

        dialog = tk.Toplevel(self.root)
        dialog.title(self.tr("edit_category"))
        dialog.geometry("320x180")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = tk.Frame(dialog)
        frame.pack(fill="both", expand=True, padx=14, pady=10)

        tk.Label(frame, text=self.tr("category_name") + ":").grid(row=0, column=0, sticky="w")
        name_var = tk.StringVar(value=cat.name)
        tk.Entry(frame, textvariable=name_var).grid(row=0, column=1, sticky="we", pady=3)

        tk.Label(frame, text=self.tr("unit") + ":").grid(row=1, column=0, sticky="w")
        unit_var = tk.StringVar(value=self.unit_display(cat.unit))
        ttk.Combobox(frame, textvariable=unit_var,
                     values=[self.unit_display(u) for u in ("g", "portions", "kcal", "mg")]).grid(
            row=1, column=1, sticky="we", pady=3
        )

        tk.Label(frame, text=self.tr("daily_limit") + ":").grid(row=2, column=0, sticky="w")
        limit_var = tk.StringVar(value=str(cat.limit))
        tk.Entry(frame, textvariable=limit_var).grid(row=2, column=1, sticky="we", pady=3)

        def save(_event=None):
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("Error", self.tr("name_empty"), parent=dialog)
                return
            try:
                limit = int(limit_var.get().strip())
            except ValueError:
                messagebox.showerror("Error", self.tr("err_invalid_number"), parent=dialog)
                return
            new_key = key if key == "calories" else name.lower()
            if new_key != key and new_key in self.diet_categories:
                messagebox.showerror("Error", self.tr("err_already_exists"), parent=dialog)
                return
            if new_key != key:
                self.diet_categories[new_key] = self.diet_categories.pop(key)
                for day in self.days.values():
                    for entry in day.entries:
                        if key in entry.extras:
                            entry.extras[new_key] = entry.extras.pop(key)
            edited = self.diet_categories[new_key]
            edited.name = name
            edited.unit = self.unit_from_label(unit_var.get().strip()) or "g"
            edited.limit = limit
            self.refresh_all()
            dialog.destroy()

        frame.columnconfigure(1, weight=1)
        buttons = tk.Frame(dialog)
        buttons.pack(pady=(0, 10))
        tk.Button(buttons, text=self.tr("save"), command=save).pack(side="left")
        tk.Button(buttons, text=self.tr("cancel"), command=dialog.destroy).pack(side="left", padx=8)
        dialog.bind("<Return>", save)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

    def remove_category(self):
        selection = self.category_list.curselection()
        if not selection:
            messagebox.showwarning("Warning", self.tr("warn_select"))
            return
        key = self.category_keys[selection[0]]
        if key == "calories":
            messagebox.showwarning("Warning", self.tr("warn_no_remove_calories"))
            return
        del self.diet_categories[key]
        self.refresh_all()

    def open_entry_dialog(self, entry=None):
        extra_count = sum(1 for k in self.diet_categories if k != "calories")
        dialog = tk.Toplevel(self.root)
        dialog.title(self.tr("create") if entry is None else self.tr("edit"))
        dialog.geometry(f"360x{290 + extra_count * 28}")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = tk.Frame(dialog)
        frame.pack(fill="both", expand=True, padx=14, pady=10)

        tk.Label(frame, text=self.tr("adding_to").format(self.format_date(self.selected_date))).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )

        tk.Label(frame, text=self.tr("food_name") + ":").grid(row=1, column=0, sticky="w")
        name_var = tk.StringVar(value=entry.name if entry else "")
        tk.Entry(frame, textvariable=name_var).grid(row=1, column=1, columnspan=2, sticky="we", pady=3)

        tk.Label(frame, text=self.tr("meal_type") + ":").grid(row=2, column=0, sticky="w")
        meal_labels = [self.tr(m) for m in MEALS]
        meal_var = tk.StringVar()
        meal_combo = ttk.Combobox(frame, textvariable=meal_var, values=meal_labels, state="readonly", width=16)
        meal_combo.grid(row=2, column=1, columnspan=2, sticky="we", pady=3)
        meal_combo.current(MEALS.index(entry.meal) if entry else 0)

        tk.Label(frame, text=self.tr("calories") + ":").grid(row=3, column=0, sticky="w")
        cal_var = tk.StringVar(value=str(entry.calories.amount) if entry else "")
        tk.Entry(frame, textvariable=cal_var).grid(row=3, column=1, columnspan=2, sticky="we", pady=3)

        tk.Label(frame, text=self.tr("amount") + ":").grid(row=4, column=0, sticky="w")
        amount_var = tk.StringVar(value=str(entry.amount.amount) if entry and entry.amount else "")
        tk.Entry(frame, textvariable=amount_var).grid(row=4, column=1, sticky="we", pady=3)
        unit_var = tk.StringVar(
            value=self.unit_display(entry.amount.unit) if entry and entry.amount else self.unit_display("g")
        )
        ttk.Combobox(frame, textvariable=unit_var,
                     values=[self.unit_display(u) for u in ("g", "portions")],
                     state="readonly", width=9).grid(
            row=4, column=2, sticky="we", padx=(4, 0), pady=3
        )

        extra_vars = {}
        row = 5
        for key, cat in self.diet_categories.items():
            if key == "calories":
                continue
            tk.Label(frame, text=f"{cat.name} ({self.unit_display(cat.unit)}):").grid(row=row, column=0, sticky="w")
            var = tk.StringVar(value=str(entry.extras[key].amount) if entry and key in entry.extras else "")
            tk.Entry(frame, textvariable=var).grid(row=row, column=1, columnspan=2, sticky="we", pady=3)
            extra_vars[key] = var
            row += 1

        def save(_event=None):
            name = name_var.get().strip()
            try:
                kcal = int(cal_var.get().strip())
            except ValueError:
                messagebox.showerror("Error", self.tr("err_invalid_calories"), parent=dialog)
                return
            if not name:
                messagebox.showerror("Error", self.tr("name_empty"), parent=dialog)
                return
            if kcal < 0:
                messagebox.showerror("Error", self.tr("err_negative"), parent=dialog)
                return

            amount = None
            if amount_var.get().strip():
                try:
                    amt = float(amount_var.get().strip())
                except ValueError:
                    messagebox.showerror("Error", self.tr("err_invalid_amount"), parent=dialog)
                    return
                if amt > 0:
                    amount = Value(amt, self.unit_from_label(unit_var.get()))

            extras = {}
            for key, var in extra_vars.items():
                if not var.get().strip():
                    continue
                try:
                    val = float(var.get().strip())
                except ValueError:
                    messagebox.showerror("Error", self.tr("err_invalid_number"), parent=dialog)
                    return
                if val >= 0:
                    extras[key] = Value(val, self.diet_categories[key].unit)

            meal = MEALS[meal_combo.current()]
            day = self.get_day(self.selected_date)
            if entry:
                entry.name = name
                entry.meal = meal
                entry.calories = Value(kcal, "kcal")
                entry.amount = amount
                entry.extras = extras
            else:
                day.add_entry(FoodEntry(name, meal, Value(kcal, "kcal"), amount, extras))
            self.refresh_all()
            dialog.destroy()

        def cancel(_event=None):
            dialog.destroy()

        frame.columnconfigure(1, weight=1)
        buttons = tk.Frame(dialog)
        buttons.pack(pady=(0, 10))
        tk.Button(buttons, text=self.tr("save"), command=save).pack(side="left")
        tk.Button(buttons, text=self.tr("cancel"), command=cancel).pack(side="left", padx=8)
        dialog.bind("<Return>", save)
        dialog.bind("<Escape>", cancel)

    def edit_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", self.tr("warn_select"))
            return
        day = self.get_day(self.selected_date)
        self.open_entry_dialog(day.entries[int(selection[0])])

    def remove_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", self.tr("warn_select"))
            return
        day = self.get_day(self.selected_date)
        day.remove_entry(int(selection[0]))
        self.refresh_all()

    def refresh_diet(self):
        self.tree.delete(*self.tree.get_children())
        cats = list(self.diet_categories)
        columns = ("name", "meal", "amount") + tuple(cats)
        self.tree["columns"] = columns
        headings = {
            "name": self.tr("food"),
            "meal": self.tr("meal"),
            "amount": self.tr("amount"),
        }
        for key in cats:
            headings[key] = self.tr("calories") if key == "calories" else self.diet_categories[key].name
        widths = {"name": 160, "meal": 80, "amount": 80}
        for key, text in headings.items():
            self.tree.heading(key, text=text)
            self.tree.column(key, width=widths.get(key, 70))

        day = self.days.get(self.selected_date)
        if day:
            for i, entry in enumerate(day.entries):
                amount_txt = ""
                if entry.amount:
                    amount_txt = f"{entry.amount.amount:g} {self.unit_display(entry.amount.unit)}"
                values = [entry.name, self.tr(entry.meal), amount_txt]
                for key in cats:
                    if key == "calories":
                        values.append(f"{entry.calories.amount:g} {self.unit_display('kcal')}")
                    else:
                        extra = entry.extras.get(key)
                        values.append(
                            f"{extra.amount:g} {self.unit_display(extra.unit)}" if extra else ""
                        )
                self.tree.insert("", "end", iid=str(i), values=values)

        if not day or not day.entries:
            self.diet_total_label.config(text=self.tr("no_entries"), fg="#555555")
        else:
            parts = []
            over = False
            for key, cat in self.diet_categories.items():
                total = day.sum_of(key, cat.unit)
                part = f"{cat.name}: {total.amount:g} {self.unit_display(total.unit)}"
                if total.amount > cat.limit:
                    part += "!"
                    over = True
                parts.append(part)
            self.diet_total_label.config(text="  |  ".join(parts),
                                         fg="#c62828" if over else "#2e7d32")

        day_s, week_s, month_s = compute_streaks(self.days, self.diet_categories, self.selected_date)
        self.diet_streak_label.config(
            text=f"{self.tr('day')}: {day_s}  |  {self.tr('week')}: {week_s}  |  {self.tr('month')}: {month_s}"
        )

        rank_key, score = diet_rank(day_s, week_s, month_s)
        self.diet_rank_label.config(
            text=self.tr("rank_label").format(self.tr(rank_key), score),
            fg="#c62828" if rank_key == "rank_none" else "#e65100",
        )

    # ---------------------------------------------------------- budget

    def set_budget_limit(self):
        try:
            hkd = int(self.budget_limit_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", self.tr("err_invalid_number"))
            return
        if hkd < 0:
            messagebox.showerror("Error", self.tr("err_negative"))
            return
        self.budget_period = PERIODS[self.budget_period_combo.current()]
        self.budget_limit = Value(hkd, "HKD")
        self.refresh_all()

    def budget_cat_display(self, c):
        key = "budget_cat_" + c.lower().replace(" ", "_")
        label = self.tr(key)
        return label if label != key else c

    def budget_cat_from_label(self, label):
        for c in CATEGORIES:
            if self.budget_cat_display(c) == label:
                return c
        return label if label in CATEGORIES else label

    def open_spending_dialog(self, entry=None):
        dialog = tk.Toplevel(self.root)
        dialog.title(self.tr("create") if entry is None else self.tr("edit"))
        dialog.geometry("340x220")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = tk.Frame(dialog)
        frame.pack(fill="both", expand=True, padx=14, pady=10)

        tk.Label(frame, text=self.tr("spending_on").format(self.format_date(self.selected_date))).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        tk.Label(frame, text=self.tr("spending_name") + ":").grid(row=1, column=0, sticky="w")
        name_var = tk.StringVar(value=entry.name if entry else "")
        tk.Entry(frame, textvariable=name_var).grid(row=1, column=1, sticky="we", pady=3)

        tk.Label(frame, text=self.tr("category") + ":").grid(row=2, column=0, sticky="w")
        cat_var = tk.StringVar(value=self.budget_cat_display(entry.category if entry else "Food"))
        ttk.Combobox(frame, textvariable=cat_var,
                     values=[self.budget_cat_display(c) for c in CATEGORIES], width=16).grid(
            row=2, column=1, sticky="we", pady=3
        )

        tk.Label(frame, text=self.tr("price") + ":").grid(row=3, column=0, sticky="w")
        price_var = tk.StringVar(value=str(entry.price.amount) if entry else "")
        tk.Entry(frame, textvariable=price_var).grid(row=3, column=1, sticky="we", pady=3)

        def save(_event=None):
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("Error", self.tr("name_empty"), parent=dialog)
                return
            try:
                price = float(price_var.get().strip())
            except ValueError:
                messagebox.showerror("Error", self.tr("err_invalid_price"), parent=dialog)
                return
            if price < 0:
                messagebox.showerror("Error", self.tr("err_negative"), parent=dialog)
                return

            spendings = self.spends.setdefault(self.selected_date, [])
            if entry:
                entry.name = name
                entry.category = self.budget_cat_from_label(cat_var.get().strip()) or "Other"
                entry.price = Value(price, "HKD")
            else:
                spendings.append(SpendingEntry(
                    name, self.budget_cat_from_label(cat_var.get().strip()) or "Other",
                    Value(price, "HKD"),
                ))
            self.refresh_all()
            dialog.destroy()

        def cancel(_event=None):
            dialog.destroy()

        frame.columnconfigure(1, weight=1)
        buttons = tk.Frame(dialog)
        buttons.pack(pady=(0, 10))
        tk.Button(buttons, text=self.tr("save"), command=save).pack(side="left")
        tk.Button(buttons, text=self.tr("cancel"), command=cancel).pack(side="left", padx=8)
        dialog.bind("<Return>", save)
        dialog.bind("<Escape>", cancel)

    def edit_budget_selected(self):
        selection = self.budget_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", self.tr("warn_select"))
            return
        index = int(selection[0])
        self.open_spending_dialog(self.spends.get(self.selected_date, [])[index])

    def remove_budget_selected(self):
        selection = self.budget_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", self.tr("warn_select"))
            return
        spendings = self.spends.get(self.selected_date, [])
        spendings.pop(int(selection[0]))
        if not spendings:
            self.spends.pop(self.selected_date, None)
        self.refresh_all()

    def refresh_budget(self):
        self.budget_tree.delete(*self.budget_tree.get_children())
        spendings = self.spends.get(self.selected_date, [])
        for i, entry in enumerate(spendings):
            self.budget_tree.insert(
                "", "end", iid=str(i),
                values=(entry.name, self.budget_cat_display(entry.category), str(entry.price)),
            )

        expenses = period_expenses(self.spends, self.budget_period, self.selected_date)
        total = Value(sum(int(e.price.amount) for e in expenses), "HKD")

        text = f"{self.tr(self.budget_period)} {self.tr('total')}: {total} / {self.tr('limit_hkd')}: {self.budget_limit.amount}"
        if total.amount > self.budget_limit.amount:
            text += f"  {self.tr('over_limit')}"
            self.budget_total_label.config(fg="#c62828")
        else:
            self.budget_total_label.config(fg="#2e7d32")
        self.budget_total_label.config(text=text)

        streaks = compute_budget_streaks(self.spends, self.budget_period, self.budget_limit.amount, self.selected_date)
        labels = {"day": self.tr("day"), "week": self.tr("week"), "month": self.tr("month")}
        streak_text = "  |  ".join(f"{labels[k]}: {v}" for k, v in streaks.items())
        self.budget_streak_label.config(
            text=f"{self.tr('streaks')} ({self.tr(self.budget_period)}): {streak_text}"
        )

    # --------------------------------------------------- persistence

    def on_close(self):
        self.save_data()
        self.root.destroy()

    def save_data(self):
        data = {
            "diet_categories": {
                key: {"name": cat.name, "unit": cat.unit, "limit": cat.limit}
                for key, cat in self.diet_categories.items()
            },
            "days": {
                d.isoformat(): [self.entry_to_dict(e) for e in day.entries]
                for d, day in self.days.items()
            },
            "budget_period": self.budget_period,
            "budget_limit": self.budget_limit.amount,
            "spends": {
                d.isoformat(): [
                    {"name": e.name, "category": e.category, "price": e.price.amount}
                    for e in entries
                ]
                for d, entries in self.spends.items()
            },
        }
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def entry_to_dict(entry):
        return {
            "name": entry.name,
            "meal": entry.meal,
            "calories": entry.calories.amount,
            "amount": [entry.amount.amount, entry.amount.unit] if entry.amount else None,
            "extras": {k: [v.amount, v.unit] for k, v in entry.extras.items()},
        }

    def load_data(self):
        if not os.path.exists(DATA_FILE):
            return
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        self.diet_categories = {}
        for key, c in data.get("diet_categories", {}).items():
            self.diet_categories[key] = CategoryLimit(
                c.get("name", key), c.get("unit", "g"), int(c.get("limit", 0))
            )
        self.diet_categories.setdefault("calories", CategoryLimit("Calories", "kcal", 2000))

        self.days = {}
        for d_str, entries in data.get("days", {}).items():
            try:
                d = date.fromisoformat(d_str)
            except ValueError:
                continue
            day = DietDay(d)
            for e in entries:
                amount = Value(*e["amount"]) if e.get("amount") else None
                extras = {k: Value(*v) for k, v in e.get("extras", {}).items()}
                day.add_entry(
                    FoodEntry(e["name"], e["meal"], Value(e["calories"], "kcal"), amount, extras)
                )
            self.days[d] = day

        self.budget_period = data.get("budget_period", "month")
        self.budget_limit = Value(float(data.get("budget_limit", 8000)), "HKD")
        self.spends = {}
        for d_str, entries in data.get("spends", {}).items():
            try:
                d = date.fromisoformat(d_str)
            except ValueError:
                continue
            self.spends[d] = [
                SpendingEntry(e["name"], e["category"], Value(float(e["price"]), "HKD"))
                for e in entries
            ]


if __name__ == "__main__":
    if tk is None:
        raise SystemExit("tkinter is not available on this system")
    root = tk.Tk()
    DietTrackerApp(root)
    root.mainloop()
