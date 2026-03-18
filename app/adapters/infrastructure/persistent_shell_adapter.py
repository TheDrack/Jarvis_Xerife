# -*- coding: utf-8 -*-
"""PersistentShellAdapter — Terminal persistente com PTY (Devin-style).

Usa pseudo-terminal para manter bash vivo durante a sessão.
Detecta fim da execução via token de sincronia.
"""
import subprocess
import os
import select
import time
import logging
from typing import Dict, Any, Optional
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)


class PersistentShellAdapter(NexusComponent):
    """Adapter para terminal persistente com PTY."""
    
    def __init__(self):
        super().__init__()
        self._master_fd = None
        self._process = None
        self._delimiter = "---JARVIS_CMD_FINISH---"
        self._initialized = False
        self._timeout = int(os.getenv("SHELL_TIMEOUT", "30"))
    
    def configure(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Configura timeout via Pipeline YAML."""
        if config:
            self._timeout = config.get("timeout", self._timeout)
    
    def _initialize_shell(self) -> bool:
        """Inicia bash persistente com PTY."""
        if self._initialized:
            return True
        
        try:
            # Linux/Mac: usa PTY
            if os.name != "nt":
                self._master_fd, slave_fd = os.openpty()
                self._process = subprocess.Popen(
                    ['/bin/bash'],
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    preexec_fn=os.setsid,
                    env=os.environ
                )
                os.close(slave_fd)
                self._initialized = True
                logger.info("[PersistentShell] Bash iniciado com PTY")
                return True
            else:
                # Windows: fallback para subprocess normal
                logger.warning("[PersistentShell] Windows detectado — usando subprocess")
                self._initialized = True
                return True
                
        except Exception as e:
            logger.error(f"[PersistentShell] Erro ao inicializar: {e}")
            return False
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """NexusComponent entry-point."""
        config = context.get("current_config", {}) or context.get("config", {})
        command = config.get("command") or context.get("command", "")
        timeout = config.get("timeout", self._timeout)
        
        if not command:
            return {"success": False, "error": "Nenhum comando fornecido"}
        
        if not self._initialized:
            if not self._initialize_shell():
                return {"success": False, "error": "Falha ao inicializar shell"}
        
        # Windows fallback
        if os.name == "nt":
            return self._execute_windows(command, timeout)
        
        # Linux/Mac com PTY
        return self._execute_pty(command, timeout)
    
    def _execute_pty(self, command: str, timeout: int) -> Dict[str, Any]:
        """Executa comando via PTY com delimiter."""
        full_command = f"{command}; echo '{self._delimiter}'\n"
        
        try:
            os.write(self._master_fd, full_command.encode())
        except Exception as e:
            # Shell morreu — reinicializa
            logger.warning("[PersistentShell] Shell morto — reinicializando")
            self._initialized = False
            self._initialize_shell()
            return {"success": False, "error": f"Shell reinicializado: {e}"}
        
        output = ""
        start_time = time.time()
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.warning(f"[PersistentShell] Timeout após {timeout}s")
                return {
                    "success": False,
                    "output": output,
                    "error": f"Timeout após {timeout}s",
                    "timeout": True
                }
            
            try:
                r, _, _ = select.select([self._master_fd], [], [], 0.1)
                if self._master_fd in r:
                    data = os.read(self._master_fd, 4096).decode(errors='ignore')
                    output += data
                    
                    if self._delimiter in output:
                        # Limpa output
                        clean = output.replace(full_command.strip(), "")
                        clean = clean.replace(self._delimiter, "").strip()
                        logger.info(f"[PersistentShell] Comando executado: {command[:50]}...")
                        
                        return {"success": True, "output": clean, "command": command}
            except OSError as e:
                logger.error(f"[PersistentShell] Erro de leitura: {e}")
                return {"success": False, "error": str(e)}
            
            time.sleep(0.05)
        
        return {"success": False, "error": "Loop encerrou sem output"}
    
    def _execute_windows(self, command: str, timeout: int) -> Dict[str, Any]:
        """Fallback para Windows (sem PTY)."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='ignore'
            )
            output = result.stdout + result.stderr
            return {
                "success": result.returncode == 0,
                "output": output,
                "command": command,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Timeout após {timeout}s", "timeout": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Verifica pré-condições."""
        return True
