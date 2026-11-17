import os
import re


def extract_signatures(file_path):
    """Extract a small set of public class/function names for the module map."""
    signatures = []
    try:
        with open(file_path, "r", encoding="utf-8") as source:
            content = source.read()
            found = re.findall(r"class\s+(\w+)|def\s+(\w+)\s*\(", content)
            for item in found[:3]:
                name = item[0] if item[0] else item[1]
                if not name.startswith("_"):
                    signatures.append(name)
    except (OSError, UnicodeError):
        pass
    return signatures


def generate_jarvis_graph(root_dir):
    """Generate a source-oriented directory map, excluding archives and runtime data."""
    header = "# Jarvis Xerife — mapa de módulos (gerado automaticamente)\n"
    header += "> Diretórios e assinaturas encontrados no checkout. Este mapa não representa "
    header += "status de execução, disponibilidade ou autorização.\n\n"
    header += "```mermaid\ngraph LR\n"
    header += "    classDef core fill:#1a1f25,stroke:#00ff00,color:#fff,stroke-width:2px;\n"
    header += "    classDef adapter fill:#1a1f25,stroke:#007bff,color:#fff;\n"
    header += "    classDef port fill:#1a1f25,stroke:#ffa500,color:#fff,stroke-dasharray: 5 5;\n"
    header += "    classDef support fill:#2d333b,stroke:#6c757d,color:#aaa;\n"

    # These trees are archives, generated/runtime state, local harness config,
    # dependencies, or documentation—not active source modules.
    exclude = {
        ".git", ".github", ".agents", ".backups", "backups", "archive",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        ".venv", "venv", "node_modules", "dist", "build",
        "data", "docs", "tests", "scripts",
    }

    body = ""
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = sorted(d for d in dirs if d not in exclude)
        rel_path = os.path.relpath(root, root_dir)
        if rel_path == ".":
            continue

        folder_name = os.path.basename(root)
        node_id = rel_path.replace(os.sep, "_").replace(".", "_")
        path_lower = rel_path.lower()
        if "core" in path_lower:
            style = "core"
        elif "adapters" in path_lower:
            style = "adapter"
        elif "ports" in path_lower:
            style = "port"
        else:
            style = "support"

        contracts = []
        for filename in sorted(files):
            if filename.endswith(".py") and filename != "__init__.py":
                signatures = extract_signatures(os.path.join(root, filename))
                if signatures:
                    contracts.append(f"📄 {filename}: {', '.join(signatures)}")

        label = f"<b>{folder_name}</b>"
        if contracts:
            label += "<br/><hr/>" + "<br/>".join(contracts)

        body += f'    {node_id}["{label}"]\n'
        body += f"    class {node_id} {style}\n"

        parent_dir = os.path.dirname(rel_path)
        if parent_dir and parent_dir != ".":
            parent_id = parent_dir.replace(os.sep, "_").replace(".", "_")
            body += f"    {parent_id} --> {node_id}\n"

    return header + body + "```\n"


if __name__ == "__main__":
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    output_file = os.path.join(base_path, "docs", "ARQUIVO_MAP.md")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    print(f"Scanning active source directories in: {base_path}")
    markdown_content = generate_jarvis_graph(base_path)

    with open(output_file, "w", encoding="utf-8") as output:
        output.write(markdown_content)

    print(f"Generated module map: {output_file}")
