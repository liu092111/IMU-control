import sys
import time
import threading
import serial
import serial.tools.list_ports
import re
import csv
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLabel, QMessageBox, QFileDialog, QSpinBox
)
from PyQt5.QtCore import QTimer, pyqtSignal, QObject
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# =========================
# 數據解析類（保留不變）
# =========================
class DataEmitter(QObject):
    data_received = pyqtSignal(dict)

class IMUDataParser:
    def __init__(self):
        self.data_emitter = DataEmitter()

    def parse_arduino_line(self, line):
        """
        解析Arduino輸出的文本數據（保留你的格式與regex）
        例如：
        ts=1234 ms  T=25C  EUL(deg)=1.23,4.56,7.89  ACC(g)=0.123,0.456,0.789
        GYR(dps)=12.3,45.6,78.9  MAG(uT)=1.2,3.4,5.6  P=1013.25  FPS(inst)=100.0
        """
        try:
            patterns = {
                'timestamp': r'ts=(\d+)',
                'temperature': r'T=(-?\d+)C',
                'euler': r'EUL\(deg\)=([-\d.]+),([-\d.]+),([-\d.]+)',
                'accel': r'ACC\(g\)=([-\d.]+),([-\d.]+),([-\d.]+)',
                'gyro': r'GYR\(dps\)=([-\d.]+),([-\d.]+),([-\d.]+)',
                'mag': r'MAG\(uT\)=([-\d.]+),([-\d.]+),([-\d.]+)',
                'pressure': r'P=([-\d.]+)',
                'fps': r'FPS\(inst\)=([-\d.]+)'
            }
            data = {}
            for key, pattern in patterns.items():
                m = re.search(pattern, line)
                if m:
                    if key in ['euler', 'accel', 'gyro', 'mag']:
                        data[key] = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
                    else:
                        data[key] = float(m.group(1))
            return data if data else None
        except Exception as e:
            print(f"解析錯誤: {e}")
            return None

# =========================
# GUI 主程式（UI 簡化，收數據流程不動）
# =========================
class IMUGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HI04M3 Data Collector (Simple UI)")
        self.serial_port = None
        self.collecting = False
        self.data_buffer = []       # 顯示用緩衝
        self.collected_data = []    # 全部數據（CSV 匯出用）
        self.stop_reader = False
        self.parser = IMUDataParser()

        # 透過 signal 把背景緒資料丟回主緒（保留原機制）
        self.parser.data_emitter.data_received.connect(self.on_data_received)

        self.init_ui()

        # 定時刷新繪圖（避免在背景緒動 GUI）
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(100)  # 10 Hz
        self.update_timer.timeout.connect(self.update_plot)
        self.update_timer.start()

        # 背景讀取線程（保留）
        self.reader_thread = threading.Thread(target=self.read_serial_data, daemon=True)
        self.reader_thread.start()

    # -------- UI：簡化版 --------
    def init_ui(self):
        # Top：Port / Refresh / Baud / Connect / Disconnect
        top = QHBoxLayout()
        self.port_cb = QComboBox()
        self.refresh_ports()
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.refresh_ports)

        self.baud_cb = QComboBox()
        self.baud_cb.addItems(["115200", "921600"])
        self.baud_cb.setCurrentText("921600")

        self.connect_btn = QPushButton("連線")
        self.disconnect_btn = QPushButton("中斷")
        self.disconnect_btn.setEnabled(False)

        self.connect_btn.clicked.connect(self.connect_serial)
        self.disconnect_btn.clicked.connect(self.disconnect_serial)

        top.addWidget(QLabel("Port:"))
        top.addWidget(self.port_cb)
        top.addWidget(btn_refresh)
        top.addWidget(QLabel("Baud:"))
        top.addWidget(self.baud_cb)
        top.addWidget(self.connect_btn)
        top.addWidget(self.disconnect_btn)

        # Controls：Start / Pause / Clear / Export
        ctrl = QHBoxLayout()
        self.start_btn = QPushButton("開始")
        self.pause_btn = QPushButton("暫停")
        self.clear_btn = QPushButton("清除")
        self.export_btn = QPushButton("匯出CSV")

        self.start_btn.clicked.connect(self.start_collecting)
        self.pause_btn.clicked.connect(self.pause_collecting)
        self.clear_btn.clicked.connect(self.clear_data)
        self.export_btn.clicked.connect(self.export_data)

        # 為了保持原緩衝限制邏輯，保留「最大點數」但縮小處理
        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(100, 10000)
        self.max_points_spin.setValue(1000)

        ctrl.addWidget(self.start_btn)
        ctrl.addWidget(self.pause_btn)
        ctrl.addWidget(self.clear_btn)
        ctrl.addWidget(self.export_btn)
        ctrl.addWidget(QLabel("最大點數"))
        ctrl.addWidget(self.max_points_spin)

        # 狀態列
        status = QHBoxLayout()
        self.status_label = QLabel("狀態：未連線")
        self.data_count_label = QLabel("數據點：0")
        status.addWidget(self.status_label)
        status.addStretch(1)
        status.addWidget(self.data_count_label)

        # 繪圖區：兩張圖（Acc & Gyro）
        self.figure = Figure(figsize=(10, 7))
        self.canvas = FigureCanvas(self.figure)

        # 主版面
        main = QVBoxLayout()
        main.addLayout(top)
        main.addLayout(ctrl)
        main.addLayout(status)
        main.addWidget(self.canvas)
        self.setLayout(main)

        # 初始圖面
        self.init_plot()

    # -------- 連線相關（保留邏輯） --------
    def refresh_ports(self):
        self.port_cb.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if ports:
            self.port_cb.addItems(ports)
        else:
            self.port_cb.addItem("無可用端口")

    def connect_serial(self):
        port = self.port_cb.currentText()
        if port == "無可用端口":
            QMessageBox.warning(self, "警告", "沒有可用的串口")
            return
        baud = int(self.baud_cb.currentText())
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            self.serial_port = serial.Serial(
                port,
                baudrate=baud,
                timeout=0.1,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            self.serial_port.reset_input_buffer()
            self.status_label.setText(f"狀態：已連線 {port} @ {baud}")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            QMessageBox.information(self, "成功", f"已連線至 {port} @ {baud}")
        except serial.SerialException as e:
            QMessageBox.critical(self, "錯誤", f"無法連線 {port}：\n{e}")
            self.status_label.setText("狀態：連線失敗")

    def disconnect_serial(self):
        self.collecting = False
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except:
                pass
        self.serial_port = None
        self.status_label.setText("狀態：已斷線")
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)

    # -------- 收集控制（保留邏輯） --------
    def start_collecting(self):
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "請先連線串口")
            return
        self.collecting = True
        self.start_btn.setText("收集中…")
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)

    def pause_collecting(self):
        self.collecting = False
        self.start_btn.setText("開始")
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)

    def clear_data(self):
        self.data_buffer.clear()
        self.collected_data.clear()
        self.data_count_label.setText("數據點：0")
        self.update_plot()

    # -------- 背景讀取（保留邏輯） --------
    def read_serial_data(self):
        buffer = ""
        while not self.stop_reader:
            if self.serial_port and self.serial_port.is_open:
                try:
                    if self.serial_port.in_waiting > 0:
                        raw = self.serial_port.read(self.serial_port.in_waiting)
                        text = raw.decode('utf-8', errors='ignore')
                        buffer += text
                        lines = buffer.split('\n')
                        buffer = lines[-1]
                        for line in lines[:-1]:
                            line = line.strip()
                            if line and 'ts=' in line:
                                data = self.parser.parse_arduino_line(line)
                                if data:
                                    # 回到主緒
                                    self.parser.data_emitter.data_received.emit(data)
                except Exception as e:
                    print(f"讀取串口錯誤: {e}")
                    time.sleep(0.1)
            else:
                time.sleep(0.1)

    def on_data_received(self, data):
        if self.collecting:
            self.data_buffer.append(data)
            self.collected_data.append(data)
            # 限制顯示緩衝大小（保留你原本的做法）
            max_points = self.max_points_spin.value()
            if len(self.data_buffer) > max_points:
                self.data_buffer = self.data_buffer[-max_points:]
            self.data_count_label.setText(f"數據點：{len(self.collected_data)}")

    # -------- 繪圖（簡化為固定兩張圖） --------
    def init_plot(self):
        self.figure.clear()
        self.canvas.draw()

    def update_plot(self):
        if not self.data_buffer:
            return
        self.figure.clear()

        subplot_idx = 1
        x = list(range(len(self.data_buffer)))

        # Acceleration
        if any('accel' in d for d in self.data_buffer):
            ax1 = self.figure.add_subplot(2, 1, subplot_idx)
            acc_x = [d.get('accel', [0,0,0])[0] for d in self.data_buffer]
            acc_y = [d.get('accel', [0,0,0])[1] for d in self.data_buffer]
            acc_z = [d.get('accel', [0,0,0])[2] for d in self.data_buffer]
            ax1.plot(x, acc_x, label='Acc X', linewidth=1)
            ax1.plot(x, acc_y, label='Acc Y', linewidth=1)
            ax1.plot(x, acc_z, label='Acc Z', linewidth=1)
            ax1.set_title("Acceleration (g)")
            ax1.grid(True, alpha=0.3)
            ax1.legend(loc='upper right')
            subplot_idx += 1

        # Gyroscope
        if any('gyro' in d for d in self.data_buffer):
            ax2 = self.figure.add_subplot(2, 1, subplot_idx)
            gyr_x = [d.get('gyro', [0,0,0])[0] for d in self.data_buffer]
            gyr_y = [d.get('gyro', [0,0,0])[1] for d in self.data_buffer]
            gyr_z = [d.get('gyro', [0,0,0])[2] for d in self.data_buffer]
            ax2.plot(x, gyr_x, label='Gyr X', linewidth=1)
            ax2.plot(x, gyr_y, label='Gyr Y', linewidth=1)
            ax2.plot(x, gyr_z, label='Gyr Z', linewidth=1)
            ax2.set_title("Angular Velocity (°/s)")
            ax2.grid(True, alpha=0.3)
            ax2.legend(loc='upper right')

        self.figure.tight_layout()
        self.canvas.draw()

    # -------- 匯出 CSV（保留邏輯與欄位） --------
    def export_data(self):
        if not self.collected_data:
            QMessageBox.warning(self, "警告", "沒有數據可以匯出")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "儲存CSV文件",
            f"imu_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )
        if filename:
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    fieldnames = [
                        'timestamp','temperature','pressure','fps',
                        'acc_x','acc_y','acc_z',
                        'gyr_x','gyr_y','gyr_z',
                        'mag_x','mag_y','mag_z',
                        'roll','pitch','yaw'
                    ]
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for d in self.collected_data:
                        row = {
                            'timestamp': d.get('timestamp', 0),
                            'temperature': d.get('temperature', 0),
                            'pressure': d.get('pressure', 0),
                            'fps': d.get('fps', 0)
                        }
                        if 'accel' in d:
                            row.update({'acc_x': d['accel'][0], 'acc_y': d['accel'][1], 'acc_z': d['accel'][2]})
                        if 'gyro' in d:
                            row.update({'gyr_x': d['gyro'][0], 'gyr_y': d['gyro'][1], 'gyr_z': d['gyro'][2]})
                        if 'mag' in d:
                            row.update({'mag_x': d['mag'][0], 'mag_y': d['mag'][1], 'mag_z': d['mag'][2]})
                        if 'euler' in d:
                            row.update({'roll': d['euler'][0], 'pitch': d['euler'][1], 'yaw': d['euler'][2]})
                        writer.writerow(row)
                QMessageBox.information(self, "成功", f"數據已儲存：{filename}\n共 {len(self.collected_data)} 筆")
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"儲存失敗：\n{e}")

    def closeEvent(self, event):
        self.stop_reader = True
        self.collecting = False
        if self.update_timer:
            self.update_timer.stop()
        time.sleep(0.2)
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except:
                pass
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = IMUGUI()
    w.show()
    sys.exit(app.exec_())
