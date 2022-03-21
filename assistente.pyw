#-*- coding:utf-8 -*-
from pynput.keyboard import Controller
import pyautogui
import time
import speech_recognition as sr
import pyttsx3
import os
import sys
import pandas as pd
import webbrowser as wb


audio = sr.Recognizer()
maquina = pyttsx3.init()


def falar (fala):
    maquina.say(fala)
    maquina.runAndWait()

def digitar (texto):
    Controller().type(texto)

def aperta (botao):
    pyautogui.press(botao)

def restart():
    python = sys.executable
    os.execl(python, python, * sys.argv)


def chamarAXerife ():
    falar('Não tema a xerife chegou')
    with sr.Microphone() as s:
        audio.adjust_for_ambient_noise(s)

        while True:
            Audio = audio.listen(s)
            comando = audio.recognize_google(Audio, language ='pt-BR',show_all=True)
            if comando != []:
                comando =audio.recognize_google(Audio, language='pt-BR')
                comando = comando.lower()

                if 'xerife' in comando:
                    comando = comando.replace('xerife ','')
                    falar('Olá')
                    if comando == '':
                        pedircomando()
                    else:
                        comandos(comando)
                    pedircomando()
                elif 'fechar' in comando:
                    falar('fechando assistente, até a próxima...')
                    sys.exit()
                else:
                    with open('arq01.txt', 'a') as arquivo:
                        arquivo.write(comando + "\n")

def Ligar_microfone ():

    with sr.Microphone() as s:
        audio.adjust_for_ambient_noise(s)

        while True:
            Audio = audio.listen(s)
            comando = audio.recognize_google(Audio, language ='pt-BR',show_all=True)
            if comando != []:
                comando =audio.recognize_google(Audio, language='pt-BR')
                comando = comando.lower()
                if 'cancelar' in comando:
                    falar('cancelado ação')
                    restart()

                elif 'fechar' in comando:
                    falar('fechando assistente, até mais...')
                    sys.exit()

                elif 'parar' in comando:
                    falar('parando comando')
                    return
                else :
                    return(comando)

def pedircomando():
    falar('Diga um comando')
    ordem = Ligar_microfone()
    ordem = ordem.replace('xerife ','')
    comandos(ordem)

def comandos(comando):
    TuplaDeComandos =  {
        ('sulfite',FazerRequisicaoSulfite),
        ('requisição',FazerRequisicaoPT1),
        ('sulfite',FazerRequisicaoSulfite),
        ('planilha',AbrirPlanilha),
        ('inventário',AtualizarInventario),
        ('balancete',ImprimirBalancete),
        ('almoxarifado',AbrirAlmox),
        ('digitar produto',Cod4rMaterial),
        ('digitar quantidade',QuantMaterial),
        ('gaveta',abrirgaveta),
        ('escreva',digitar),
        ('aperte',aperta),
        ('falar',falar),
        ('internet', abrirInternet),
        ('estoque',ConsultarEstoque),
        ('site',abrirsite),
        ('clicar em',clicarNaNet)}

    for comandos,acao in TuplaDeComandos:
        if comandos in comando:
            comando = comando.replace(f'{comandos} ','')
            acao(comando)

def clicarNaNet (comando):
    falar('procurando')
    comando = comando.replace('clicar em ', '')
    pyautogui.hotkey('ctrl','f')
    digitar(comando)
    clicarNeste()

def clicarNeste():
    falar('clicar neste?')
    resposta = Ligar_microfone()
    if 'próximo' in resposta:
        aperta('enter')
        clicarNeste()
    elif 'voltar' in resposta:
        pyautogui.hotkey('shift','enter')
    else :
        pyautogui.hotkey('ctrl','enter')

def abrirsite (comando):
    url = escolhersite(comando)
    wb.open(url)

def escolhersite(comando):

    site = comando
    planilhaDeSite = pd.read_excel(r"ServicoAutomatico\Lista de Sites.xlsx")
    out = planilhaDeSite.to_numpy().tolist()
    TuplaDeSITE = [tuple(elt) for elt in out]
    for SITE,URL in TuplaDeSITE:
        URL = str(URL)
        if SITE in site:       
                mandar = URL
    try:
        return (mandar)

    except UnboundLocalError:
            falar('Qual o site?')
            site = escolhersite(Ligar_microfone())




def abrirgaveta (teste):
    pyautogui.hotkey('ctrl','shift','g')

def FazerRequisicaoPT1 (teste):
    falar('Fazendo requisição')
    AbrirRequisicao()
    EscolherCentroDeCusto()
    descritivoRequisicao()
    AnotacaoRequisicao()
    FazerRequisicaoPT2(teste)
def FazerRequisicaoPT2 (teste):
    digitar(Cod4rMaterial(teste))
    QuantMaterial()
    AlgoMais()

def AbrirRequisicao ():
    pyautogui.PAUSE = 0.4
    falar('Irá inicializar uma requisição automatizada, não clique em nada')
    pyautogui.leftClick(200,1050)
    pyautogui.hotkey('win','up')
    pyautogui.leftClick(200,50)
    pyautogui.leftClick(770,90)
    pyautogui.doubleClick(100,175)
    pyautogui.PAUSE = 0.6
    aperta(['tab','tab','tab'])
    pyautogui.PAUSE = 0.4
    digitar('1')
    aperta(['enter','enter'])

def EscolherCentroDeCusto ():
    falar('Qual centro de custo será o destinatário?')
    CC = Ligar_microfone()
    df = pd.read_excel(r"ServicoAutomatico\Lista de CC.xlsx")
    out = df.to_numpy().tolist()
    TuplaDeCC = [tuple(elt) for elt in out]
    for codigo,escrito in TuplaDeCC:
        codigo = str(codigo)
        if escrito in CC:       
            CC = codigo
    digitar(CC)
    aperta('enter')
    aperta('enter')


def descritivoRequisicao ():
    falar('Diga o descritivo')
    
    desc = Ligar_microfone()
    desc = desc.upper()
    digitar(desc)
    aperta('enter')


def AnotacaoRequisicao():
    falar('Está aos cuidados de qual solicitante?')
    
    AC = Ligar_microfone()
    AC = AC.upper()
    digitar('A/C ' + AC)
    aperta('enter')

def Cod4rMaterial (teste):
    falar('Diga o material')
    Material = Ligar_microfone()
    df = pd.read_excel(r"ServicoAutomatico\Lista de Materiais.xlsx")
    out = df.to_numpy().tolist()
    TuplaDeMateriais = [tuple(elt) for elt in out]
    for codigo,material in TuplaDeMateriais:
        codigo = str(codigo)
        if material in Material:
            Material = '0'+ codigo
    return(Material)


def QuantMaterial ():
    falar('Fale a quantidade')
    Quantidade = Ligar_microfone()
    if 'pular' in Quantidade:
        prox()
        pyautogui.hotkey('shift','tab')
    else:
        aperta('enter')
    digitar(Quantidade)


def AlgoMais():
    falar('Algo mais?')
    resposta = Ligar_microfone()
    if 'sim' in resposta:
        FazerRequisicaoPT2(resposta)
    elif 'não'  in resposta:
        falar('Pronto')
        restart()
    else :
        falar('Não entendi')

def prox ():
    aperta('enter')
    digitar('1')
    aperta('enter')

def FazerRequisicaoSulfite (teste):
    falar('Preparando requisição de sulfite')
    pyautogui.PAUSE = 0.4
    pyautogui.leftClick(660,1050)
    pyautogui.leftClick(200,50)
    pyautogui.leftClick(770,90)
    pyautogui.doubleClick(100,175)
    aperta(['tab','tab','tab'])
    digitar('1')
    aperta('enter')
    aperta('enter')
    aperta('enter')
    aperta('enter')
    aperta('enter')
    aperta('enter')
    digitar('0301603043')
    aperta('enter')
    digitar('0,5')
    pyautogui.alert('Automatização concluida, continue manualmente')

def AtualizarInventario (teste):
    falar('Atualizando planilha de inventario')
    pyautogui.PAUSE = 0.4
    pyautogui.leftClick(660,1050)
    pyautogui.leftClick(200,50)
    pyautogui.doubleClick(100,270)
    pyautogui.doubleClick(160,165)
    pyautogui.leftClick(155,175)
    pyautogui.leftClick(155,175)
    pyautogui.leftClick(585,310)
    pyautogui.leftClick(585,400)
    pyautogui.leftClick(585,480)
    pyautogui.leftClick(170,505)
    pyautogui.leftClick(170,600)
    pyautogui.alert('clique em Ok quando carregar a página de impressão, para evitar falhas com a velocidade do 4R')
    pyautogui.leftClick(20,30)
    aperta('home')
    aperta('down')
    aperta('down')
    aperta('down')
    aperta('down')
    aperta('down')
    aperta('enter')
    aperta('enter')
    pyautogui.hotkey('shift','tab')
    pyautogui.hotkey('shift','tab')
    pyautogui.hotkey('shift','tab')
    aperta('home')
    aperta('a')
    time.sleep(1)
    aperta('enter')
    aperta('tab')
    aperta('tab')
    aperta('tab')
    digitar('Material 10\Rafael\Consumo.inventario\Dados\inventario.xls')
    aperta('enter')
    aperta('enter')
    pyautogui.leftClick(2000,10)
    pyautogui.alert('Automatização concluida, continue manualmente')



def ImprimirBalancete (teste):
    falar('Abrindo lançamento de Balancete')
    pyautogui.PAUSE = 0.4
    pyautogui.leftClick(660,1050)
    pyautogui.leftClick(200,50)
    pyautogui.doubleClick(100,270)
    pyautogui.doubleClick(160,155)
    pyautogui.leftClick(240,200)
    digitar('1')
    pyautogui.leftClick(585,320)
    pyautogui.leftClick(585,440)
    pyautogui.leftClick(585,565)
    pyautogui.leftClick(400,150)
    pyautogui.alert('Automatização concluida, continue manualmente')

def AbrirPlanilha (teste):
    falar('Abrindo Planilha, espere para clicar no Ok')
    pyautogui.PAUSE = 0.4
    pyautogui.hotkey('ctrl', 'shift', 'i')
    pyautogui.alert('ESPERE. Clique em Ok quando a planilha abrir para não dar erro')
    aperta('enter')
    time.sleep(2)
    pyautogui.hotkey('win', 'right')
    pyautogui.doubleClick(1500,270)
    pyautogui.hotkey('ctrl', 'b')
    pyautogui.leftClick(660,1050)
    pyautogui.hotkey('win','left')
    pyautogui.alert('Automatização concluida, continue manualmente')

def AbrirAlmox (teste):
    falar('Abrindo Almoxarifado 4R')
    pyautogui.PAUSE = 0.8
    pyautogui.alert("O código vai começar. Não use nada do seu computador enquanto o código está rodando")
    pyautogui.hotkey('ctrl', 'shift', 'a')
    time.sleep(10)
    digitar('jesus.anhaia')
    aperta('tab')
    digitar('123456')
    aperta('enter')
    aperta('enter')
    pyautogui.alert('Almoxarifado 4R Aberto, prossiga manualmente')

def ConsultarEstoque(teste):
    material = Cod4rMaterial(teste)
    df = pd.read_excel(r"ServicoAutomatico/inventario.xls")
    out = df.to_numpy().tolist()
    TuplaDeMateriais = [tuple(elt) for elt in out]
    for codigo,Qntd, in TuplaDeMateriais:
        codigo = str(codigo).replace('.','')
        if material in codigo:
            falar(Qntd)
            return(Qntd)

def abrirInternet (teste):
    pyautogui.hotkey('ctrl','shift','c')



chamarAXerife()
