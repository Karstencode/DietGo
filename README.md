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

- 🏆 **Leaderboard**: ranks every registered user by their combined diet score.
- 🟢 Calendar day colouring: green = within limits, red = over, grey = no data.
- 👤 Per-user accounts with salted password hashes (web version).

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

## Deployment (Streamlit Community Cloud)

1. Push this folder to a GitHub repository.
2. On [share.streamlit.io](https://share.streamlit.io), click **New app**,
   select the repo, set **Main file path** to `app.py`, and deploy.
3. `requirements.txt` installs `streamlit` automatically.

> Data for the web version is stored in a local SQLite database
> (`streamlit_data.db`) next to `app.py`. On Community Cloud each app
> gets persistent network storage, but for guaranteed durability you can point
> `DB_PATH` at hosted storage (e.g. a PostgreSQL/Supabase backend).