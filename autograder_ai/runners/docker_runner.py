# autograder_ai/runners/docker_runner.py

import docker
import os
import shutil
import logging
import shlex
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Union, List

logger = logging.getLogger(__name__)


class DockerRunner(ABC):
    def __init__(self, image_name: str, timeout: int = 30):
        self.image_name = image_name
        self.timeout = timeout
        try:
            self.client = docker.from_env()
        except Exception:
            self.client = None
            logger.warning("Docker client not found. Execution will fail unless mocked.")

    @abstractmethod
    def run_submission(
        self,
        submission_path: str,
        assignment_config: Dict[str, Any]
    ) -> Tuple[str, str, int]:
        """
        Runs the submission in a container.
        Returns: (stdout, stderr, exit_code)
        """
        raise NotImplementedError

    def _normalize_command(self, command: Union[str, List[str]]) -> List[str]:
        """
        Normalize the docker command into a list of args.
        Also rewrites 'pytest ...' to 'python -m pytest ...' for reliability.
        """
        if isinstance(command, str):
            cmd = shlex.split(command)
        else:
            cmd = list(command)

        # Make pytest invocation robust inside containers
        if cmd and cmd[0] == "pytest":
            cmd = ["python", "-m", "pytest"] + cmd[1:]

        return cmd

    def _run_container(self, mount_dir: str, command: Union[str, List[str]]) -> Tuple[str, str, int]:
        if not self.client:
            return "", "Docker not available", -1

        abs_mount_dir = os.path.abspath(mount_dir)
        cmd = self._normalize_command(command)

        try:
            container = self.client.containers.run(
                image=self.image_name,
                command=cmd,  # pass list of args (more reliable than a raw string)
                volumes={abs_mount_dir: {"bind": "/submission", "mode": "rw"}},
                working_dir="/submission",
                detach=True,
                network_disabled=True,  # Security
                # mem_limit="512m",    # Optional resource limits
                # pids_limit=256,      # Optional: limit number of processes
            )

            try:
                result = container.wait(timeout=self.timeout)
                exit_code = result.get("StatusCode", -1)

                # Grab combined logs (Docker doesn't always cleanly split stdout/stderr)
                logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
                stdout = logs
                stderr = ""

            except Exception as e:  # Timeout or other error
                try:
                    container.kill()
                except Exception:
                    pass

                stdout = ""
                stderr = f"Execution timed out or failed: {str(e)}"
                exit_code = -1

            finally:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

            return stdout, stderr, exit_code

        except Exception as e:
            return "", str(e), -1
