#!/usr/bin/env python3
"""
AD9106 + Teensy ADC Signal Monitor with GUI
帶圖形界面的監控程式
"""

import serial
import matplotlib.pyplot as plt
import numpy as np
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from datetime import datetime
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class TeensyADCGUIMonitor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AD9106 + Teensy ADC 監控系統")
        self.root.geometry("1000x700")
        
        # 串列連接參數
        self.ser = None
        self.connected = False
        
        # 數據儲存
        self.timestamps = []
        self.voltages = []
        self.sample_rate = 0
        self.num_samples = 0
        self.adc_ref_voltage = 0
        
        # 創建GUI
        self.create_widgets()
        
    def create_widgets(self):
        """創建GUI元件"""
        # 主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 連接控制框架
        control_frame = ttk.LabelFrame(main_frame, text="連接控制", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # COM port選擇
        ttk.Label(control_frame, text="COM Port:").grid(row=0, column=0, sticky=tk.W)
        self.port_var = tk.StringVar(value="COM3")
        self.port_entry = ttk.Entry(control_frame, textvariable=self.port_var, width=10)
        self.port_entry.grid(row=0, column=1, padx=(5, 10))
        
        # 連接按鈕
        self.connect_btn = ttk.Button(control_frame, text="連接", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=2, padx=5)
        
        # 連接狀態指示
        self.status_label = ttk.Label(control_frame, text="未連接", foreground="red")
        self.status_label.grid(row=0, column=3, padx=10)
        
        # 操作控制框架
        operation_frame = ttk.LabelFrame(main_frame, text="操作控制", padding=10)
        operation_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 開始/停止波形按鈕
        self.wave_btn = ttk.Button(operation_frame, text="開始波形產生", 
                                  command=self.toggle_wave_generation, state=tk.DISABLED)
        self.wave_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 測量按鈕
        self.measure_btn = ttk.Button(operation_frame, text="測量並繪圖", 
                                     command=self.start_measurement, state=tk.DISABLED)
        self.measure_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 保存數據按鈕
        self.save_btn = ttk.Button(operation_frame, text="保存數據", 
                                  command=self.save_data, state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT)
        
        # 進度條
        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(operation_frame, variable=self.progress_var, 
                                       maximum=100, length=200)
        self.progress.pack(side=tk.RIGHT)
        
        # 資訊顯示框架
        info_frame = ttk.LabelFrame(main_frame, text="系統資訊", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.info_text = tk.Text(info_frame, height=6, width=80)
        scrollbar = ttk.Scrollbar(info_frame, orient=tk.VERTICAL, command=self.info_text.yview)
        self.info_text.configure(yscrollcommand=scrollbar.set)
        
        self.info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 圖表框架
        plot_frame = ttk.LabelFrame(main_frame, text="signal monitor", padding=5)
        plot_frame.pack(fill=tk.BOTH, expand=True)
        
        # 創建matplotlib圖表
        self.fig = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # 初始化空圖表
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)
        self.ax1.set_title("AD9106 DAC Output Signal")
        self.ax1.set_xlabel("time (ms)")
        self.ax1.set_ylabel("voltage (V)")
        self.ax1.grid(True, alpha=0.3)
        
        self.ax2.set_title("Spectrum Analysis (FFT)")
        self.ax2.set_xlabel("Frequency (Hz)")
        self.ax2.set_ylabel("Amplitude")
        self.ax2.grid(True, alpha=0.3)
        
        self.fig.tight_layout()
        self.canvas.draw()
        
        # 狀態變數
        self.wave_started = False
        
    def log_info(self, message):
        """在資訊區域顯示訊息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.info_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.info_text.see(tk.END)
        self.root.update_idletasks()
        
    def toggle_connection(self):
        """切換連接狀態"""
        if not self.connected:
            self.connect_to_teensy()
        else:
            self.disconnect_from_teensy()
    
    def connect_to_teensy(self):
        """連接到Teensy"""
        try:
            port = self.port_var.get()
            self.ser = serial.Serial(port, 115200, timeout=10)
            time.sleep(2)  # 等待Arduino重啟
            
            self.connected = True
            self.status_label.config(text="已連接", foreground="green")
            self.connect_btn.config(text="斷開連接")
            self.wave_btn.config(state=tk.NORMAL)
            self.measure_btn.config(state=tk.NORMAL)
            
            self.log_info(f"已連接到 {port}")
            
        except serial.SerialException as e:
            messagebox.showerror("連接錯誤", f"無法連接到 {self.port_var.get()}:\n{e}")
            self.log_info(f"連接失敗: {e}")
    
    def disconnect_from_teensy(self):
        """斷開Teensy連接"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            
        self.connected = False
        self.status_label.config(text="未連接", foreground="red")
        self.connect_btn.config(text="連接")
        self.wave_btn.config(state=tk.DISABLED)
        self.measure_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.DISABLED)
        
        self.log_info("已斷開連接")
    
    def send_command(self, command):
        """發送命令到Teensy"""
        if self.ser and self.ser.is_open:
            self.ser.write(command.encode())
            self.log_info(f"發送命令: {command}")
    
    def read_serial_line(self):
        """讀取一行串列數據"""
        if self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode('utf-8').strip()
                return line
            except UnicodeDecodeError:
                return ""
        return ""
    
    def toggle_wave_generation(self):
        """切換波形產生狀態"""
        if not self.connected:
            return
            
        self.send_command('s')
        
        # 讀取回應
        response = self.read_serial_line()
        if response:
            self.log_info(f"Teensy回應: {response}")
            
        # 切換按鈕狀態
        self.wave_started = not self.wave_started
        if self.wave_started:
            self.wave_btn.config(text="停止波形產生")
        else:
            self.wave_btn.config(text="開始波形產生")
    
    def start_measurement(self):
        """開始測量（在背景執行緒中）"""
        if not self.connected:
            return
            
        # 在背景執行緒中執行測量
        self.measure_btn.config(state=tk.DISABLED, text="測量中...")
        self.progress_var.set(0)
        
        measurement_thread = threading.Thread(target=self.measure_data_thread)
        measurement_thread.daemon = True
        measurement_thread.start()
    
    def measure_data_thread(self):
        """在背景執行緒中執行數據收集"""
        try:
            if self.collect_data():
                self.root.after(0, self.update_plot)  # 在主執行緒中更新UI
                self.root.after(0, lambda: self.save_btn.config(state=tk.NORMAL))
            
        finally:
            self.root.after(0, lambda: self.measure_btn.config(state=tk.NORMAL, text="測量並繪圖"))
            self.root.after(0, lambda: self.progress_var.set(0))
    
    def collect_data(self):
        """收集ADC數據"""
        self.log_info("開始測量...")
        self.send_command('m')
        
        # 清空緩存
        self.timestamps = []
        self.voltages = []
        
        # 等待數據開始標記
        while True:
            line = self.read_serial_line()
            self.log_info(f"接收: {line}")
            
            if line == "START_DATA":
                break
            elif line.startswith("Error:"):
                self.log_info(line)
                return False
            elif not line:
                continue
        
        # 讀取參數
        while True:
            line = self.read_serial_line()
            self.log_info(f"參數: {line}")
            
            if line.startswith("SAMPLE_RATE:"):
                self.sample_rate = int(line.split(":")[1])
            elif line.startswith("NUM_SAMPLES:"):
                self.num_samples = int(line.split(":")[1])
            elif line.startswith("ADC_REF_VOLTAGE:"):
                self.adc_ref_voltage = float(line.split(":")[1])
            elif line == "DATA_BEGIN":
                break
        
        self.log_info(f"Sampling rate: {self.sample_rate}Hz, Samples: {self.num_samples}")
        
        # 收集數據點
        data_count = 0
        while data_count < self.num_samples:
            line = self.read_serial_line()
            
            if line == "DATA_END":
                break
            elif not line:
                continue
            
            try:
                # 解析時間戳和電壓
                timestamp_us, voltage = line.split(',')
                timestamp_ms = float(timestamp_us) / 1000.0
                voltage = float(voltage)
                
                self.timestamps.append(timestamp_ms)
                self.voltages.append(voltage)
                data_count += 1
                
                # 更新進度條
                progress = (data_count / self.num_samples) * 100
                self.root.after(0, lambda p=progress: self.progress_var.set(p))
                
            except ValueError:
                continue
        
        self.log_info(f"數據收集完成! 共收集 {len(self.timestamps)} 個樣本")
        return True
    
    def update_plot(self):
        """更新圖表顯示"""
        if not self.timestamps or not self.voltages:
            return
        
        # 清除舊圖表
        self.ax1.clear()
        self.ax2.clear()
        
        # 時域圖
        self.ax1.plot(self.timestamps, self.voltages, 'b-', linewidth=1, alpha=0.8)
        self.ax1.set_title(f'AD9106 DAC Output - Sampling Rate: {self.sample_rate}Hz')
        self.ax1.set_xlabel('Time (ms)')
        self.ax1.set_ylabel('Voltage (V)')
        self.ax1.grid(True, alpha=0.3)
        
        # 統計資訊
        voltage_array = np.array(self.voltages)
        stats_text = f'Max: {np.max(voltage_array):.3f}V\nMin: {np.min(voltage_array):.3f}V\nAvg: {np.mean(voltage_array):.3f}V\nP-P: {np.max(voltage_array) - np.min(voltage_array):.3f}V'
        self.ax1.text(0.02, 0.98, stats_text, transform=self.ax1.transAxes, 
                     verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        # FFT頻譜圖
        if len(self.voltages) > 1:
            dt = (self.timestamps[-1] - self.timestamps[0]) / (len(self.timestamps) - 1) / 1000.0
            freqs = np.fft.fftfreq(len(self.voltages), dt)
            fft_vals = np.fft.fft(self.voltages)
            
            positive_freq_idx = freqs > 0
            freqs_positive = freqs[positive_freq_idx]
            fft_magnitude = np.abs(fft_vals[positive_freq_idx])
            
            self.ax2.plot(freqs_positive, fft_magnitude, 'r-', linewidth=1)
            self.ax2.set_title('Spectrum Analysis (FFT)')
            self.ax2.set_xlabel('Frequency (Hz)')
            self.ax2.set_ylabel('Amplitude')
            self.ax2.grid(True, alpha=0.3)
            self.ax2.set_xlim(0, min(5000, np.max(freqs_positive)))
        
        self.fig.tight_layout()
        self.canvas.draw()
    
    def save_data(self):
        """保存數據到CSV文件"""
        if not self.timestamps or not self.voltages:
            messagebox.showwarning("警告", "沒有數據可保存")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialname=f"AD9106_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write("Timestamp_ms,Voltage_V\n")
                    for t, v in zip(self.timestamps, self.voltages):
                        f.write(f"{t:.3f},{v:.4f}\n")
                
                self.log_info(f"數據已保存至: {filename}")
                messagebox.showinfo("成功", f"數據已保存至:\n{filename}")
                
            except Exception as e:
                messagebox.showerror("錯誤", f"保存失敗:\n{e}")
    
    def run(self):
        """執行GUI主迴圈"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()
    
    def on_closing(self):
        """程式關閉時的清理工作"""
        if self.connected:
            self.disconnect_from_teensy()
        self.root.destroy()

def main():
    app = TeensyADCGUIMonitor()
    app.run()

if __name__ == "__main__":
    main()