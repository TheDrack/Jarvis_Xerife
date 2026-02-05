#-*- coding:utf-8 -*-
"""
Command Processor for the voice assistant.
This module contains the CommandProcessor class that maps command strings
to their corresponding action functions.
"""
from app.actions.gui_commands import (
    falar,
    digitar,
    aperta,
    abrirgaveta,
    clicarNaNet,
    abrirInternet
)
from app.actions.business_logic import (
    FazerRequisicaoSulfite,
    FazerRequisicaoPT1,
    AbrirPlanilha,
    AtualizarInventario,
    ImprimirBalancete,
    AbrirAlmox,
    Cod4rMaterial,
    QuantMaterial,
    ConsultarEstoque,
    abrirsite
)


class CommandProcessor:
    """
    Process voice commands by mapping command strings to action functions.
    
    This class replaces the old TuplaDeComandos tuple-based approach with
    a more organized dictionary-based command mapping system.
    """
    
    def __init__(self):
        """
        Initialize the CommandProcessor with a dictionary mapping
        command strings to their corresponding action functions.
        """
        self.comandos = {
            'sulfite': FazerRequisicaoSulfite,
            'requisição': FazerRequisicaoPT1,
            'planilha': AbrirPlanilha,
            'inventário': AtualizarInventario,
            'balancete': ImprimirBalancete,
            'almoxarifado': AbrirAlmox,
            'digitar produto': Cod4rMaterial,
            'digitar quantidade': QuantMaterial,
            'gaveta': abrirgaveta,
            'escreva': digitar,
            'aperte': aperta,
            'falar': falar,
            'internet': abrirInternet,
            'estoque': ConsultarEstoque,
            'site': abrirsite,
            'clicar em': clicarNaNet
        }
    
    def execute(self, comando: str):
        """
        Execute a command by identifying the correct action and running it.
        
        Args:
            comando (str): The command string to execute
            
        Returns:
            The result of the executed action, or None if no matching command found
        """
        # Iterate through registered commands to find a match
        for cmd_key, acao in self.comandos.items():
            if cmd_key in comando:
                # Remove the command keyword from the string to get parameters
                # Use replace with count=1 and strip to handle edge cases
                parametro = comando.replace(cmd_key, '', 1).strip()
                # Execute the action with the parameter
                return acao(parametro)
        
        # If no command matched, return None
        return None
