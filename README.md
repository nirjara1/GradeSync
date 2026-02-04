# GradeSync Employee Portal (Django + Postgres + Docker)
## Git check
## Prereqs
- Docker Desktop installed and running

## Setup
1) Clone repo
2) Create env file:
   - copy `.env.example` to `.env`

## Run
docker compose up --build

## Migrate DB
docker compose exec web python manage.py migrate

## Create admin user (optional)
docker compose exec web python manage.py createsuperuser

## Open
- App: http://localhost:8000/
- Admin: http://localhost:8000/admin/
