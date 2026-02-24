# -*- coding: utf-8 -*-
"""Mission models - Task execution payloads for distributed workers"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class Mission:
    """
    Represents a serverless task execution mission sent to a Worker
    """
    mission_id: str
    code: str
    requirements: List[str] = field(default_factory=list)
    browser_interaction: bool = False
    keep_alive: bool = False
    target_device_id: Optional[int] = None
    timeout: int = 300
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "code": self.code,
            "requirements": self.requirements,
            "browser_interaction": self.browser_interaction,
            "keep_alive": self.keep_alive,
            "target_device_id": self.target_device_id,
            "timeout": self.timeout,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Mission":
        return cls(
            mission_id=data["mission_id"],
            code=data["code"],
            requirements=data.get("requirements", []),
            browser_interaction=data.get("browser_interaction", False),
            keep_alive=data.get("keep_alive", False),
            target_device_id=data.get("target_device_id"),
            timeout=data.get("timeout", 300),
            metadata=data.get("metadata", {}),
        )

@dataclass
class MissionResult:
    """
    Represents the result of a mission execution
    """
    mission_id: str
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "execution_time": self.execution_time,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MissionResult":
        return cls(
            mission_id=data["mission_id"],
            success=data["success"],
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            exit_code=data.get("exit_code", 0),
            execution_time=data.get("execution_time", 0.0),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )

# O Nexus agora encontrará a classe 'Mission' diretamente pelo nome do arquivo.
