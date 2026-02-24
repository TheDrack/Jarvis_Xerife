import os
import re
from pathlib import Path

def fix_build_config():
    print("="*60)
    print("[PROTOCOLO JARVIS] CORRIGINDO CONFIGURAÇÃO DE BUILD")
    print("="*60)

    build_script = Path("build_config.py")

    if not build_script.exists():
        print("[ERRO] build_config.py não encontrado na raiz.")
        return

    content = build_script.read_text(encoding='utf-8')

    # 1. Atualiza o caminho do script principal
    # Procura por referências a main.py e atualiza para o novo caminho hexagonal
    old_main = "main.py"
    new_main = "app/application/services/main.py"

    if old_main in content and new_main not in content:
        content = content.replace(f"'{old_main}'", f"'{new_main}'")
        content = content.replace(f'"{old_main}"', f'"{new_main}"')
        print(f"[OK] Entry point atualizado: {new_main}")

    # 2. Injeta o PATH do pacote 'app' para o PyInstaller
    # Isso resolve os erros de 'ModuleNotFoundError' durante a compilação
    if "--paths" not in content:
        # Tenta injetar o argumento --paths=. nos comandos do PyInstaller dentro do script
        content = re.sub(
            r"(pyinstaller|PyInstaller\.render\()", 
            r"\1 --paths=.", 
            content
        )
        print("[OK] Argumento --paths=. injetado para reconhecimento do pacote 'app'")

    build_script.write_text(content, encoding='utf-8')
    print("[SUCESSO] build_config.py está pronto para a nova estrutura.")

def check_structure():
    """Verifica se os arquivos essenciais estão nos lugares certos antes do build"""
    essential_files = [
        "app/application/services/main.py",
        "app/application/containers/hub.py",
        "app/domain/models/system_state.py"
    ]

    for f in essential_files:
        if Path(f).exists():
            print(f"[VERIFICADO] Arquivo presente: {f}")
        else:
            print(f"[ALERTA] Arquivo não encontrado: {f}")

if __name__ == "__main__":
    fix_build_config()
    check_structure()
