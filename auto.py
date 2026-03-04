import pyautogui
import random
import time
import threading
from pynput import keyboard

clicando = False
rodando = True


def auto_click():
    global clicando, rodando
    while rodando:
        if clicando:
            pyautogui.doubleClick()

            # intervalo aleatório (min, max)
            intervalo = random.uniform(1, 1.8)
            time.sleep(intervalo)
        else:
            time.sleep(0.1)


def on_press(key):
    global clicando, rodando

    if key == keyboard.Key.f6:
        clicando = not clicando
        print("Clicando:", clicando)

    if key == keyboard.Key.esc:
        print("Encerrando...")
        rodando = False
        return False  # para o listener


print("F6 liga/desliga | ESC sai")

thread = threading.Thread(target=auto_click)
thread.start()

with keyboard.Listener(on_press=on_press) as listener:
    listener.join()

thread.join()