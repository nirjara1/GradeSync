# GradeSync Local Setup Guide

Follow these steps to run GradeSync natively on your local machine using SQLite/PostgreSQL and local Python environments.

## Prerequisites
- Python 3.10+
- `pip` and `virtualenv`
- (Optional) Local PostgreSQL instance

## 1. Environment Setup

Copy the environment example to create your local variables:
```bash
cp "env example" .env
```
Edit `.env` to match your local setup (e.g., if using SQLite, database variables can be ignored).

## 2. Virtual Environment

Create and activate your virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Install Dependencies

Install the requirements from the root directory:
```bash
pip install -r requirements.txt
```

## 4. Database Migrations

Apply Django migrations to set up your local database:
```bash
cd app
python manage.py migrate
```

## 5. Running the Application

We have provided a helper script in the `scripts/` directory to start the server:

```bash
# Ensure you are at the repository root
bash scripts/run_local.sh
```

Alternatively, manually start the server:
```bash
cd app
python manage.py runserver
```

The app will be available at `http://127.0.0.1:8000`.
