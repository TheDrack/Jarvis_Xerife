# -*- coding: utf-8 -*-

import os
from typing import Set, Dict, Any
from app.core.interfaces import Interfaces as NexusComponent


class Consolidator(NexusComponent):
    def __init__(self):
        self.output_file = "CORE_LOGIC_CONSOLIDATED.txt"

        self.ignore_dirs: Set[str] = {
            ".git",
            "venv",
            "__pycache__",
            "tests",
            "build",
            "dist",
            "metabolism_logs",
        }

        self.ignore_files: Set[str] = {
            ".env",
            "credentials.json",
            self.output_file,
        }

        self.allowed_extensions: Set[str] = {
            ".py",
            ".json",
            ".yml",
            ".yaml",
            ".sh",
            ".sql",
        }

    def configure(self, config: dict):
        self.output_file = config.get(
            "output_file", self.output_file
        )

        # Garante que o próprio output não seja reimportado
        self.ignore_files.add(self.output_file)

    def can_execute(self) -> bool:
        return True

    def execute(self, context: Dict[str, Any]):
        """
        Entry-point oficial do Nexus / Pipeline
        """
        return self.consolidate()

    # ==========================
    # Lógica interna (reutilizável)
    # ==========================

    def consolidate(self) -> str:
        print(f"🔬 Consolidando projeto → {self.output_file}")

        with open(self.output_file, "w", encoding="utf-8") as out:
            out.write("### CONSOLIDAÇÃO DE SISTEMA - JARVIS ENTITY ###\n")
            out.write(f"### RAIZ: {os.getcwd()} ###\n\n")

            for root, dirs, files in os.walk("."):
                dirs[:] = [d for d in dirs if d not in self.ignore_dirs]

                for file in files:
                    if not file.endswith(tuple(self.allowed_extensions)):
                        continue
                    if file in self.ignore_files:
                        continue

                    path = os.path.join(root, file)
                    rel = os.path.relpath(path, ".")

                    out.write("\n" + "=" * 80 + "\n")
                    out.write(f" FILE: {rel}\n")
                    out.write("=" * 80 + "\n\n")

                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            out.write(f.read())
                    except Exception as e:
                        out.write(f"[ERRO] {e}\n")

                    out.write(f"\n--- FIM DO ARQUIVO: {rel} ---\n")

        print("✅ Consolidação concluída")
        return self.output_file