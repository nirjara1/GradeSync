# GradeSync Docker Setup Guide

GradeSync provides a complete, containerized environment that simplifies execution mapping to a PostgreSQL container and a Web Django container.

## 1. Environment Configurations

Make sure to adjust `.env` variable bindings (either safely copied from `env example` or customized with real DB credentials). Default Docker-compose connects properly.

```bash
cp "env example" .env
```

## 2. Running GradeSync

We provide helper scripts located in the `scripts/` directory. Ensure you're running this from the repository text root.

```bash
bash scripts/run_docker.sh
```

Alternatively, you can just manually trigger Docker Compose:

```bash
docker compose up --build
```

### Accessing the System
Once the containers finish booting natively, access GradeSync at: `http://localhost:80` (or `http://127.0.0.1:80` on macOS).

## 3. Stopping the Container

Simply use your terminal equivalent to exit (usually `Ctrl+C`). It safely shuts down instances.

To remove detached volumes or clean up cleanly:
```bash
docker compose down -v
```
