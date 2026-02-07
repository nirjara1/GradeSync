# GradeSync Employee Portal (Django + Postgres + Docker)

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

## To load the dummy seed data use the following command
docker compose exec web python manage.py seed_data


## Create admin user (optional)
docker compose exec web python manage.py createsuperuser

## Open Locally
- App: http://localhost
- Admin: http://localhost/admin/

## When the EC2 is ON
- http://3.151.189.18
