# -*- coding: utf-8 -*-
"""TaskRunner - Ephemeral script execution service for distributed workers"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from app.domain.models.mission import Mission, MissionResult

logger = logging.getLogger(__name__)


class StructuredLogger:
    """Wrapper for structured logging with context"""
    
    def __init__(self, logger_instance, **context):
        self.logger = logger_instance
        self.context = context
    
    def _log(self, level, msg, **extra):
        """Log with structured context"""
        log_data = {**self.context, **extra, "message": msg}
        self.logger.log(level, json.dumps(log_data))
    
    def info(self, msg, **extra):
        self._log(logging.INFO, msg, **extra)
    
    def error(self, msg, **extra):
        self._log(logging.ERROR, msg, **extra)
    
    def warning(self, msg, **extra):
        self._log(logging.WARNING, msg, **extra)
    
    def debug(self, msg, **extra):
        self._log(logging.DEBUG, msg, **extra)


class DependencyInstallationError(Exception):
    """Exception raised when a dependency fails to install"""
    
    def __init__(self, package: str, stderr: str, timeout: bool = False):
        self.package = package
        self.stderr = stderr
        self.timeout = timeout
        message = f"Failed to install package '{package}'"
        if timeout:
            message += " (timeout)"
        super().__init__(message)


class TaskRunner:
    """
    TaskRunner executes Python scripts in isolated environments with dependency management.
    
    Features:
    - Creates temporary virtual environments for script execution
    - Manages Python package dependencies
    - Captures stdout/stderr from script execution
    - Supports environment persistence for repeated executions
    - Integrates with library cache to avoid repeated downloads
    """
    
    def __init__(self, cache_dir: Optional[Path] = None, use_venv: bool = True, device_id: Optional[str] = None):
        """
        Initialize the TaskRunner
        
        Args:
            cache_dir: Optional directory for caching libraries and environments
            use_venv: Whether to use virtual environments (default: True)
            device_id: Optional device identifier for logging context
        """
        self.use_venv = use_venv
        self.device_id = device_id or "unknown"
        
        # Setup cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(tempfile.gettempdir()) / "jarvis_task_cache"
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"TaskRunner initialized with cache directory: {self.cache_dir}")
    
    def execute_mission(self, mission: Mission, session_id: Optional[str] = None) -> MissionResult:
        """
        Execute a mission with the provided code and dependencies
        
        Args:
            mission: Mission object containing code and configuration
            session_id: Optional session identifier for tracking
            
        Returns:
            MissionResult with execution outcome
        """
        start_time = time.time()
        mission_id = mission.mission_id
        session_id = session_id or "default"
        
        # Create structured logger with context
        log = StructuredLogger(
            logger,
            mission_id=mission_id,
            device_id=self.device_id,
            session_id=session_id
        )
        
        log.info("mission_started", 
                requirements=mission.requirements,
                browser_interaction=mission.browser_interaction,
                keep_alive=mission.keep_alive)
        
        # Create temporary script file
        script_file = None
        venv_path = None
        
        try:
            # Create temporary directory for this mission
            temp_dir = Path(tempfile.mkdtemp(prefix=f"mission_{mission_id}_"))
            script_file = temp_dir / "script.py"
            
            # Write script to file
            script_file.write_text(mission.code)
            log.debug("script_written", script_path=str(script_file))
            
            # Setup environment
            if self.use_venv:
                if mission.keep_alive:
                    # Use persistent venv in cache
                    venv_path = self.cache_dir / f"venv_{mission_id}"
                else:
                    # Use temporary venv
                    venv_path = temp_dir / "venv"
                
                # Create venv if it doesn't exist
                if not venv_path.exists():
                    log.info("venv_creating", venv_path=str(venv_path))
                    self._create_venv(venv_path)
                else:
                    log.info("venv_reusing", venv_path=str(venv_path))
                
                # Install dependencies if any - with graceful failure handling
                if mission.requirements:
                    log.info("dependencies_installing", count=len(mission.requirements))
                    try:
                        self._install_dependencies(venv_path, mission.requirements, log)
                    except DependencyInstallationError as e:
                        # Graceful failure: Log structured error and return friendly message
                        log.error("dependency_installation_failed",
                                error=str(e),
                                failed_package=e.package,
                                stderr=e.stderr)
                        
                        execution_time = time.time() - start_time
                        return MissionResult(
                            mission_id=mission_id,
                            success=False,
                            stdout="",
                            stderr=f"Failed to install dependency: {e.package}",
                            exit_code=1,
                            execution_time=execution_time,
                            error=f"DEPENDENCY_FAILED: {e.package} - {e.stderr[:200]}",
                        )
                
                # Get Python executable from venv
                python_exe = self._get_python_executable(venv_path)
            else:
                # Use system Python
                python_exe = sys.executable
                
                # Install dependencies to user site-packages if needed
                if mission.requirements:
                    log.info("dependencies_installing_system", count=len(mission.requirements))
                    try:
                        self._install_dependencies_system(mission.requirements, log)
                    except DependencyInstallationError as e:
                        # Graceful failure for system installation too
                        log.error("dependency_installation_failed",
                                error=str(e),
                                failed_package=e.package,
                                stderr=e.stderr)
                        
                        execution_time = time.time() - start_time
                        return MissionResult(
                            mission_id=mission_id,
                            success=False,
                            stdout="",
                            stderr=f"Failed to install dependency: {e.package}",
                            exit_code=1,
                            execution_time=execution_time,
                            error=f"DEPENDENCY_FAILED: {e.package} - {e.stderr[:200]}",
                        )
            
            # Execute the script
            log.info("script_executing", python_exe=python_exe, timeout=mission.timeout)
            result = self._execute_script(python_exe, script_file, mission.timeout)
            
            execution_time = time.time() - start_time
            log.info("mission_completed", 
                    execution_time=execution_time,
                    exit_code=result['exit_code'],
                    success=result["exit_code"] == 0)
            
            # Create result
            mission_result = MissionResult(
                mission_id=mission_id,
                success=result["exit_code"] == 0,
                stdout=result["stdout"],
                stderr=result["stderr"],
                exit_code=result["exit_code"],
                execution_time=execution_time,
                error=result.get("error"),
                metadata={
                    "venv_path": str(venv_path) if venv_path else None,
                    "script_path": str(script_file),
                    "persistent": mission.keep_alive,
                }
            )
            
            return mission_result
            
        except Exception as e:
            import traceback
            execution_time = time.time() - start_time
            tb = traceback.format_exc()
            log.error("mission_failed", 
                     error=str(e),
                     error_type=type(e).__name__,
                     traceback=tb,
                     execution_time=execution_time)
            
            return MissionResult(
                mission_id=mission_id,
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=1,
                execution_time=execution_time,
                error=str(e),
            )
            
        finally:
            # Cleanup unless keep_alive is set
            if not mission.keep_alive and script_file:
                try:
                    # Remove temporary files
                    if script_file.exists():
                        script_file.unlink()
                    
                    # Remove temp directory if it's not in cache
                    temp_dir = script_file.parent
                    if temp_dir.exists() and not str(temp_dir).startswith(str(self.cache_dir)):
                        import shutil
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        logger.debug(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as e:
                    logger.warning(f"Error during cleanup: {e}")
    
    def _create_venv(self, venv_path: Path) -> None:
        """Create a virtual environment at the specified path"""
        try:
            import venv
            venv.create(str(venv_path), with_pip=True, clear=False)
            logger.debug(f"Virtual environment created: {venv_path}")
        except Exception as e:
            logger.error(f"Failed to create venv: {e}")
            raise
    
    def _get_python_executable(self, venv_path: Path) -> str:
        """Get the Python executable path from a virtual environment"""
        if sys.platform == "win32":
            python_exe = venv_path / "Scripts" / "python.exe"
        else:
            python_exe = venv_path / "bin" / "python"
        
        if not python_exe.exists():
            raise FileNotFoundError(f"Python executable not found in venv: {python_exe}")
        
        return str(python_exe)
    
    def _install_dependencies(self, venv_path: Path, requirements: list, log: StructuredLogger) -> None:
        """
        Install dependencies in the virtual environment with graceful failure handling
        
        Args:
            venv_path: Path to virtual environment
            requirements: List of package requirements
            log: Structured logger instance
            
        Raises:
            DependencyInstallationError: If installation fails or times out
        """
        python_exe = self._get_python_executable(venv_path)
        
        for requirement in requirements:
            try:
                log.debug("dependency_installing", package=requirement)
                result = subprocess.run(
                    [python_exe, "-m", "pip", "install", "--quiet", requirement],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minutes timeout for installation
                )
                
                if result.returncode != 0:
                    log.warning("dependency_install_failed", 
                              package=requirement,
                              stderr=result.stderr,
                              returncode=result.returncode)
                    raise DependencyInstallationError(requirement, result.stderr)
                else:
                    log.debug("dependency_installed", package=requirement)
                    
            except subprocess.TimeoutExpired:
                log.error("dependency_install_timeout", package=requirement)
                raise DependencyInstallationError(requirement, "Installation timeout after 5 minutes", timeout=True)
            except DependencyInstallationError:
                # Re-raise our custom exception
                raise
            except Exception as e:
                log.error("dependency_install_error", 
                         package=requirement,
                         error=str(e),
                         error_type=type(e).__name__)
                raise DependencyInstallationError(requirement, str(e))
    
    def _install_dependencies_system(self, requirements: list, log: StructuredLogger) -> None:
        """
        Install dependencies to system/user site-packages with graceful failure handling
        
        Args:
            requirements: List of package requirements
            log: Structured logger instance
            
        Raises:
            DependencyInstallationError: If installation fails or times out
        """
        for requirement in requirements:
            try:
                log.debug("dependency_installing_system", package=requirement)
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--user", "--quiet", requirement],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                
                if result.returncode != 0:
                    log.warning("dependency_install_failed",
                              package=requirement,
                              stderr=result.stderr,
                              returncode=result.returncode)
                    raise DependencyInstallationError(requirement, result.stderr)
                else:
                    log.debug("dependency_installed_system", package=requirement)
                    
            except subprocess.TimeoutExpired:
                log.error("dependency_install_timeout", package=requirement)
                raise DependencyInstallationError(requirement, "Installation timeout after 5 minutes", timeout=True)
            except DependencyInstallationError:
                # Re-raise our custom exception
                raise
            except Exception as e:
                log.error("dependency_install_error",
                         package=requirement,
                         error=str(e),
                         error_type=type(e).__name__)
                raise DependencyInstallationError(requirement, str(e))
    
    def _execute_script(self, python_exe: str, script_file: Path, timeout: int) -> dict:
        """
        Execute a Python script and capture output
        
        Args:
            python_exe: Path to Python executable
            script_file: Path to script file
            timeout: Maximum execution time in seconds
            
        Returns:
            Dictionary with stdout, stderr, exit_code, and optional error
        """
        try:
            logger.debug(f"Running script: {script_file} with timeout {timeout}s")
            
            result = subprocess.run(
                [python_exe, str(script_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(script_file.parent),
            )
            
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
            }
            
        except subprocess.TimeoutExpired as e:
            logger.error(f"Script execution timeout after {timeout}s")
            return {
                "stdout": e.stdout.decode() if e.stdout else "",
                "stderr": e.stderr.decode() if e.stderr else "",
                "exit_code": 124,  # Standard timeout exit code
                "error": f"Execution timeout after {timeout} seconds",
            }
        except Exception as e:
            logger.error(f"Error executing script: {e}")
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": 1,
                "error": str(e),
            }
    
    def cleanup_cache(self, max_age_days: int = 7) -> None:
        """
        Clean up old cached environments
        
        Args:
            max_age_days: Maximum age in days for cached environments
        """
        try:
            import shutil
            
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            for item in self.cache_dir.iterdir():
                if item.is_dir():
                    # Check age
                    item_age = current_time - item.stat().st_mtime
                    
                    if item_age > max_age_seconds:
                        logger.info(f"Removing old cached environment: {item.name}")
                        shutil.rmtree(item, ignore_errors=True)
                        
        except Exception as e:
            logger.error(f"Error cleaning cache: {e}")
