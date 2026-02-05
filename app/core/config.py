"""
Configuração do projeto.

Este módulo define as configurações do projeto, incluindo caminhos
para diretórios de assets, dados e arquivo de log.
"""
from pathlib import Path
from dotenv import load_dotenv


# Carrega variáveis de ambiente do arquivo .env (se existir)
load_dotenv()


class Settings:
    """
    Classe de configuração do projeto.
    
    Define os caminhos base do projeto e cria os diretórios necessários
    se não existirem.
    """
    
    # Define o caminho base do projeto (diretório raiz)
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    
    # Diretório para imagens
    ASSETS_DIR: Path = BASE_DIR / "assets" / "imagens"
    
    # Diretório para planilhas (CC, Materiais, Sites)
    DATA_DIR: Path = BASE_DIR / "data"
    
    # Arquivo de log
    LOG_FILE: Path = BASE_DIR / "logs" / "app.log"
    
    def __init__(self):
        """
        Inicializa a configuração e cria os diretórios necessários.
        """
        self._create_directories()
    
    def _create_directories(self) -> None:
        """
        Verifica se os diretórios necessários existem e os cria se necessário.
        """
        # Cria diretório de assets/imagens
        self.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Cria diretório de dados
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Cria diretório de logs
        self.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


# Instância singleton da configuração
settings = Settings()
