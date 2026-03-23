import os
import re

def extract_signatures(file_path):
    """Extrai classes e métodos principais para documentar o contrato."""
    signatures = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Captura classes e funções principais (limite de 3 para não poluir o gráfico)
            found = re.findall(r"class\s+(\w+)|def\s+(\w+)\s*\(", content)
            for item in found[:3]:
                name = item[0] if item[0] else item[1]
                if not name.startswith("_"): # Ignora membros privados
                    signatures.append(name)
    except Exception:
        pass
    return signatures

def generate_jarvis_graph(root_dir):
    header = "# 🏗️ JARVIS_Xerife: Mapa de Arquitetura Dinâmico\n"
    header += "> **Protocolo de Simbiose:** Documentação gerada via análise de código real.\n\n"
    header += "```mermaid\ngraph LR\n"
    
    # Estilização visual das camadas
    header += "    classDef core fill:#1a1f25,stroke:#00ff00,color:#fff,stroke-width:2px;\n"
    header += "    classDef adapter fill:#1a1f25,stroke:#007bff,color:#fff;\n"
    header += "    classDef port fill:#1a1f25,stroke:#ffa500,color:#fff,stroke-dasharray: 5 5;\n"
    header += "    classDef support fill:#2d333b,stroke:#6c757d,color:#aaa;\n"

    body = ""
    exclude = {'.git', '__pycache__', 'venv', 'node_modules', '.github', 'tests', 'scripts'}
    
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in exclude]
        rel_path = os.path.relpath(root, root_dir)
        if rel_path == ".": continue
        
        folder_name = os.path.basename(root)
        node_id = rel_path.replace(os.sep, '_').replace('.', '_')
        
        # Identificação de Camada para Estilo
        path_lower = rel_path.lower()
        if "core" in path_lower:
            style = "core"
        elif "adapters" in path_lower:
            style = "adapter"
        elif "ports" in path_lower:
            style = "port"
        else:
            style = "support"
        
        # Analisar ficheiros para extrair assinaturas do Nexus
        contracts = []
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                sigs = extract_signatures(os.path.join(root, file))
                if sigs:
                    contracts.append(f"📄 {file}: {', '.join(sigs)}")

        # Formatação do Nó com HTML para o Mermaid
        label = f"<b>{folder_name}</b>"
        if contracts:
            label += "<br/><hr/>" + "<br/>".join(contracts)

        body += f"    {node_id}[\"{label}\"]\n"
        body += f"    class {node_id} {style}\n"
        
        # Conexão hierárquica (Pai -> Filho)
        parent_dir = os.path.dirname(rel_path)
        if parent_dir and parent_dir != ".":
            parent_id = parent_dir.replace(os.sep, '_').replace('.', '_')
            body += f"    {parent_id} --> {node_id}\n"

    return header + body + "```\n"

if __name__ == "__main__":
    # Como o script está em /scripts, subimos um nível para a raiz do projeto
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    output_file = os.path.join(base_path, "ARCHITECTURE.md")
    
    print(f"🔍 Analisando projeto em: {base_path}")
    markdown_content = generate_jarvis_graph(base_path)
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    
    print(f"🚀 [JARVIS] Arquitetura exportada para: {output_file}")
