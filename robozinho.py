import pyautogui
import os
import time
import pyttsx3

#começa 'declarando os comandos basicos'

maquina = pyttsx3.init()


def falar (fala):
    print(fala)
    maquina.say(fala)
    maquina.runAndWait()

def digitar (texto):
    pyautogui.write(texto)

def aperta (botao):
    pyautogui.press(botao)



tempoDeEspera = 7

def localizanatela(imagem):
    caminho = r'C:\Users\jesus.anhaia\OneDrive\Documentos\GitHub\ServicoAutomatico\imagens'
    arquivo = imagem
    k = 0
    n = tempoDeEspera
    os.chdir(caminho)

    while True:
        #Procura a imagem
        local = pyautogui.locateCenterOnScreen(arquivo)

        #Se imagem for localizada 
        if local != None:
            pyautogui.moveTo(local)
            print(f'Imagem {imagem} localizada na posição: {local}')
            return ("sim")

        #Após n tentativas o programa encerra
        if k >= n:
            print(f'Imagem {imagem} não localizada')
            break

        #Aguarda um pouco para tentar novamente
        time.sleep(0.25)
        k += 1

#---------------------------------------------------------------#
#A partir daqui é a execução#

pyautogui.PAUSE = 0.8
time.sleep(2)

pyautogui.hotkey("ctrl","shift","a")
falar("Abrindo 4R")
time.sleep(2)
if "sim" in localizanatela("login4R.png"):
    digitar('jesus.anhaia')
    aperta('tab')
    digitar('123456')
    aperta('enter')
    aperta('enter')

os.startfile("C:\Program Files\Google\Chrome\Application\chrome.exe")
falar("abrindo internet")

pyautogui.moveTo(1,1)
time.sleep(1)
pyautogui.hotkey('alt','tab')
if "sim" in localizanatela("login1DOC.png"): 
    pyautogui.leftClick(1000,700)
else :
    falar("não encontrei o 1 DOC")

pyautogui.hotkey('ctrl', 'tab')
if "sim" in localizanatela("loginWEBMAIL.png"):
     aperta('enter')
else:
    falar("não encontrei o web mail")

time.sleep(1)
pyautogui.hotkey('ctrl', 'tab')
os.startfile(r"C:\Users\jesus.anhaia\OneDrive\Documentos\GitHub\ServicoAutomatico\janelaAuto.pyw")

