# Local Development Setup

To run GradeSync locally using the PostgreSQL shared database:

### 1. Configure Environment
Copy the example environment file:
```bash
cp .env.example .env
```
Ensure that your local PostgreSQL instance matches the credentials listed in `.env` or update them as needed.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Migrations
Generate the database schema on your local PostgreSQL engine:
```bash
cd backend
python manage.py migrate
```

### 4. Load Seed Data
Populate the database with the pre-configured mock professor, student, and grading assistant accounts for testing:
```bash
python manage.py loaddata ../database/postgres/seed_data.json
```

### 5. Start Server
```bash
python manage.py runserver
```
