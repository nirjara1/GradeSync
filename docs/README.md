# GradeSync Employee Portal (Django + Postgres + Docker)

## Prereqs
- Docker Desktop installed and running

## Setup
1) Clone repo
2) Create env file:
   - copy `.env.example` to `.env`
   - For anything beyond your own machine, set `DJANGO_SECRET_KEY` and `DJANGO_DEBUG=0` (see comments in `.env.example`)

## Run
docker compose up --build

## Migrate DB
docker compose exec web python manage.py migrate


## Create admin user
docker compose exec web python manage.py createsuperuser

Step 1: Login as admin at http://localhost:8000/admin/
Step 2: Create an User from account option from navigation bar. Assign the user as professor or student.
Step 3: Admin will create an username and password for the user. Use that login credentials to login as professor or student.

## Open Locally
Default Compose maps the app to **port 8000** (`8000:8000`). Use that port unless you add a reverse proxy on 80.

- Student portal: http://localhost:8000/
- Professor area: http://localhost:8000/professor/
- Admin: http://localhost:8000/admin/

## Sample assignment test cases (CSV)
Professors can download a starter file from **Create Assignment** in the UI. 

## When the EC2 is ON
- Student portal: http://3.151.189.18/
- Professor area: http://3.151.189.18/professor/
- Admin: http://3.151.189.18/admin/
