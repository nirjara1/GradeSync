from .docker_runner import DockerRunner
from typing import Dict, Any, Tuple, List, Union
import os


class PythonRunner(DockerRunner):
    """
    Runs Python submissions inside the Python grader Docker image.
    Assumes the host-side submission_path is mounted to /submission in the container.
    """

    def __init__(self, image_name: str = "gradesync-python"):
        super().__init__(image_name)

    def run_submission(
        self,
        submission_path: str,
        assignment_config: Dict[str, Any]
    ) -> Tuple[str, str, int]:
        # Where to run tests from (inside /submission). Default: run discovery from /submission.
        # If your prepared workspace puts tests in /submission/tests, set this in config:
        # assignment_config["tests_dir"] = "tests"
        tests_dir = assignment_config.get("tests_dir")  # e.g. "tests" or None

        # Where to write pytest's JSON report (inside the mounted /submission directory)
        # This ensures the host can read it back at submission_path/report.json
        report_filename = assignment_config.get("pytest_report_file", "report.json")

        # Build a robust pytest command:
        # - use python3 -m pytest (no PATH issues)
        # - force-load plugin even if autoload is disabled
        cmd: List[str] = [
            "python3", "-m", "pytest",
            "-q",
            "-p", "pytest_jsonreport",
            "--json-report",
            f"--json-report-file={report_filename}",
        ]

        # If tests_dir is provided, run pytest against that directory
        if tests_dir:
            cmd.append(tests_dir)

        # Run inside docker
        stdout, stderr, exit_code = self._run_container(submission_path, cmd)
        return stdout, stderr, exit_code
