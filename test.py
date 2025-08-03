import serial

ser = serial.Serial('COM3', 115200, timeout=1)  # 改成你的 COM Port

while True:
    line = ser.readline().decode('utf-8', errors='ignore').strip()
    if line:
        print(line)
