from gpiozero import OutputDevice
from time import sleep

motor = OutputDevice(27, active_high=True, initial_value=False)

print("Vibration motor test started")

while True:
    motor.on()
    print("VIBRATION ON")
    sleep(1)

    motor.off()
    print("VIBRATION OFF")
    sleep(1)