# GradeSync Structure

This repository has been structured strictly to separate the frontend, backend, database scripts, AI autograder context, and deployment configurations into their own logical directories.

## Directory Layout

* `backend/` - Contains the Django project and all Django apps representing the server-side code API, admin configuration, routes, settings, logic, signals and ORM operations.
* `frontend/` - Contains the templates for Django apps and all static assets over traditional UI delivery (html, css, js, images).
* `database/` - Postgres settings, SQLite data layers, database migrations setups or seed files.
* `autograder_ai/` - Separate module holding external logic that is safely isolated from backend. Handing containerization builds, Java & Python code evaluation, and similarity reports scoring.
* `infra/` - Deployment, orchestrations configs, environment files to manage the running environments for GradeSync using docker.
* `docs/` - Comprehensive repository documentation and setups.
* `scripts/` - Easy-run scripting commands to execute systems components or build processes locally.
