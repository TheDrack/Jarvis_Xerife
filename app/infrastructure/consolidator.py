# -*- coding: utf-8 -*-

import os
from typing import Set


class Consolidator:
    """
    Consolida o projeto em um único arquivo de texto,
    preservando o caminho completo de cada arquivo.
    """

    def __init__(
        self,
        output_file: str = "CORE_LOGIC_CONSOLIDATED.txt",
    ):
        self.output_file = output_file

        # Filtros de segurança e foco
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
            self.output_file,
            ".env",
            "credentials.json",
        }

        self.allowed_extensions: Set[str] = {
            ".py",
            ".json",
            ".yml",
            ".yaml",
            ".sh",
            ".sql",
        }

    def consolidate(self) -> str:
        """
        Varre o repositório e gera um arquivo único
        contendo todos os arquivos permitidos.
        """

        print(f"🔬 JARVIS: Iniciando consolidação em '{self.output_file}'...")

        with open(self.output_file, "w", encoding="utf-8") as out:
            # Cabeçalho de integridade
            out.write("### CONSOLIDAÇÃO DE SISTEMA - JARVIS ENTITY ###\n")
            out.write(f"### RAIZ: {os.getcwd()} ###\n\n")

            for root, dirs, files in os.walk("."):
                # Remove diretórios ignorados (in-place)
                dirs[:] = [d for d in dirs if d not in self.ignore_dirs]

                for filename in files:
                    file_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(file_path, ".")

                    # Valida extensão e arquivos ignorados
                    if (
                        filename.endswith(tuple(self.allowed_extensions))
                        and filename not in self.ignore_files
                    ):
                        out.write("\n" + "=" * 80 + "\n")
                        out.write(f" FILE: {rel_path}\n")
                        out.write("=" * 80 + "\n\n")

                        try:
                            with open(file_path, "r", encoding="utf-8") as content:
                                out.write(content.read())
                        except Exception as exc:
                            out.write(
                                f"[!] ERRO AO LER {rel_path}: {str(exc)}\n"
                            )

                        out.write(
                            f"\n\n--- FIM DO ARQUIVO: {rel_path} ---\n"
                        )

        print("✅ Consolidação finalizada com sucesso.")
        return self.output_file


# ==========================
# Ponto de entrada (CI / CLI)
# ==========================

def main():
    consolidator = Consolidator()
    consolidator.consolidate()


if __name__ == "__main__":
    main()