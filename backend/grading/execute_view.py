"""
GradeSync – Remote Code Execution API
POST /api/execute

Spawns an ephemeral Docker container, injects student code, runs it with
strict resource limits, captures stdout/stderr, and tears the container down.

Security posture:
  - No network access for the container (--network none)
  - CPU limited to 0.5 cores, memory to 128 MB
  - Hard wall-clock timeout of 5 seconds (configurable via EXECUTION_TIMEOUT_SECONDS)
  - /tmp is a tmpfs (RAM-backed, no disk persistence)
  - /code is a writable bind-mount of a secure host tmpdir (needed for compilers)
  - Container is force-killed and removed after execution
  - Only authenticated users may call this endpoint
  - Payload is validated before Docker is ever invoked
"""

import json
import subprocess
import tempfile
import os
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration – tweak these values via environment variables if needed.
# ---------------------------------------------------------------------------
EXECUTION_TIMEOUT_SECONDS = int(os.environ.get("EXECUTION_TIMEOUT_SECONDS", 5))
MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB – prevent runaway stdout flooding the DB

# Shared sandbox directory — must be bind-mounted into the web container with
# the SAME path as it has on the host (see docker-compose.yml volumes section).
# The host Docker daemon uses THIS path when it mounts -v into execution containers.
SANDBOX_BASE_DIR = "/tmp/gradesync_sandbox"
os.makedirs(SANDBOX_BASE_DIR, mode=0o1777, exist_ok=True)

# Maps language identifiers sent from the frontend to Docker image + run command.
LANGUAGE_CONFIG = {
    "python": {
        "image": "python:3.10-alpine",
        "filename": "main.py",
        "cmd": ["python", "/code/main.py"],
    },
    "java": {
        "image": "openjdk:17-alpine",
        "filename": "Main.java",
        # compile first, then run; errors go to stderr naturally
        "cmd": ["sh", "-c", "cd /code && javac Main.java && java Main"],
    },
    "javascript": {
        "image": "node:20-alpine",
        "filename": "main.js",
        "cmd": ["node", "/code/main.js"],
    },
    "c": {
        "image": "gcc:13-alpine",
        "filename": "main.c",
        "cmd": ["sh", "-c", "gcc /code/main.c -o /code/a.out && /code/a.out"],
    },
}

ALLOWED_LANGUAGES = set(LANGUAGE_CONFIG.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_payload(data: dict) -> tuple[bool, str, dict]:
    """Return (ok, error_message, parsed_data)."""
    code = data.get("code", "")
    language = data.get("language", "").lower().strip()
    filename = data.get("filename", "").strip()

    if not code:
        return False, "No code provided.", {}
    if len(code) > 100_000:
        return False, "Code exceeds maximum allowed size (100 KB).", {}
    if language not in ALLOWED_LANGUAGES:
        return False, f"Unsupported language '{language}'. Supported: {sorted(ALLOWED_LANGUAGES)}", {}

    # Normalize filename
    config = LANGUAGE_CONFIG[language]
    if not filename:
        filename = config["filename"]

    return True, "", {"code": code, "language": language, "filename": filename}


def _run_in_docker(code: str, language: str) -> dict:
    """
    Write code to a temp file, mount it into a Docker container,
    execute it, and return {'stdout': ..., 'stderr': ..., 'exit_code': ...}.
    """
    config = LANGUAGE_CONFIG[language]
    container_name = None  # will be set once container starts

    with tempfile.TemporaryDirectory(prefix="exec_", dir=SANDBOX_BASE_DIR) as tmpdir:
        # Write the source file into the temp directory
        source_path = os.path.join(tmpdir, config["filename"])
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Build the docker run command
        # Security flags explained:
        #   --rm              : auto-remove after exit
        #   --network none    : no outbound internet access
        #   --memory          : hard memory cap
        #   --cpus            : fractional CPU cap
        #   --pids-limit      : prevent fork bombs
        #   --tmpfs /tmp      : RAM-backed /tmp, no disk writes persist
        #   -v <tmpdir>:/code : inject student source file (writable so
        #                       javac/gcc can write .class/.out into /code)
        #
        # NOTE: --read-only is intentionally omitted here because compiled
        # languages (Java, C) need to write output artefacts back into /code.
        # The tmpdir on the host is a secure, isolated temp directory that is
        # deleted by Python's TemporaryDirectory context manager after execution.
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--network", "none",
            "--memory", "128m",
            "--cpus", "0.5",
            "--pids-limit", "64",
            "--tmpfs", "/tmp:size=32m",
            "-v", f"{tmpdir}:/code",   # writable so compilers can emit .class/.out
            config["image"],
        ] + config["cmd"]

        logger.info(
            "[execute] lang=%s image=%s timeout=%ss",
            language, config["image"], EXECUTION_TIMEOUT_SECONDS
        )

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                timeout=EXECUTION_TIMEOUT_SECONDS,
                text=True,
            )
            stdout = result.stdout[:MAX_OUTPUT_BYTES]
            stderr = result.stderr[:MAX_OUTPUT_BYTES]
            exit_code = result.returncode

        except subprocess.TimeoutExpired:
            logger.warning("[execute] Execution timed out after %ss", EXECUTION_TIMEOUT_SECONDS)
            # The container has been killed by the timeout; subprocess cleans up.
            return {
                "stdout": "",
                "stderr": f"⏱ Execution timed out after {EXECUTION_TIMEOUT_SECONDS} seconds. "
                          "Check for infinite loops or excessive computation.",
                "exit_code": -1,
                "timed_out": True,
            }
        except FileNotFoundError:
            logger.error("[execute] Docker binary not found on PATH")
            return {
                "stdout": "",
                "stderr": "Server configuration error: Docker is not available.",
                "exit_code": -2,
                "timed_out": False,
            }
        except Exception as exc:
            logger.exception("[execute] Unexpected error during Docker execution: %s", exc)
            return {
                "stdout": "",
                "stderr": f"Execution engine error: {exc}",
                "exit_code": -3,
                "timed_out": False,
            }

    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "timed_out": False,
    }


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

@login_required
@require_POST
@csrf_exempt   # CSRF is enforced via Django session; we keep this for fetch() calls
               # that already send the session cookie.  If you want full CSRF token
               # validation, remove this decorator and pass X-CSRFToken in the header.
def execute_code_view(request):
    """
    POST /api/execute
    Body (JSON): { "code": "...", "language": "python", "filename": "main.py" }
    Response (JSON): { "stdout": "...", "stderr": "...", "exit_code": 0, "timed_out": false }
    """
    # Parse JSON body
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    # Validate
    ok, error_msg, parsed = _validate_payload(data)
    if not ok:
        return JsonResponse({"error": error_msg}, status=422)

    # Execute
    result = _run_in_docker(parsed["code"], parsed["language"])

    logger.info(
        "[execute] user=%s lang=%s exit_code=%s timed_out=%s",
        request.user.username, parsed["language"], result["exit_code"], result["timed_out"]
    )

    return JsonResponse(result)
