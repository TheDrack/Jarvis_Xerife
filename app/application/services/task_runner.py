# -*- coding: utf-8 -*-
"""TaskRunner - Ephemeral script execution service for distributed workers"""

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
    
    def __init__(self, cache_dir: Optional[Path] = None, use_venv: bool = True):
        """
        Initialize the TaskRunner
        
        Args:
            cache_dir: Optional directory for caching libraries and environments
            use_venv: Whether to use virtual environments (default: True)
        """
        self.use_venv = use_venv
        
        # Setup cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(tempfile.gettempdir()) / "jarvis_task_cache"
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"TaskRunner initialized with cache directory: {self.cache_dir}")
    
    def execute_mission(self, mission: Mission) -> MissionResult:
        """
        Execute a mission with the provided code and dependencies
        
        Args:
            mission: Mission object containing code and configuration
            
        Returns:
            MissionResult with execution outcome
        """
        start_time = time.time()
        mission_id = mission.mission_id
        
        logger.info(f"Starting mission execution: {mission_id}")
        logger.debug(f"Mission details - Requirements: {mission.requirements}, "
                    f"Browser: {mission.browser_interaction}, Keep-alive: {mission.keep_alive}")
        
        # Create temporary script file
        script_file = None
        venv_path = None
        
        try:
            # Create temporary directory for this mission
            temp_dir = Path(tempfile.mkdtemp(prefix=f"mission_{mission_id}_"))
            script_file = temp_dir / "script.py"
            
            # Write script to file
            script_file.write_text(mission.code)
            logger.debug(f"Script written to: {script_file}")
            
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
                    logger.info(f"Creating virtual environment at: {venv_path}")
                    self._create_venv(venv_path)
                else:
                    logger.info(f"Using existing virtual environment: {venv_path}")
                
                # Install dependencies if any
                if mission.requirements:
                    logger.info(f"Installing {len(mission.requirements)} dependencies")
                    self._install_dependencies(venv_path, mission.requirements)
                
                # Get Python executable from venv
                python_exe = self._get_python_executable(venv_path)
            else:
                # Use system Python
                python_exe = sys.executable
                
                # Install dependencies to user site-packages if needed
                if mission.requirements:
                    logger.info(f"Installing {len(mission.requirements)} dependencies to user site")
                    self._install_dependencies_system(mission.requirements)
            
            # Execute the script
            logger.info(f"Executing script with Python: {python_exe}")
            result = self._execute_script(python_exe, script_file, mission.timeout)
            
            execution_time = time.time() - start_time
            logger.info(f"Mission {mission_id} completed in {execution_time:.2f}s "
                       f"with exit code {result['exit_code']}")
            
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
            execution_time = time.time() - start_time
            logger.error(f"Mission {mission_id} failed: {e}", exc_info=True)
            
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
    
    def _install_dependencies(self, venv_path: Path, requirements: list) -> None:
        """Install dependencies in the virtual environment"""
        python_exe = self._get_python_executable(venv_path)
        
        for requirement in requirements:
            try:
                logger.debug(f"Installing: {requirement}")
                result = subprocess.run(
                    [python_exe, "-m", "pip", "install", "--quiet", requirement],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minutes timeout for installation
                )
                
                if result.returncode != 0:
                    logger.warning(f"Failed to install {requirement}: {result.stderr}")
                else:
                    logger.debug(f"Successfully installed: {requirement}")
                    
            except subprocess.TimeoutExpired:
                logger.error(f"Timeout installing {requirement}")
                raise
            except Exception as e:
                logger.error(f"Error installing {requirement}: {e}")
                raise
    
    def _install_dependencies_system(self, requirements: list) -> None:
        """Install dependencies to system/user site-packages"""
        for requirement in requirements:
            try:
                logger.debug(f"Installing to user site: {requirement}")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--user", "--quiet", requirement],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                
                if result.returncode != 0:
                    logger.warning(f"Failed to install {requirement}: {result.stderr}")
                else:
                    logger.debug(f"Successfully installed: {requirement}")
                    
            except Exception as e:
                logger.error(f"Error installing {requirement}: {e}")
                raise
    
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
