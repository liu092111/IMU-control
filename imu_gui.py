import sys
import time
import threading
import serial
import serial.tools.list_ports
import re
import csv
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                           QPushButton, QComboBox, QLabel, QMessageBox, QFileDialog,
                           QSpinBox, QCheckBox)
from PyQt5.QtCore import QTimer, pyqtSignal, QObject
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

# =========================
# 數據解析類
# =========================
class DataEmitter(QObject):
    data_received = pyqtSignal(dict)

class IMUDataParser:
    def __init__(self):
        self.data_emitter = DataEmitter()
        
    def parse_arduino_line(self, line):
        """解析Arduino輸出的文本數據"""
        try:
            # 解析格式: ts=1234 ms  T=25C  EUL(deg)=1.23,4.56,7.89  ACC(g)=0.123,0.456,0.789  GYR(dps)=12.3,45.6,78.9  MAG(uT)=1.2,3.4,5.6  P=1013.25  FPS(inst)=100.0
            
            # 使用正則表達式提取數據
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
                match = re.search(pattern, line)
                if match:
                    if key in ['euler', 'accel', 'gyro', 'mag']:
                        # 三軸數據
                        data[key] = [float(match.group(1)), float(match.group(2)), float(match.group(3))]
                    else:
                        # 單個數值
                        data[key] = float(match.group(1))
            
            return data if data else None
            
        except Exception as e:
            print(f"解析錯誤: {e}")
            return None

# =========================
# GUI 主程式
# =========================
class IMUGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HI04M3 Data Collector")
        self.serial_port = None
        self.collecting = False
        self.data_buffer = []
        self.stop_reader = False
        self.parser = IMUDataParser()
        self.collected_data = []  # 用於儲存所有數據（1000Hz）
        self.display_data = []   # 用於顯示的數據（50Hz或其他顯示頻率）
        self.display_counter = 0  # 用於控制顯示頻率
        
        # 連接信號
        self.parser.data_emitter.data_received.connect(self.on_data_received)
        
        self.init_ui()
        
        # 使用QTimer來更新繪圖，避免在線程中直接更新GUI
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_plot)
        self.update_timer.start(100)  # 100ms更新一次
        
        # 背景讀取線程
        self.reader_thread = threading.Thread(target=self.read_serial_data, daemon=True)
        self.reader_thread.start()
    
    def init_ui(self):
        # --- COM & Baud 選擇 ---
        top_layout = QHBoxLayout()
        self.port_cb = QComboBox()
        self.refresh_ports()
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_ports)
        
        self.baud_cb = QComboBox()
        self.baud_cb.addItems(["115200", "921600"])
        self.baud_cb.setCurrentText("115200")  # 預設115200，之後會自動切換到921600
        
        self.connect_btn = QPushButton("連線")
        self.disconnect_btn = QPushButton("中斷")
        self.disconnect_btn.setEnabled(False)

        self.connect_btn.clicked.connect(self.connect_serial)
        self.disconnect_btn.clicked.connect(self.disconnect_serial)

        top_layout.addWidget(QLabel("Port:"))
        top_layout.addWidget(self.port_cb)
        top_layout.addWidget(refresh_btn)
        top_layout.addWidget(QLabel("Baud:"))
        top_layout.addWidget(self.baud_cb)
        top_layout.addWidget(self.connect_btn)
        top_layout.addWidget(self.disconnect_btn)

        # --- 控制按鈕 ---
        ctrl_layout = QHBoxLayout()
        self.start_btn = QPushButton("開始收集")
        self.pause_btn = QPushButton("暫停")
        self.clear_btn = QPushButton("清除數據")
        self.export_btn = QPushButton("匯出CSV")
        self.send_cmd_btn = QPushButton("設定1000Hz")
        
        self.start_btn.clicked.connect(self.start_collecting)
        self.pause_btn.clicked.connect(self.pause_collecting)
        self.clear_btn.clicked.connect(self.clear_data)
        self.export_btn.clicked.connect(self.export_data)
        self.send_cmd_btn.clicked.connect(self.send_1000hz_command)
        
        # 數據顯示限制
        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(100, 10000)
        self.max_points_spin.setValue(1000)
        
        # 顯示選項
        self.show_accel = QCheckBox("加速度")
        self.show_gyro = QCheckBox("角速度")
        self.show_euler = QCheckBox("歐拉角")
        self.show_accel.setChecked(True)
        self.show_gyro.setChecked(True)
        
        ctrl_layout.addWidget(self.send_cmd_btn)
        ctrl_layout.addWidget(self.start_btn)
        ctrl_layout.addWidget(self.pause_btn)
        ctrl_layout.addWidget(self.clear_btn)
        ctrl_layout.addWidget(QLabel("最大點數:"))
        ctrl_layout.addWidget(self.max_points_spin)
        ctrl_layout.addWidget(self.show_accel)
        ctrl_layout.addWidget(self.show_gyro)
        ctrl_layout.addWidget(self.show_euler)
        ctrl_layout.addWidget(self.export_btn)

        # --- 狀態顯示 ---
        status_layout = QHBoxLayout()
        self.status_label = QLabel("狀態: 未連線")
        self.data_count_label = QLabel("數據點: 0")
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.data_count_label)

        # --- 畫布 ---
        self.figure = Figure(figsize=(12, 8))
        self.canvas = FigureCanvas(self.figure)

        # --- 主佈局 ---
        layout = QVBoxLayout()
        layout.addLayout(top_layout)
        layout.addLayout(ctrl_layout)
        layout.addLayout(status_layout)
        layout.addWidget(self.canvas)
        self.setLayout(layout)
        
        # 初始繪圖
        self.init_plot()

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
            self.status_label.setText(f"狀態: 已連線至 {port} @ {baud}")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.send_cmd_btn.setEnabled(True)
            QMessageBox.information(self, "成功", f"已連線至 {port} @ {baud}\n\n提示：請點擊'設定1000Hz'按鈕設定取樣頻率")
        except serial.SerialException as e:
            QMessageBox.critical(self, "錯誤", f"無法連線 {port}：\n{e}")
            self.status_label.setText("狀態: 連線失敗")

    def disconnect_serial(self):
        self.collecting = False
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except:
                pass
        self.serial_port = None
        self.status_label.setText("狀態: 已斷線")
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.send_cmd_btn.setEnabled(False)

    def send_1000hz_command(self):
        """發送1000Hz設定指令"""
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "請先連線串口")
            return
        
        try:
            # 發送UNLOGALL LOG HI91 ONTIME 0.001指令
            command = "UNLOGALL\r\nLOG HI91 ONTIME 0.001\r\n"
            self.serial_port.write(command.encode('utf-8'))
            self.serial_port.flush()
            QMessageBox.information(self, "指令發送", "已發送1000Hz設定指令:\nUNLOGALL\nLOG HI91 ONTIME 0.001")
            self.status_label.setText("狀態: 已設定1000Hz取樣頻率")
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"發送指令失敗：\n{e}")

    def start_collecting(self):
        if not self.serial_port or not self.serial_port.is_open:
            QMessageBox.warning(self, "警告", "請先連線串口")
            return
        self.collecting = True
        self.start_btn.setText("收集中...")
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)

    def pause_collecting(self):
        self.collecting = False
        self.start_btn.setText("開始收集")
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        
    def clear_data(self):
        self.data_buffer.clear()
        self.collected_data.clear()
        self.display_data.clear()
        self.display_counter = 0
        self.data_count_label.setText("數據點: 0")
        # 清除圖表
        self.figure.clear()
        self.canvas.draw()
        self.update_plot()

    def on_data_received(self, data):
        """處理接收到的數據"""
        if self.collecting:
            # 所有數據都存到collected_data（1000Hz完整數據）
            self.collected_data.append(data)
            
            # 控制顯示頻率 - 每20筆數據顯示1筆（1000Hz -> 50Hz顯示）
            # 你可以修改這個數字來調整顯示頻率：20 = 50Hz, 10 = 100Hz, 5 = 200Hz
            self.display_counter += 1
            if self.display_counter >= 20:  # 每20筆顯示1筆
                self.data_buffer.append(data)
                self.display_data.append(data)
                self.display_counter = 0
                
                # 限制顯示緩衝區大小
                max_points = self.max_points_spin.value()
                if len(self.data_buffer) > max_points:
                    self.data_buffer = self.data_buffer[-max_points:]
            
            self.data_count_label.setText(f"數據點: {len(self.collected_data)} (顯示: {len(self.data_buffer)})")

    def read_serial_data(self):
        """背景線程讀取串口數據"""
        buffer = ""
        while not self.stop_reader:
            if self.serial_port and self.serial_port.is_open:
                try:
                    if self.serial_port.in_waiting > 0:
                        # 讀取可用數據
                        raw_data = self.serial_port.read(self.serial_port.in_waiting)
                        text_data = raw_data.decode('utf-8', errors='ignore')
                        buffer += text_data
                        
                        # 按行處理
                        lines = buffer.split('\n')
                        buffer = lines[-1]  # 保留最後不完整的行
                        
                        for line in lines[:-1]:
                            line = line.strip()
                            if line and 'ts=' in line:  # 只處理包含時間戳的數據行
                                data = self.parser.parse_arduino_line(line)
                                if data:
                                    self.parser.data_emitter.data_received.emit(data)
                except Exception as e:
                    print(f"讀取串口錯誤: {e}")
                    time.sleep(0.1)
            else:
                time.sleep(0.1)

    def init_plot(self):
        """初始化繪圖"""
        self.figure.clear()
        
    def update_plot(self):
        """更新繪圖"""
        if not self.data_buffer:
            return
            
        self.figure.clear()
        
        plot_count = sum([self.show_accel.isChecked(), 
                         self.show_gyro.isChecked(), 
                         self.show_euler.isChecked()])
        
        if plot_count == 0:
            return
            
        subplot_idx = 1
        
        # 準備時間軸（使用索引）
        x_data = list(range(len(self.data_buffer)))
        
        if self.show_accel.isChecked() and any('accel' in d for d in self.data_buffer):
            ax = self.figure.add_subplot(plot_count, 1, subplot_idx)
            acc_x = [d.get('accel', [0,0,0])[0] for d in self.data_buffer]
            acc_y = [d.get('accel', [0,0,0])[1] for d in self.data_buffer]
            acc_z = [d.get('accel', [0,0,0])[2] for d in self.data_buffer]
            
            ax.plot(x_data, acc_x, 'r-', label='Acc X', linewidth=1)
            ax.plot(x_data, acc_y, 'g-', label='Acc Y', linewidth=1)
            ax.plot(x_data, acc_z, 'b-', label='Acc Z', linewidth=1)
            ax.legend(loc='upper right')  # 固定在右上角
            ax.set_title("加速度 (g)")
            ax.grid(True, alpha=0.3)
            subplot_idx += 1

        if self.show_gyro.isChecked() and any('gyro' in d for d in self.data_buffer):
            ax = self.figure.add_subplot(plot_count, 1, subplot_idx)
            gyr_x = [d.get('gyro', [0,0,0])[0] for d in self.data_buffer]
            gyr_y = [d.get('gyro', [0,0,0])[1] for d in self.data_buffer]
            gyr_z = [d.get('gyro', [0,0,0])[2] for d in self.data_buffer]
            
            ax.plot(x_data, gyr_x, 'r-', label='Gyr X', linewidth=1)
            ax.plot(x_data, gyr_y, 'g-', label='Gyr Y', linewidth=1)
            ax.plot(x_data, gyr_z, 'b-', label='Gyr Z', linewidth=1)
            ax.legend(loc='upper right')  # 固定在右上角
            ax.set_title("角速度 (°/s)")
            ax.grid(True, alpha=0.3)
            subplot_idx += 1
            
        if self.show_euler.isChecked() and any('euler' in d for d in self.data_buffer):
            ax = self.figure.add_subplot(plot_count, 1, subplot_idx)
            roll = [d.get('euler', [0,0,0])[0] for d in self.data_buffer]
            pitch = [d.get('euler', [0,0,0])[1] for d in self.data_buffer]
            yaw = [d.get('euler', [0,0,0])[2] for d in self.data_buffer]
            
            ax.plot(x_data, roll, 'r-', label='Roll', linewidth=1)
            ax.plot(x_data, pitch, 'g-', label='Pitch', linewidth=1)
            ax.plot(x_data, yaw, 'b-', label='Yaw', linewidth=1)
            ax.legend(loc='upper right')  # 固定在右上角
            ax.set_title("歐拉角 (°)")
            ax.grid(True, alpha=0.3)

        self.figure.tight_layout()
        self.canvas.draw()

    def export_data(self):
        """匯出數據到CSV文件"""
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
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['timestamp', 'temperature', 'pressure', 'fps',
                                'acc_x', 'acc_y', 'acc_z',
                                'gyr_x', 'gyr_y', 'gyr_z',
                                'mag_x', 'mag_y', 'mag_z',
                                'roll', 'pitch', 'yaw']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for data in self.collected_data:
                        row = {
                            'timestamp': data.get('timestamp', 0),
                            'temperature': data.get('temperature', 0),
                            'pressure': data.get('pressure', 0),
                            'fps': data.get('fps', 0)
                        }
                        
                        # 加速度
                        if 'accel' in data:
                            row.update({
                                'acc_x': data['accel'][0],
                                'acc_y': data['accel'][1],
                                'acc_z': data['accel'][2]
                            })
                        
                        # 角速度
                        if 'gyro' in data:
                            row.update({
                                'gyr_x': data['gyro'][0],
                                'gyr_y': data['gyro'][1],
                                'gyr_z': data['gyro'][2]
                            })
                            
                        # 磁力計
                        if 'mag' in data:
                            row.update({
                                'mag_x': data['mag'][0],
                                'mag_y': data['mag'][1],
                                'mag_z': data['mag'][2]
                            })
                            
                        # 歐拉角
                        if 'euler' in data:
                            row.update({
                                'roll': data['euler'][0],
                                'pitch': data['euler'][1],
                                'yaw': data['euler'][2]
                            })
                        
                        writer.writerow(row)
                
                QMessageBox.information(self, "成功", f"數據已儲存至 {filename}\n共 {len(self.collected_data)} 筆數據")
            except Exception as e:
                QMessageBox.critical(self, "錯誤", f"儲存失敗：\n{e}")

    def closeEvent(self, event):
        """程式關閉時的清理工作"""
        self.stop_reader = True
        self.collecting = False
        
        if self.update_timer:
            self.update_timer.stop()
            
        time.sleep(0.2)  # 等待線程結束
        
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except:
                pass
                
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IMUGUI()
    window.show()
    sys.exit(app.exec_())