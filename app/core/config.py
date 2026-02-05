# -*- coding: utf-8 -*-
"""
Módulo de configuração do aplicativo.

Este módulo contém a classe Settings que gerencia as configurações
do aplicativo, incluindo caminhos para recursos como imagens.
"""

import os


class Settings:
    """
    Classe de configuração para o aplicativo.
    
    Gerencia as configurações globais do aplicativo, incluindo
    caminhos para recursos utilizados nas automações.
    """
    
    def __init__(self):
        """
        Inicializa as configurações com valores padrão.
        """
        # Caminho padrão para as imagens utilizadas na automação de interface
        self.imagens_path = r'C:\Users\jesus.anhaia\OneDrive\Documentos\GitHub\ServicoAutomatico\imagens'
        
        # Tempo de espera padrão para localizar imagens na tela (em segundos)
        self.tempo_espera_localizacao = 7.5
    
    def get_imagens_path(self):
        """
        Retorna o caminho configurado para o diretório de imagens.
        
        Returns:
            str: Caminho completo para o diretório de imagens.
        """
        return self.imagens_path
    
    def set_imagens_path(self, path):
        """
        Define um novo caminho para o diretório de imagens.
        
        Args:
            path (str): Novo caminho para o diretório de imagens.
        """
        self.imagens_path = path
    
    def get_tempo_espera_localizacao(self):
        """
        Retorna o tempo de espera configurado para localização de imagens.
        
        Returns:
            float: Tempo de espera em segundos.
        """
        return self.tempo_espera_localizacao
    
    def set_tempo_espera_localizacao(self, tempo):
        """
        Define um novo tempo de espera para localização de imagens.
        
        Args:
            tempo (float): Tempo de espera em segundos.
        """
        self.tempo_espera_localizacao = tempo


# Instância global de configurações
settings = Settings()
