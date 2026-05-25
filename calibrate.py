import board, busio, time, math
from adafruit_bno08x.i2c import BNO08X_I2C
from adafruit_bno08x import BNO_REPORT_ROTATION_VECTOR

i2c = busio.I2C(board.SCL, board.SDA)
bno = BNO08X_I2C(i2c, address=0x4A)
bno.enable_feature(BNO_REPORT_ROTATION_VECTOR)

def get_heading():
    readings = []
    for _ in range(5):
        q = bno.quaternion
        if q:
            qw,qx,qy,qz = q
            yaw = math.degrees(math.atan2(2*(qw*qz+qx*qy), 1-2*(qy*qy+qz*qz))) % 360
            readings.append(yaw)
        time.sleep(0.2)
    return round(sum(readings)/len(readings), 1) if readings else 0.0

directions = ['NORTH', 'EAST', 'SOUTH', 'WEST']
results = {}

for d in directions:
    input(f'\nFace {d} then press Enter...')
    deg = get_heading()
    results[d] = deg
    print(f'  {d} = {deg}')

print('\n=== RESULTS ===')
for d, deg in results.items():
    print(f'{d}: {deg}')
