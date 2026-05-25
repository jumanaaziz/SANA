import time
import board
import busio

from adafruit_vl53l1x import VL53L1X
from adafruit_bno08x.i2c import BNO08X_I2C
from adafruit_bno08x import BNO_REPORT_ACCELEROMETER

# I2C
i2c = busio.I2C(board.SCL, board.SDA)

# VL53L1X
tof = VL53L1X(i2c)
tof.distance_mode = 2
tof.timing_budget = 100
tof.start_ranging()

# BNO085
bno = BNO08X_I2C(i2c)
bno.enable_feature(BNO_REPORT_ACCELEROMETER)

print("Sensors started.")

while True:
    try:
        if tof.data_ready:
            distance = tof.distance
            tof.clear_interrupt()
            print(f"[VL53L1X] Distance: {distance} mm")

        accel = bno.acceleration
        print(f"[BNO085] Accel: X={accel[0]:.2f} Y={accel[1]:.2f} Z={accel[2]:.2f}")

        time.sleep(1)

    except Exception as e:
        print("Error:", e)
        time.sleep(1)