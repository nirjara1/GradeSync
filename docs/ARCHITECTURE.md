# GradeSync Architecture Overview

GradeSync is composed of three main architectural modules: a Django-based web interface, a PostgreSQL relational database backend, and an isolated autograder AI Python/Java execution module.

## 1. Web Frontend & Backend (Django)
The primary interface logic and APIs are built using Django. The codebase handles routing, views, form processing, professor dashboards, student portals, and models. 

### Key Systems
- **Django Apps**: Features structured around logically cohesive units (`grading`, `portal`, `items`, `professor`).
- **Templates**: Standard server-rendered HTML blocks integrated with vanilla CSS and Bootstrap constraints.
- **ORM Models**: Django interacts dynamically via ORM mapping tables mapped directly to standard workflows (Users, Courses, Assignments).

## 2. Autograder AI Engine (`autograder_ai/`)
This is a secure, containerized (or deterministically controlled) module built to analyze submissions using AST parsing, AI-driven heuristic feedback generation, and structured outputs.

### Key Systems
- **Validation**: Security checks on sandboxed code.
- **Runners**: Direct python/java compilation/execution hooks.
- **Plagiarism Tracking**: Detection checks for syntax similarities.

## 3. Database Infrastructure (`database/`)
All relational persistent history is handled using PostgreSQL, specifically via the `docker-compose.yml` db container. Local development can fall back to `db.sqlite3` during basic testing.
