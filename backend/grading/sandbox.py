"""
Docker-based code execution sandbox for secure student code execution.

This module provides isolated execution environments for running student
code with resource constraints, timeout limits, and no network access.
"""

import base64
import docker
import tempfile
import os
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional
import time

logger = logging.getLogger(__name__)

# Base dir for temp execution dirs — must be bind-mounted into the web container from the host
# so that when we mount it into the student container, the host path has our files (see docker-compose).
SANDBOX_BASE_DIR = os.environ.get("GRADESYNC_SANDBOX_DIR", "/tmp/gradesync_sandbox")
try:
    os.makedirs(SANDBOX_BASE_DIR, mode=0o1777, exist_ok=True)
except OSError:
    pass  # use default temp if not writable


class CodeExecutionError(Exception):
    """Exception raised during code execution."""
    pass


class SandboxExecutor:
    """
    Executes code in Docker containers with strict resource and security constraints.
    
    Features:
    - Language support: Python 3.10+, Java 17+
    - Resource limits: 128MB memory, 10-second timeout
    - Security: No network access, read-only code volume
    - Input/Output: Support for stdin input and stdout/stderr capture
    """
    
    TIMEOUT_SECONDS = 10
    MEMORY_LIMIT = '128m'
    
    # Docker image mappings for different languages
    # Use stable, widely-available tags
    LANGUAGE_IMAGES = {
        'python': 'python:3.10-alpine',
        # Eclipse Temurin is the current official OpenJDK distribution on Docker Hub
        'java': 'eclipse-temurin:17-jdk',
    }
    
    def __init__(self):
        """Initialize Docker client."""
        try:
            self.client = docker.from_env()
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise CodeExecutionError(f"Docker not available: {e}")
    
    def execute_python(
        self,
        code: str,
        input_data: str = "",
        submission_id: Optional[int] = None,
    ) -> Dict[str, any]:
        """
        Execute Python code in an isolated container.
        
        Args:
            code: Python source code to execute
            input_data: Input to pass via stdin
            submission_id: Optional submission ID for logging
            
        Returns:
            Dict with keys:
            - success: bool, whether execution completed successfully
            - stdout: str, captured standard output
            - stderr: str, captured standard error
            - exit_code: int, process exit code
            - execution_time: float, seconds taken to execute
            - error: str (optional), error message if execution failed
        """
        return self._execute_in_container(
            language='python',
            code=code,
            input_data=input_data,
            submission_id=submission_id,
        )
    
    def execute_java(
        self,
        code: str,
        input_data: str = "",
        submission_id: Optional[int] = None,
    ) -> Dict[str, any]:
        """
        Execute Java code in an isolated container.
        
        Args:
            code: Java source code to execute (must contain a main class)
            input_data: Input to pass via stdin
            submission_id: Optional submission ID for logging
            
        Returns:
            Dict with same structure as execute_python
        """
        return self._execute_in_container(
            language='java',
            code=code,
            input_data=input_data,
            submission_id=submission_id,
        )
    
    def _execute_in_container(
        self,
        language: str,
        code: str,
        input_data: str = "",
        submission_id: Optional[int] = None,
    ) -> Dict[str, any]:
        """
        Internal method to execute code in a Docker container.
        
        Args:
            language: Programming language ('python' or 'java')
            code: Source code to execute
            input_data: Input via stdin
            submission_id: Optional submission ID for logging/tracking
            
        Returns:
            Execution result dictionary
        """
        if language not in self.LANGUAGE_IMAGES:
            return {
                'success': False,
                'stdout': '',
                'stderr': f'Unsupported language: {language}',
                'exit_code': -1,
                'execution_time': 0.0,
                'error': f'Language {language} not supported',
            }
        
        container = None
        start_time = time.time()
        
        try:
            # Prepare code execution based on language
            if language == 'python':
                container_code, command = self._prepare_python_execution(code)
            elif language == 'java':
                container_code, command = self._prepare_java_execution(code)
            
            # Encode test input as base64 and pass via env so we don't rely on volume having input.txt
            stdin_b64 = base64.b64encode((input_data or '').encode('utf-8')).decode('ascii')
            # Run inside container: decode env to /tmp/input.txt (tmpfs), then run with stdin from that file
            if language == 'python':
                run_cmd = 'echo "$STDIN_B64" | base64 -d > /tmp/input.txt && python /code/solution.py < /tmp/input.txt'
            else:
                run_cmd = 'echo "$STDIN_B64" | base64 -d > /tmp/input.txt && javac /code/Solution.java && java -cp /code Solution < /tmp/input.txt'

            # Create temporary directory for code (inside host-visible sandbox so mount works)
            try:
                use_sandbox_dir = SANDBOX_BASE_DIR if os.path.isdir(SANDBOX_BASE_DIR) else None
            except OSError:
                use_sandbox_dir = None
            with tempfile.TemporaryDirectory(prefix="exec_", dir=use_sandbox_dir) as tmpdir:
                code_file = os.path.join(tmpdir, 'solution.py' if language == 'python' else 'Solution.java')
                with open(code_file, 'w', encoding='utf-8') as f:
                    f.write(container_code)

                image = self.LANGUAGE_IMAGES[language]
                try:
                    self.client.images.get(image)
                except docker.errors.ImageNotFound:
                    logger.info(f"Pulling Docker image: {image}")
                    self.client.images.pull(image)

                # Java needs a writable /code volume so javac can emit .class files.
                volume_mode = 'ro' if language == 'python' else 'rw'

                container = self.client.containers.create(
                    image,
                    command=['sh', '-c', run_cmd],
                    stdin_open=False,
                    mem_limit=self.MEMORY_LIMIT,
                    memswap_limit=self.MEMORY_LIMIT,
                    network_disabled=True,
                    read_only=False,
                    tmpfs={'/tmp': 'size=32m,mode=1777'},
                    volumes={
                        tmpdir: {'bind': '/code', 'mode': volume_mode},
                    },
                    environment={
                        'PYTHONUNBUFFERED': '1',
                        'PYTHONDONTWRITEBYTECODE': '1',
                        'STDIN_B64': stdin_b64,
                    },
                )
                
                # Execute container with timeout
                try:
                    result = container.start()
                    
                    # Wait for container with timeout
                    exit_code = container.wait(timeout=self.TIMEOUT_SECONDS)
                    
                    # Get output
                    output = container.logs(stdout=True, stderr=False).decode('utf-8', errors='replace')
                    error_output = container.logs(stdout=False, stderr=True).decode('utf-8', errors='replace')
                    
                    execution_time = time.time() - start_time
                    
                    return {
                        'success': exit_code == 0,
                        'stdout': output,
                        'stderr': error_output,
                        'exit_code': exit_code,
                        'execution_time': execution_time,
                    }
                    
                except docker.errors.APIError as e:
                    if 'Timeout' in str(e) or 'timeout' in str(e).lower():
                        # Container execution timed out
                        execution_time = time.time() - start_time
                        return {
                            'success': False,
                            'stdout': '',
                            'stderr': f'Execution timeout after {self.TIMEOUT_SECONDS} seconds',
                            'exit_code': -1,
                            'execution_time': execution_time,
                            'error': 'Timeout - code took too long to execute',
                        }
                    else:
                        raise
        
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = str(e)
            logger.exception(f"Error executing {language} code (submission_id={submission_id}): {error_msg}")
            
            return {
                'success': False,
                'stdout': '',
                'stderr': error_msg,
                'exit_code': -1,
                'execution_time': execution_time,
                'error': f'Execution error: {error_msg}',
            }
        
        finally:
            # Clean up container
            if container:
                try:
                    container.remove(force=True)
                except Exception as e:
                    logger.warning(f"Failed to remove container: {e}")
    
    def _prepare_python_execution(self, code: str) -> Tuple[str, list]:
        """
        Prepare Python code for container execution.
        
        Args:
            code: Student Python code
            
        Returns:
            Tuple of (modified_code, command_list)
        """
        # Wrap code to handle input/output properly
        wrapped_code = f"""
import sys
import io

# Set up stdin/stdout
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

# Execute student code
{code}
"""
        
        command = ['python', '-c', wrapped_code]
        return wrapped_code, command
    
    def _prepare_java_execution(self, code: str) -> Tuple[str, list]:
        """
        Prepare Java code for container execution.
        
        Args:
            code: Student Java code
            
        Returns:
            Tuple of (modified_code, command_list)
        """
        # Java needs a main class named 'Solution'
        # Extract class name if present
        if 'class Solution' not in code:
            if 'class ' in code:
                # Replace existing class name with Solution
                import re
                code = re.sub(r'class\s+\w+', 'class Solution', code, count=1)
            else:
                # Wrap code in a Solution class
                code = f"""
public class Solution {{
    public static void main(String[] args) {{
{chr(10).join(f'        {line}' for line in code.split(chr(10)))}
    }}
}}
"""
        
        command = ['sh', '-c', f'javac /code/Solution.java && java -cp /code Solution']
        return code, command
    
    def cleanup(self):
        """Clean up Docker client resources."""
        try:
            self.client.close()
        except Exception as e:
            logger.warning(f"Error closing Docker client: {e}")


# Global executor instance
_executor = None


def get_executor() -> SandboxExecutor:
    """Get or create the global SandboxExecutor instance."""
    global _executor
    if _executor is None:
        _executor = SandboxExecutor()
    return _executor


def execute_code(
    language: str,
    code: str,
    input_data: str = "",
    submission_id: Optional[int] = None,
) -> Dict[str, any]:
    """
    Execute code in a sandboxed Docker container.
    
    Args:
        language: 'python' or 'java'
        code: Source code to execute
        input_data: Input to pass via stdin
        submission_id: Optional submission ID for tracking
        
    Returns:
        Execution result dictionary with stdout, stderr, exit_code, etc.
    """
    executor = get_executor()
    
    if language == 'python':
        return executor.execute_python(code, input_data, submission_id)
    elif language == 'java':
        return executor.execute_java(code, input_data, submission_id)
    else:
        return {
            'success': False,
            'stdout': '',
            'stderr': f'Unsupported language: {language}',
            'exit_code': -1,
            'execution_time': 0.0,
            'error': f'Language {language} not supported',
        }
