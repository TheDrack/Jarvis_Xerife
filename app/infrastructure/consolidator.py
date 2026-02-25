# -*- coding: utf-8 -*-
import os
from datetime import datetime
from typing import Set, Dict, Any
from app.core.nexuscomponent import NexusComponent

class Consolidator(NexusComponent):
    def __init__(self):
        self.output_file = "CORE_LOGIC_CONSOLIDATED.txt"
        self.ignore_dirs: Set[str] = {".git", "venv", "__pycache__", "tests", "build", "dist"}
        self.ignore_files: Set[str] = {".env", "credentials.json"}
        self.allowed_extensions: Set[str] = {".py", ".json", ".yml", ".yaml", ".sh", ".sql"}

    def configure(self, config: dict):
        self.output_file = config.get("output_file", self.output_file)
        self.ignore_files.add(self.output_file)

    def execute(self, context: Dict[str, Any]) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"🔬 [NEXUS] Iniciando Consolidação: {timestamp}")

        with open(self.output_file, "w", encoding="utf-8") as out:
            out.write("=" * 80 + "\n")
            out.write(f"### JARVIS SYSTEM CONSOLIDATION ###\n")
            out.write(f"### LAST UPDATE: {timestamp} ###\n")
            out.write(f"### WORKSPACE: {os.getcwd()} ###\n")
            out.write("=" * 80 + "\n\n")

            for root, dirs, files in os.walk("."):
                dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
                for file in files:
                    if not file.endswith(tuple(self.allowed_extensions)) or file in self.ignore_files:
                        continue
                    
                    path = os.path.join(root, file)
                    rel = os.path.relpath(path, ".")
                    out.write(f"\n--- INÍCIO: {rel} ---\n")
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            out.write(f.read())
                    except Exception as e:
                        out.write(f"[ERRO] {e}\n")
                    out.write(f"\n--- FIM: {rel} ---\n")

        print(f"✅ [NEXUS] Arquivo gerado: {self.output_file}")
        return self.output_file
