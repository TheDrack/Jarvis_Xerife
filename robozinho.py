import pyautogui
import time

pyautogui.PAUSE = 0.8
time.sleep(2)
pyautogui.hotkey('ctrl', 'shift', 'a')
time.sleep(10)
pyautogui.write('jesus.anhaia')
pyautogui.press('tab')
pyautogui.write('123456')
pyautogui.press('enter')
pyautogui.press('enter')
time.sleep(1)
pyautogui.hotkey('ctrl', 'shift', 'c')
time.sleep(5)
pyautogui.leftClick(1000,700)
pyautogui.hotkey('ctrl', 'tab')
pyautogui.press('enter')
time.sleep(1)
pyautogui.hotkey('ctrl', 'tab')
pyautogui.hotkey('ctrl', 'shift', 'j')
pyautogui.alert('Pronto')
