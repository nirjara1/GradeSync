from .docker_runner import DockerRunner
from .normalize_java import normalize_java_files
from typing import Dict, Any, Tuple
import os

class JavaRunner(DockerRunner):
    def __init__(self, image_name: str = "gradesync-java"):
        super().__init__(image_name)

    def run_submission(self, submission_path: str, assignment_config: Dict[str, Any]) -> Tuple[str, str, int]:
        # 1. Normalize files
        normalize_java_files(submission_path)
        
        # 2. Compile and Run
        # We need a main class or test runner.
        # Simplification: Compile all .java and run a specific Main class or Test class
        
        main_class = assignment_config.get('main_class', 'Main')
        
        # javac *.java && java Main
        command = f"sh -c 'javac *.java && java {main_class}'"
        
        stdout, stderr, exit_code = self._run_container(submission_path, command)
        return stdout, stderr, exit_code
