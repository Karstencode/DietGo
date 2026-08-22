# Diet & Budget Diary

A dual diet and budget tracking app with per-user accounts, a shared calendar,
streaks, and a cross-user diet leaderboard. Ships with two front-ends:

- **`main.py`** — desktop app built with Tkinter (Python stdlib, no install needed).
- **`app.py`** — multi-user web app for Streamlit (deployable to the
  Streamlit Community Cloud).

Both front-ends share all business logic in `main.py` and support bilingual
interfaces: **English** and **繁體中文 (Traditional Chinese)**.

## Features

- 📅 Side-by-side **Diet** and **Budget** panels for the selected day.
- 🍽️ Diet tracking with configurable categories (calories, water, vegetables…),
  each with its own unit and daily limit.
- 💰 Budget tracking with **day / week / month** limit periods.
- 🔥 Streaks for diet (day / week / month) and budget, plus a **diet-only
  ranking system** that combines all three streaks into a score:

  | Tier | Score |
  |------|-------|
  | Legend 傳奇 | ≥ 365 |
  | Disciplined 自律 | ≥ 200 |
  | Marathoner 馬拉松 | ≥ 120 |
  | Dedicated 專注 | ≥ 60 |
  | Consistent 穩定 | ≥ 30 |
  | Rookie 新手 | ≥ 7 |
  | No streak 尚未開始 | < 7 |

  Score = `day_streak + week_streak × 7 + month_streak × 30`.

- 🏆 **Groups**: any user can **create** or **join** a group. Groups are either
  **private** (join by name + access code) or **public** (join by name only).
  Every member is automatically on the group ranking,
  ordered top‑to‑bottom by their combined diet score
  (`Score = day_streak + week_streak × 7 + month_streak × 30`).
- The **owner** (creator) can rename the group, change its access code
  (private groups only), remove it, **promote** members to co‑owners (same
  rights) or **demote** owners, **kick** members, and view any member's
  records — but only the
  parts the member agreed to share.
  - When joining a group you choose what the owner may see: **diet**,
    **budget**, or **both** (changeable any time under *Sharing*). Owner-side
    views respect that choice — diet/budget the member didn't share show
    *Permission not granted* — and always present the member's items in the
    same tables the owner uses, including the member's category amounts and
    their diet/budget limits.
  - Non‑owners can **leave** a group any time.
- 🟢 Calendar day colouring: green = within limits, red = over, grey = no data.
- 👤 Per-user accounts with salted password hashes (web version).
- 📱 Mobile-friendly web UI: the diet/budget day panels switch between a big
  **Add** button (entry form) and a **Display/Edit** button (list + edit/remove).
- 🗃️ The web app keeps at most **60 days** of diet/budget data per user. When
  storage is full, adding a brand‑new day prompts you to delete the oldest
  stored day(s) first. Day / week / month streaks are **preserved across
  deletions** and keep building seamlessly, so trimming old data never breaks a
  streak.

## Run locally (web)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Run locally (desktop)

```bash
python3 main.py
```

## Tests

```bash
python3 test.py
```

## Admin account (web)

A reserved **`admin`** account is created automatically on first run. Only
**admin** can (and admin never views any user's diet/budget records):

- reset any user's password
- delete accounts
- add accounts
- rename any username (group memberships and ownership follow)
- create, rename, or remove groups the admin created (admin-created groups are
  **public** and always created by name only, with no access code, and never
  joined by the admin). Admin sees a public group's
  member list and can kick members; **private (user-created) groups are never
  shown to or managed by the admin** — their membership and member records stay
  completely private.

Set the admin password via the `ADMIN_PASSWORD` environment variable or in
`.streamlit/secrets.toml` (`admin_password`). Otherwise it defaults to
`admin123` — **change it before going live**.

## Deployment (Streamlit Community Cloud)

1. Push this folder to a GitHub repository.
2. On [share.streamlit.io](https://share.streamlit.io), click **New app**,
   select the repo, set **Main file path** to `app.py`, and deploy.
3. `requirements.txt` installs `streamlit` automatically.

> **Where your data lives.** By default the web app uses a local SQLite file
> (`streamlit_data.db`) next to `app.py` — perfect for `streamlit run app.py`
> on your own machine. On Streamlit Community Cloud that filesystem is
> **ephemeral**: when a free-tier app sleeps (or restarts/redeploys), local
> files are wiped.

### Free durable hosting (no data loss, even when the app sleeps)

Point the app at [Turso](https://turso.tech) — a free hosted SQLite service
that never sleeps and keeps your data forever:

1. Create a free Turso account and database:
   ```bash
   curl -sSfL https://get.tur.so/install.sh | bash
   turso auth signup
   turso db create diet-budget-diary
   turso db show diet-budget-diary --url          # libsql://… URL
   turso db tokens create diet-budget-diary       # auth token
   ```
2. Give the credentials to the app via Streamlit secrets (Community Cloud:
   *App → Settings → Secrets*) or environment variables:
   ```toml
   turso_database_url = "libsql://diet-budget-diary-<you>.turso.io"
   turso_auth_token = "<token>"
   ```
   Env-var equivalents: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`.
3. Redeploy. The app now stores everything on Turso (`get_db()` switches
   automatically); accounts, diary entries, streaks and groups all survive
   sleeps, restarts and redeploys. Without these settings the app simply keeps
   using the local SQLite file as before.