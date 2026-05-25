from gpiozero import Button
from signal import pause

touch = Button(17)

print("Touch sensor ready...")

touch.when_pressed = lambda: print("TOUCHED")
touch.when_released = lambda: print("RELEASED")

pause()