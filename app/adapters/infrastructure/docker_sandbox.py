# -*- coding: utf-8 -*-
"""DockerSandbox — Isola testes em containers Docker (Devin-style)."""
import logging
import tarfile
import io
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

try:
    import docker
    _DOCKER_AVAILABLE = True
except ImportError:
    _DOCKER_AVAILABLE = False


class DockerSandbox:
    """Sandbox de testes em container Docker."""
    
    def __init__(self, image: str = "python:3.11-slim"):
        self.image = image
        self.timeout_seconds = 120
        self.container = None
        self.client = None
        
        if _DOCKER_AVAILABLE:
            try:
                self.client = docker.from_env()
            except Exception as e:
                logger.warning(f"[DockerSandbox] Docker não disponível: {e}")
    
    def run_tests(self, code: str, test_file: str) -> Tuple[bool, str]:
        """Executa testes em container isolado."""
        if not self.client:
            return self._run_local_tests(code, test_file)
        
        try:
            self.container = self.client.containers.run(
                self.image,
                command="pytest /app/tests/ -v --tb=short",
                volumes={str(Path("/tmp").absolute()): {"bind": "/app", "mode": "rw"}},
                working_dir="/app",
                remove=True,
                detach=True,
                network_disabled=True,
                cap_drop=["ALL"],
                read_only=True,
                tmpfs={"/app": "rw,size=100m"},
            )
            
            self._inject_code(code, test_file)
            result = self.container.wait(timeout=self.timeout_seconds)
            logs = self.container.logs().decode("utf-8")
            
            self.container.remove(force=True)
            self.container = None
            
            success = result.get("StatusCode", 1) == 0
            return success, logs
            
        except Exception as e:
            logger.error(f"❌ [DockerSandbox] Erro: {e}")
            return False, str(e)
        finally:
            if self.container:
                try:
                    self.container.remove(force=True)
                except Exception:
                    pass
    
    def _inject_code(self, code: str, test_file: str) -> None:
        if not self.container:
            return
        
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            test_info = tarfile.TarInfo(name=test_file)
            test_info.size = len(code.encode('utf-8'))
            tar.addfile(test_info, io.BytesIO(code.encode('utf-8')))
        
        tar_stream.seek(0)
        self.container.put_archive("/app", tar_stream)
    
    def _run_local_tests(self, code: str, test_file: str) -> Tuple[bool, str]:
        """Fallback para execução local se Docker não disponível."""
        import subprocess
        try:
            result = subprocess.run(
                ["pytest", test_file, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)