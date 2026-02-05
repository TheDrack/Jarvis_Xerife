# -*- coding: utf-8 -*-
"""
Módulo de comandos de automação de interface gráfica.

Este módulo contém funções para automatizar interações com a interface
gráfica do usuário, incluindo digitação, pressionamento de teclas,
localização de elementos na tela e cliques.
"""

from pynput.keyboard import Controller
import pyautogui
import time
import os
from app.core.config import settings


def digitar(texto):
    """
    Digita um texto utilizando o teclado virtual.
    
    Esta função simula a digitação de texto no campo atualmente focado,
    utilizando o controlador de teclado do pynput.
    
    Args:
        texto (str): O texto a ser digitado.
    
    Example:
        >>> digitar("Olá mundo")
        # Digita "Olá mundo" no campo focado
    """
    Controller().type(texto)


def aperta(botao):
    """
    Pressiona uma ou mais teclas do teclado.
    
    Esta função simula o pressionamento de teclas específicas,
    como teclas de navegação, atalhos ou teclas especiais.
    
    Args:
        botao (str or list): Nome da tecla a ser pressionada (ex: 'enter', 'tab')
                            ou lista de teclas para pressionar sequencialmente.
    
    Example:
        >>> aperta('enter')
        # Pressiona a tecla Enter
        
        >>> aperta(['tab', 'tab', 'enter'])
        # Pressiona Tab duas vezes e depois Enter
    """
    pyautogui.press(botao)


def localizanatela(imagem):
    """
    Localiza uma imagem na tela e move o cursor até ela.
    
    Esta função procura por uma imagem específica na tela usando o PyAutoGUI.
    O caminho das imagens é obtido da classe Settings. A função tenta localizar
    a imagem repetidamente até encontrá-la ou atingir o tempo limite.
    
    Args:
        imagem (str): Nome do arquivo de imagem a ser localizado (ex: 'botao.PNG').
    
    Returns:
        tuple or None: Coordenadas (x, y) do centro da imagem se encontrada,
                      None se a imagem não for localizada.
    
    Example:
        >>> localizanatela('botaoOK.PNG')
        Imagem botaoOK.PNG localizada na posição: (500, 300)
        (500, 300)
    
    Note:
        - O tempo de espera é configurável através da classe Settings
        - A função aguarda 0.25 segundos entre cada tentativa
        - Move o cursor automaticamente para o centro da imagem encontrada
    """
    caminho = settings.get_imagens_path()
    arquivo = imagem
    k = 0
    n = settings.get_tempo_espera_localizacao()
    os.chdir(caminho)

    while True:
        # Procura a imagem
        local = pyautogui.locateCenterOnScreen(arquivo)

        # Se imagem for localizada 
        if local != None:
            pyautogui.moveTo(local)
            print(f'Imagem {imagem} localizada na posição: {local}')
            break

        # Após n tentativas o programa encerra
        if k >= n:
            print(f'Imagem {imagem} não localizada')
            break

        # Aguarda um pouco para tentar novamente
        time.sleep(0.25)
        k += 1
    return local


def clicarNaNet(comando):
    """
    Procura e clica em um texto na página web atual.
    
    Esta função utiliza o atalho Ctrl+F para abrir a busca no navegador,
    digita o texto procurado e chama a função clicarNeste para confirmar
    a ação.
    
    Args:
        comando (str): Texto a ser procurado na página (pode conter o prefixo
                      'clicar em ' que será removido).
    
    Example:
        >>> clicarNaNet('clicar em Login')
        # Procura por "Login" na página e permite ao usuário confirmar o clique
    
    Note:
        - Utiliza falar() para feedback de voz
        - Requer interação do usuário através de clicarNeste()
    """
    from assistente import falar  # Import local para evitar dependência circular
    
    falar('procurando')
    comando = comando.replace('clicar em ', '')
    pyautogui.hotkey('ctrl', 'f')
    digitar(comando)
    clicarNeste()


def clicarNeste():
    """
    Confirma ou navega pelos resultados de busca na página.
    
    Esta função interage com o usuário por voz para confirmar se deve
    clicar no resultado atual da busca, ir para o próximo ou voltar
    ao anterior.
    
    Respostas aceitas:
        - 'próximo': Vai para o próximo resultado (pressiona Enter)
        - 'voltar': Volta para o resultado anterior (Shift+Enter)
        - Qualquer outra resposta: Confirma o clique (Ctrl+Enter)
    
    Example:
        >>> clicarNeste()
        # Pergunta "clicar neste?" e aguarda resposta por voz
        # Navega conforme a resposta do usuário
    
    Note:
        - Função recursiva para navegar por múltiplos resultados
        - Utiliza Ligar_microfone() para capturar comandos de voz
        - Utiliza falar() para feedback de voz
    """
    from assistente import falar, Ligar_microfone  # Import local para evitar dependência circular
    
    falar('clicar neste?')
    resposta = Ligar_microfone()
    if 'próximo' in resposta:
        aperta('enter')
        clicarNeste()
    elif 'voltar' in resposta:
        pyautogui.hotkey('shift', 'enter')
    else:
        pyautogui.hotkey('ctrl', 'enter')
