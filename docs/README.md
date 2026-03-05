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


## Create admin user
docker compose exec web python manage.py createsuperuser

Step 1: Login as admin at http://localhost/admin/
Step 2: Create an User from account option from navigation bar. Assign the user as professor or student.
Step 3: Admin will create an username and password for the user. Use that login credentials to login as professor or student.

## Open Locally
- Student_login: http://localhost
- Professor_login: http://localhost/professor
- Admin_login: http://localhost/admin/

## When the EC2 is ON
- Student_login: http://3.151.189.18
- Professor_login: http://3.151.189.18/professor
- Admin: http://3.151.189.18/admin/
