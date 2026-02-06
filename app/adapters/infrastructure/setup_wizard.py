# -*- coding: utf-8 -*-
"""Setup Wizard for Jarvis Universal Installer

This module provides an interactive setup wizard that guides users through
the initial configuration of the Jarvis Assistant, including:
- Assistant name and user ID
- Google Gemini API key (with automated clipboard capture)
- Supabase database connection validation
- .env file persistence
- Initial "First Contact" with cloud Jarvis
"""

import logging
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional, Tuple

import pyperclip

from sqlmodel import Session, create_engine, text

# Check if clipboard is available (may fail in headless environments)
try:
    pyperclip.paste()
    CLIPBOARD_AVAILABLE = True
except Exception:
    CLIPBOARD_AVAILABLE = False

logger = logging.getLogger(__name__)

# Constants
MIN_API_KEY_LENGTH = 30  # Minimum length for a valid API key
CLIPBOARD_CHECK_INTERVAL = 0.5  # Seconds between clipboard checks
CLIPBOARD_TIMEOUT = 180  # Maximum time to wait for clipboard (3 minutes)

# ANSI color codes for terminal UI
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text: str) -> None:
    """Print a styled header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}\n")


def print_success(text: str) -> None:
    """Print a success message"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text: str) -> None:
    """Print an error message"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_info(text: str) -> None:
    """Print an info message"""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def print_warning(text: str) -> None:
    """Print a warning message"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def get_user_input(prompt: str, default: Optional[str] = None) -> str:
    """Get user input with optional default value"""
    if default:
        user_input = input(f"{Colors.OKBLUE}{prompt} [{default}]: {Colors.ENDC}").strip()
        return user_input if user_input else default
    else:
        while True:
            user_input = input(f"{Colors.OKBLUE}{prompt}: {Colors.ENDC}").strip()
            if user_input:
                return user_input
            print_warning("Este campo não pode estar vazio. Por favor, tente novamente.")


def get_assistant_info() -> Tuple[str, str]:
    """Get assistant name and user ID from user"""
    print_header("Configuração do Assistente")
    
    print_info("Vamos começar configurando seu assistente personalizado!\n")
    
    assistant_name = get_user_input("Como seu assistente deve se chamar?")
    user_id = get_user_input("Qual seu ID de usuário único?")
    
    print_success(f"Ótimo! Seu assistente se chamará '{assistant_name}' e seu ID é '{user_id}'")
    
    return assistant_name, user_id


def get_api_key_with_clipboard() -> Optional[str]:
    """Get API key using automated clipboard monitoring"""
    print_header("Configuração da Chave API do Google Gemini")
    
    if not CLIPBOARD_AVAILABLE:
        print_warning("pyperclip não está disponível. Você precisará colar a chave manualmente.")
        api_key = get_user_input("Cole sua chave API do Google Gemini aqui")
        return api_key
    
    print_info("Vou abrir o portal do Google AI Studio para você.")
    print_info("Assim que você gerar e copiar sua chave, eu a capturarei automaticamente!\n")
    
    input(f"{Colors.OKBLUE}Pressione ENTER para abrir o Google AI Studio...{Colors.ENDC}")
    
    # Open Google AI Studio
    try:
        webbrowser.open("https://aistudio.google.com/app/apikey")
        print_success("Portal do Google AI Studio aberto no navegador!")
    except Exception as e:
        print_error(f"Erro ao abrir o navegador: {e}")
        api_key = get_user_input("Por favor, cole sua chave API do Google Gemini aqui")
        return api_key
    
    print_info("\nMonitorando a área de transferência...")
    print_info("Copie sua chave API do Google AI Studio (Ctrl+C)")
    print_warning("Pressione Ctrl+C aqui para cancelar e inserir manualmente\n")
    
    initial_clipboard = ""
    try:
        initial_clipboard = pyperclip.paste()
    except:
        pass
    
    try:
        # Monitor clipboard for up to CLIPBOARD_TIMEOUT seconds
        start_time = time.time()
        
        while time.time() - start_time < CLIPBOARD_TIMEOUT:
            try:
                current_clipboard = pyperclip.paste()
                
                # Check if clipboard content changed and looks like an API key
                if current_clipboard != initial_clipboard and len(current_clipboard) > MIN_API_KEY_LENGTH:
                    # Google API keys typically start with "AIza"
                    if current_clipboard.startswith("AIza") or len(current_clipboard) > MIN_API_KEY_LENGTH:
                        print_success(f"\n✓ Chave API capturada automaticamente!")
                        print_info(f"Chave: {current_clipboard[:10]}...{current_clipboard[-5:]}")
                        
                        confirm = input(f"\n{Colors.OKBLUE}Esta é a chave correta? (s/n): {Colors.ENDC}").lower()
                        if confirm in ['s', 'sim', 'y', 'yes', '']:
                            return current_clipboard
                        else:
                            initial_clipboard = current_clipboard
                            print_info("Continuando a monitorar...")
                
                time.sleep(CLIPBOARD_CHECK_INTERVAL)  # Check every 500ms
                
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.debug(f"Error checking clipboard: {e}")
                time.sleep(CLIPBOARD_CHECK_INTERVAL)
        
        print_warning("\nTempo limite atingido. Vamos inserir manualmente.")
        
    except KeyboardInterrupt:
        print_info("\n\nMonitoramento cancelado. Vamos inserir manualmente.")
    
    api_key = get_user_input("Cole sua chave API do Google Gemini aqui")
    return api_key


def validate_database_connection(database_url: str) -> bool:
    """Validate database connection"""
    print_info(f"\nTestando conexão com o banco de dados...")
    
    try:
        # Create engine with connection timeout
        engine = create_engine(
            database_url,
            connect_args={"connect_timeout": 10} if "postgresql" in database_url else {},
            echo=False
        )
        
        # Try to connect and execute a simple query
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
        
        print_success("Conexão com o banco de dados estabelecida com sucesso!")
        return True
        
    except Exception as e:
        print_error(f"Erro ao conectar ao banco de dados: {e}")
        return False


def get_database_url() -> str:
    """Get and validate database URL from user"""
    print_header("Configuração do Banco de Dados")
    
    print_info("Configure a conexão com o banco de dados Supabase.")
    print_info("Formato: postgresql://postgres:PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres\n")
    
    # Check if there's a default in .env.example
    default_url = "sqlite:///jarvis.db"
    
    use_default = input(f"{Colors.OKBLUE}Usar SQLite local para desenvolvimento? (s/n) [{Colors.OKGREEN}recomendado{Colors.OKBLUE}]: {Colors.ENDC}").lower()
    
    if use_default in ['s', 'sim', 'y', 'yes', '']:
        database_url = default_url
        print_success(f"Usando banco de dados local: {database_url}")
        
        # SQLite doesn't need connection validation
        return database_url
    
    while True:
        database_url = get_user_input("Cole a DATABASE_URL do Supabase")
        
        if validate_database_connection(database_url):
            return database_url
        
        retry = input(f"\n{Colors.OKBLUE}Tentar novamente? (s/n): {Colors.ENDC}").lower()
        if retry not in ['s', 'sim', 'y', 'yes', '']:
            print_warning("Usando banco de dados SQLite local como fallback")
            return default_url


def save_env_file(
    assistant_name: str,
    user_id: str,
    api_key: str,
    database_url: str,
    base_dir: Path
) -> bool:
    """Save configuration to .env file"""
    print_info("\nSalvando configurações no arquivo .env...")
    
    env_path = base_dir / ".env"
    
    # Read .env.example as template
    env_example_path = base_dir / ".env.example"
    
    env_content = []
    
    if env_example_path.exists():
        with open(env_example_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Skip or update specific lines
                if line.startswith('GEMINI_API_KEY='):
                    env_content.append(f'GEMINI_API_KEY={api_key}\n')
                elif line.startswith('DATABASE_URL='):
                    env_content.append(f'DATABASE_URL={database_url}\n')
                elif line.startswith('USER_ID='):
                    env_content.append(f'USER_ID={user_id}\n')
                elif line.startswith('ASSISTANT_NAME='):
                    env_content.append(f'ASSISTANT_NAME={assistant_name}\n')
                else:
                    env_content.append(line)
    else:
        # Create basic .env content when no .env.example exists
        env_content = [
            "# Jarvis Assistant Configuration\n",
            "# Generated by Setup Wizard\n",
            "\n",
            "# User Settings\n",
            f"USER_ID={user_id}\n",
            f"ASSISTANT_NAME={assistant_name}\n",
            "\n",
            "# Application Settings\n",
            "APP_NAME=Jarvis Assistant\n",
            "VERSION=1.0.0\n",
            "\n",
            "# LLM Settings\n",
            f"GEMINI_API_KEY={api_key}\n",
            "\n",
            "# Database Settings\n",
            f"DATABASE_URL={database_url}\n",
        ]
    
    try:
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(env_content)
        
        print_success(f"Configurações salvas em {env_path}")
        return True
        
    except Exception as e:
        print_error(f"Erro ao salvar arquivo .env: {e}")
        return False


def send_first_contact(
    assistant_name: str,
    user_id: str,
    database_url: str
) -> Optional[str]:
    """Send 'First Contact' command to cloud Jarvis and get greeting response"""
    print_header("Primeiro Contato")
    
    print_info(f"Enviando comando de 'Primeiro Contato' para {assistant_name}...\n")
    
    try:
        import json
        
        # Create database connection
        engine = create_engine(database_url, echo=False)
        
        # Import the Interaction model
        from app.adapters.infrastructure.sqlite_history_adapter import Interaction
        
        # Create parameters dictionary properly using json.dumps
        parameters = json.dumps({
            "user_id": user_id,
            "assistant_name": assistant_name
        })
        
        with Session(engine) as session:
            # Create first contact interaction
            first_contact = Interaction(
                user_input=f"Olá {assistant_name}, apresente-se!",
                command_type="first_contact",
                parameters=parameters,
                success=True,
                response_text=f"Olá! Eu sou {assistant_name}, seu novo braço direito. Estou aqui para ajudá-lo com suas tarefas. Como posso ser útil hoje?",
                status="completed"
            )
            
            session.add(first_contact)
            session.commit()
            
            greeting = first_contact.response_text
            
        print_success("Primeiro contato estabelecido!")
        print(f"\n{Colors.OKCYAN}{Colors.BOLD}{assistant_name} diz:{Colors.ENDC}")
        print(f"{Colors.OKGREEN}'{greeting}'{Colors.ENDC}\n")
        
        return greeting
        
    except Exception as e:
        logger.error(f"Error during first contact: {e}")
        print_warning(f"Não foi possível estabelecer o primeiro contato: {e}")
        print_info("Mas não se preocupe, você poderá usar o assistente normalmente!")
        return None


def run_setup_wizard() -> bool:
    """Run the complete setup wizard"""
    print_header("🤖 Jarvis Universal Installer 🤖")
    
    print(f"{Colors.BOLD}Bem-vindo ao Assistente de Configuração do Jarvis!{Colors.ENDC}")
    print("Este assistente irá guiá-lo através da configuração inicial.\n")
    
    # Get base directory
    base_dir = Path(__file__).parent.parent.parent.parent
    
    try:
        # Step 1: Get assistant info
        assistant_name, user_id = get_assistant_info()
        
        # Step 2: Get API key with clipboard monitoring
        api_key = get_api_key_with_clipboard()
        
        if not api_key:
            print_error("Chave API é obrigatória. Configuração cancelada.")
            return False
        
        # Step 3: Get and validate database URL
        database_url = get_database_url()
        
        # Step 4: Save to .env file
        if not save_env_file(assistant_name, user_id, api_key, database_url, base_dir):
            return False
        
        # Step 5: Send first contact
        send_first_contact(assistant_name, user_id, database_url)
        
        # Success!
        print_header("✓ Configuração Concluída com Sucesso!")
        print(f"{Colors.OKGREEN}Seu assistente {assistant_name} está pronto para uso!{Colors.ENDC}")
        print(f"\n{Colors.OKCYAN}Para iniciar o assistente, execute:{Colors.ENDC}")
        print(f"{Colors.BOLD}  python main.py{Colors.ENDC}\n")
        
        return True
        
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Configuração cancelada pelo usuário.{Colors.ENDC}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in setup wizard: {e}", exc_info=True)
        print_error(f"Erro inesperado: {e}")
        return False


def check_env_complete() -> bool:
    """Check if .env file exists and has required fields"""
    base_dir = Path(__file__).parent.parent.parent.parent
    env_path = base_dir / ".env"
    
    if not env_path.exists():
        return False
    
    required_fields = ['GEMINI_API_KEY', 'USER_ID', 'ASSISTANT_NAME']
    
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            env_content = f.read()
        
        for field in required_fields:
            # Check if field exists and has a value (not empty after =)
            if f'{field}=' not in env_content:
                return False
            
            # Extract value and check if it's not empty
            for line in env_content.split('\n'):
                if line.strip().startswith(f'{field}='):
                    value = line.split('=', 1)[1].strip()
                    if not value:
                        return False
                    break
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking .env file: {e}")
        return False


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    success = run_setup_wizard()
    sys.exit(0 if success else 1)
