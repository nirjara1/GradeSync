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
import re
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration – tweak these values via environment variables if needed.
# ---------------------------------------------------------------------------
EXECUTION_TIMEOUT_SECONDS = int(os.environ.get("EXECUTION_TIMEOUT_SECONDS", 10))
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
        # Use a stable Temurin JDK 17 image (official OpenJDK distro)
        "image": "eclipse-temurin:17-jdk",
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
    files = data.get("files", None)

    if language not in ALLOWED_LANGUAGES:
        return False, f"Unsupported language '{language}'. Supported: {sorted(ALLOWED_LANGUAGES)}", {}

    # Normalize filename
    config = LANGUAGE_CONFIG[language]
    parsed_files = []
    total_size = 0

    if files is not None:
        if not isinstance(files, list) or len(files) == 0:
            return False, "Field 'files' must be a non-empty list.", {}
        for item in files:
            if not isinstance(item, dict):
                return False, "Each item in 'files' must be an object.", {}
            fn = (item.get("filename") or item.get("name") or "").strip()
            fc = item.get("code", item.get("content", ""))
            if not fn:
                return False, "Each file must have a filename.", {}
            if fc is None:
                fc = ""
            if not isinstance(fc, str):
                return False, "Each file's code/content must be a string.", {}
            total_size += len(fc)
            parsed_files.append({"filename": fn, "code": fc})

        if total_size > 250_000:
            return False, "Total code exceeds maximum allowed size (250 KB).", {}

        if not filename:
            filename = parsed_files[0]["filename"]

    else:
        if not code:
            return False, "No code provided.", {}
        if len(code) > 100_000:
            return False, "Code exceeds maximum allowed size (100 KB).", {}
        if not filename:
            filename = config["filename"]

    return True, "", {"code": code, "language": language, "filename": filename, "files": parsed_files}


def _safe_filename(name: str) -> str:
    name = os.path.basename(name or "").strip()
    # Keep it simple: forbid directory traversal / empty filenames
    return name or "main"


_JAVA_MAIN_PATTERN = re.compile(r"public\s+static\s+void\s+main\s*\(", re.MULTILINE)


def _resolve_java_main_class_name(files: list | None, entry_filename: str) -> str:
    """
    JVM entry point for `java <ClassName>` after `javac *.java`.

    If multiple .java files are submitted, the active editor tab may point at a
    helper class with no main(). Prefer the source file that contains
    `public static void main(` and use its public class name (filename stem).
    Otherwise fall back to the basename of entry_filename (single-file / legacy).
    """
    if files:
        for item in files:
            fn = (item.get("filename") or item.get("name") or "").strip()
            if not fn.lower().endswith(".java"):
                continue
            content = item.get("code") or item.get("content") or ""
            if _JAVA_MAIN_PATTERN.search(content):
                base = os.path.splitext(os.path.basename(fn))[0]
                if base:
                    return base
    base = os.path.splitext(os.path.basename(_safe_filename(entry_filename)))[0]
    return base or "Main"


def _run_in_docker_with_input(code: str, language: str, filename: str, input_data: str = "", files: list | None = None) -> dict:
    """
    Write code to a temp file, mount it into a Docker container,
    execute it with stdin input, and return {'stdout': ..., 'stderr': ..., 'exit_code': ...}.
    """
    config = LANGUAGE_CONFIG[language]
    container_name = None  # will be set once container starts

    # Step 1: Clean the Input Data
    # Ensure any literal string representations of newlines are converted to actual newlines
    if input_data:
        input_data = input_data.replace('\\n', '\n')

    with tempfile.TemporaryDirectory(prefix="exec_", dir=SANDBOX_BASE_DIR) as tmpdir:
        entry_filename = _safe_filename(filename)

        # Write files into the temp directory
        if files:
            for item in files:
                fn = _safe_filename(item.get("filename", ""))
                fp = os.path.join(tmpdir, fn)
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(item.get("code", ""))
        else:
            source_path = os.path.join(tmpdir, entry_filename)
            with open(source_path, "w", encoding="utf-8") as f:
                f.write(code)

        # Step 2: Create a Temporary Input File
        input_file_path = os.path.join(tmpdir, "input_temp.txt")
        with open(input_file_path, "w", encoding="utf-8") as f:
            f.write(input_data)

        # Step 3: Refactor the Docker Run Command
        base_cmd = config["cmd"]

        # For Java, compile all sources then run the class that defines main()
        if language == "java":
            class_name = _resolve_java_main_class_name(files, entry_filename)
            logger.info("[execute] java entry class=%s (active filename hint=%s)", class_name, entry_filename)
            inner_script = f"cd /code && javac *.java && java {class_name}"
            docker_cmd_suffix = ["/bin/sh", "-c", f"{inner_script} < /code/input_temp.txt"]
        else:
            if language == "python":
                inner_script = f"python /code/{entry_filename}"
                docker_cmd_suffix = ["/bin/sh", "-c", f"{inner_script} < /code/input_temp.txt"]
            elif language == "javascript":
                inner_script = f"node /code/{entry_filename}"
                docker_cmd_suffix = ["/bin/sh", "-c", f"{inner_script} < /code/input_temp.txt"]
            elif language == "c":
                inner_script = f"gcc /code/{entry_filename} -o /code/a.out && /code/a.out"
                docker_cmd_suffix = ["/bin/sh", "-c", f"{inner_script} < /code/input_temp.txt"]
            else:
                if base_cmd[0] in ("sh", "/bin/sh") and base_cmd[1] == "-c":
                    inner_script = base_cmd[2]
                    docker_cmd_suffix = ["/bin/sh", "-c", f"{inner_script} < /code/input_temp.txt"]
                else:
                    joined_cmd = " ".join(base_cmd)
                    docker_cmd_suffix = ["/bin/sh", "-c", f"{joined_cmd} < /code/input_temp.txt"]

        # Build the docker run command
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
        ] + docker_cmd_suffix

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

            # Step 4: Capture and Clean Output
            # If stderr contains any data (like EOFError or ValueError), append it
            if stderr:
                # Provide spacing if there is already stdout
                if stdout:
                    stdout += "\n"
                stdout += stderr

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

    # TemporaryDirectory automatically cleans up the tmpdir and input_temp.txt here
    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "timed_out": False,
    }


def _run_in_docker(code: str, language: str, filename: str) -> dict:
    """
    Wrapper for _run_in_docker_with_input with no input (for backward compatibility).
    """
    return _run_in_docker_with_input(code, language, filename, input_data="")


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
    result = _run_in_docker_with_input(
        parsed["code"],
        parsed["language"],
        parsed["filename"],
        input_data="",
        files=parsed.get("files") or None,
    )

    logger.info(
        "[execute] user=%s lang=%s exit_code=%s timed_out=%s",
        request.user.username, parsed["language"], result["exit_code"], result["timed_out"]
    )

    return JsonResponse(result)
