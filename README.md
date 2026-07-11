# Expense Tracker — Backend

Flask REST API for the Expense Tracker application, organised in a layered
architecture (blueprints → controllers → database) over PostgreSQL. Serves the
[expense-tracker-mobile](https://github.com/123yogin/expense-tracker-mobile) app.

## Features

- **Expenses, income, categories, and budgets** with full CRUD
- **Groups & split expenses** and per-user data isolation
- **Recurring expenses** and reusable **templates/shortcuts**
- **Receipts** and **reporting/export**
- **Notifications** and smart features (smart categorization, voice entry)
- Versioned **SQL migrations** and a production **Gunicorn** config

## Tech stack

- Python + Flask (blueprint-based modular API)
- PostgreSQL (SQL migrations under `migrations/`)
- Gunicorn (production WSGI)
- Pytest for tests; Dockerfile included

## Getting started

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # database connection + config
# apply migrations in migrations/ to your PostgreSQL database, then:
python app.py                 # dev server
# production:
gunicorn -c gunicorn.conf.py app:app
```

Run with Docker:

```bash
docker build -t expensetracker-api .
docker run --env-file .env -p 5000:5000 expensetracker-api
```

## Project structure

```
app.py                entry point / app factory
blueprints/           expenses, income, categories, budgets, groups, receipts,
                      recurring_expenses, reports, export, notifications,
                      smart_categorization, smart_features, templates, voice
controllers/          request handling (e.g. expense_controller.py)
database.py           DB connection
middleware.py         request middleware · validators.py · responses.py · errors.py
migrations/           001–009 SQL migrations
tests/                pytest suite
```
