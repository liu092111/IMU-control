# imu_gui.py
import sys
import json
import csv
import serial
import threading
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QFileDialog
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class IMUGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IMU data collector")
        self.serial_port = serial.Serial('COM3', baudrate=115200, timeout=1)
        self.collecting = False
        self.data_buffer = []

        # UI 元件
        self.start_btn = QPushButton("開始")
        self.pause_btn = QPushButton("暫停")
        self.export_btn = QPushButton("匯出資料")

        self.start_btn.clicked.connect(self.start_collecting)
        self.pause_btn.clicked.connect(self.pause_collecting)
        self.export_btn.clicked.connect(self.export_data)

        layout = QVBoxLayout()
        layout.addWidget(self.start_btn)
        layout.addWidget(self.pause_btn)
        layout.addWidget(self.export_btn)

        # 加速度圖
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        self.setLayout(layout)

        # 啟動背景執行緒
        self.thread = threading.Thread(target=self.read_serial_data)
        self.thread.daemon = True
        self.thread.start()

    def start_collecting(self):
        self.collecting = True
        self.start_time = None  # 重設

    def pause_collecting(self):
        self.collecting = False

    def export_data(self):
        filename, _ = QFileDialog.getSaveFileName(self, "儲存資料", "", "CSV Files (*.csv)")
        if filename:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Time", "Ax", "Ay", "Az", "Gx", "Gy", "Gz"])
                for row in self.data_buffer:
                    writer.writerow(row)

    def read_serial_data(self):
        while True:
            try:
                line = self.serial_port.readline().decode().strip()
                if not self.collecting or not line.startswith("{"):
                    continue
                data = json.loads(line)
                if "imu" in data:
                    imu = data["imu"]
                    acc = imu["acc"]
                    gyr = imu["gyr"]
                    timestamp = data.get("time", 0)
                    if self.start_time is None:
                        self.start_time = timestamp
                    elapsed_time = timestamp - self.start_time
                    self.data_buffer.append([elapsed_time] + acc + gyr)
                    self.update_plot(acc, gyr)
            except Exception as e:
                print("Error:", e)

    def update_plot(self, acc, gyr):
        self.figure.clear()

        ax1 = self.figure.add_subplot(211)  # 上半部：加速度
        ax2 = self.figure.add_subplot(212)  # 下半部：陀螺儀

        # 取最後 100 筆資料來畫
        recent = self.data_buffer[-100:]

        acc_x = [row[1] for row in recent]
        acc_y = [row[2] for row in recent]
        acc_z = [row[3] for row in recent]

        gyr_x = [row[4] for row in recent]
        gyr_y = [row[5] for row in recent]
        gyr_z = [row[6] for row in recent]

        ax1.plot(acc_x, label="Ax")
        ax1.plot(acc_y, label="Ay")
        ax1.plot(acc_z, label="Az")
        ax1.set_title("Accelerometer (m/s²)")
        ax1.legend()

        ax2.plot(gyr_x, label="Gx")
        ax2.plot(gyr_y, label="Gy")
        ax2.plot(gyr_z, label="Gz")
        ax2.set_title("Gyroscope (°/s)")
        ax2.legend()

        self.canvas.draw()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IMUGUI()
    window.show()
    sys.exit(app.exec_())
