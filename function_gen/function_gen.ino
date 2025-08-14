#include <SPI.h>

// AD9106 SPI 腳位定義
#define AD9106_CS_PIN 10    // Chip Select (可自由選擇數位腳位)
#define AD9106_RESET_PIN 9  // Reset 腳位 (可自由選擇)

// AD9106 重要暫存器位址
#define AD9106_REG_SPI_CONFIG     0x00
#define AD9106_REG_POWERDOWN      0x01
#define AD9106_REG_CLKCFG         0x02
#define AD9106_REG_REFADJ         0x03
#define AD9106_REG_DAC1_DGAIN     0x35
#define AD9106_REG_DAC1_RSET      0x36
#define AD9106_REG_SAW_CONFIG     0x37
#define AD9106_REG_DDS_TW32       0x3E
#define AD9106_REG_DDS_TW1        0x3F
#define AD9106_REG_DDS_PW1        0x43
#define AD9106_REG_TRIG_TW_SEL    0x47
#define AD9106_REG_DDSx_CONFIG    0x48
#define AD9106_REG_WAV1_CONFIG    0x49
#define AD9106_REG_PATTERN_RPT    0x4B
#define AD9106_REG_PATTERN_DLY    0x4C
#define AD9106_REG_DAC_PAT        0x4D
#define AD9106_REG_TRIG_DELAY     0x4E
#define AD9106_REG_ADC_CONFIG     0x4F
#define AD9106_REG_START_DELAY    0x5C
#define AD9106_REG_CFG_ERROR      0x5D
#define AD9106_REG_RAMUPDATE      0x1D  // RAM 更新暫存器（正確位址）
#define AD9106_REG_PAT_STATUS     0x1E  // 模式狀態暫存器（正確位址）
#define AD9106_REG_PAT_TYPE       0x1F  // 模式類型暫存器
#define AD9106_REG_PATTERN_DLY    0x20  // 模式延遲暫存器
#define AD9106_REG_DAC1_CST       0x22  // DAC1 常數值暫存器
#define AD9106_REG_DAC1_DGAIN     0x35  // DAC1 數位增益
#define AD9106_REG_DDS_PHASE1     0x43  // DDS1 相位暫存器

// SPI 設定
SPISettings ad9106Settings(10000000, MSBFIRST, SPI_MODE0); // 10MHz, MSB first, Mode 0

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000); // 等待 Serial 連接，最多 3 秒
  
  Serial.println("AD9106 Sine Wave Generator - Teensy 4.1");
  Serial.println("開始硬體除錯...");
  
  // 初始化腳位
  pinMode(AD9106_CS_PIN, OUTPUT);
  pinMode(AD9106_RESET_PIN, OUTPUT);
  digitalWrite(AD9106_CS_PIN, HIGH);   // CS 預設為高電位
  digitalWrite(AD9106_RESET_PIN, HIGH);
  
  // 初始化 SPI
  SPI.begin();
  
  // 腳位狀態檢查
  Serial.println("腳位狀態檢查：");
  Serial.print("CS Pin ("); Serial.print(AD9106_CS_PIN); Serial.print("): ");
  Serial.println(digitalRead(AD9106_CS_PIN) ? "HIGH" : "LOW");
  Serial.print("Reset Pin ("); Serial.print(AD9106_RESET_PIN); Serial.print("): ");
  Serial.println(digitalRead(AD9106_RESET_PIN) ? "HIGH" : "LOW");
  
  // 硬體重置 AD9106
  Serial.println("執行硬體重置...");
  resetAD9106();
  
  delay(500); // 延長等待時間
  
  // SPI 連線測試
  Serial.println("SPI 連線測試...");
  testSPIConnection();
  
  delay(100);
  
  // 設定 AD9106 產生 50kHz 正弦波
  if (setupAD9106_50kHz_Sine()) {
    Serial.println("AD9106 設定成功！正在輸出 50kHz 正弦波");
  } else {
    Serial.println("AD9106 設定失敗！請檢查硬體連接");
    Serial.println("常見問題：");
    Serial.println("1. 檢查 SPI 線路連接 (MOSI, MISO, SCK, CS)");
    Serial.println("2. 確認 AD9106 開發板是否有供電");
    Serial.println("3. 確認 GND 共地連接");
    Serial.println("4. 檢查 Reset 線路連接");
  }
}

void loop() {
  // 主迴圈可以保持空白，或添加其他功能
  // 例如：監控狀態、調整參數等
  delay(1000);
  
  // 讀取一些狀態暫存器來檢查運作情況
  uint16_t cfg_error = readRegister(AD9106_REG_CFG_ERROR);
  if (cfg_error != 0) {
    Serial.print("配置錯誤狀態: 0x");
    Serial.println(cfg_error, HEX);
  }
}

// 硬體重置 AD9106
void resetAD9106() {
  Serial.println("重置 AD9106...");
  digitalWrite(AD9106_RESET_PIN, LOW);
  delay(10); // 延長重置時間
  digitalWrite(AD9106_RESET_PIN, HIGH);
  delay(100); // 延長等待時間
  Serial.println("重置完成");
}

// SPI 連線測試（擴展版）
void testSPIConnection() {
  Serial.println("測試 SPI 連線...");
  
  // 測試基本暫存器
  uint16_t spi_config = readRegister(AD9106_REG_SPI_CONFIG);
  uint16_t powerdown = readRegister(AD9106_REG_POWERDOWN);
  uint16_t clkcfg = readRegister(AD9106_REG_CLKCFG);
  
  Serial.print("SPI_CONFIG (0x00): 0x");
  Serial.println(spi_config, HEX);
  Serial.print("POWERDOWN (0x01): 0x");
  Serial.println(powerdown, HEX);
  Serial.print("CLKCFG (0x02): 0x");
  Serial.println(clkcfg, HEX);
  
  // 測試寫入和讀回功能
  Serial.println("\n測試寫入/讀取功能...");
  
  // 嘗試寫入一個已知值到 POWERDOWN 暫存器
  Serial.println("寫入測試值到 POWERDOWN 暫存器...");
  writeRegister(AD9106_REG_POWERDOWN, 0x0001); // 寫入測試值
  delay(1);
  uint16_t readback = readRegister(AD9106_REG_POWERDOWN);
  Serial.print("寫入 0x0001，讀回: 0x");
  Serial.println(readback, HEX);
  
  // 復原設定
  writeRegister(AD9106_REG_POWERDOWN, 0x0000);
  
  // 測試調諧字暫存器的直接存取
  Serial.println("\n測試調諧字暫存器存取...");
  
  // 直接測試 TW1 暫存器
  Serial.println("測試 TW1 (0x3F) 暫存器...");
  writeRegister(0x3F, 0x1234); // 直接使用暫存器位址
  delay(1);
  uint16_t tw1_test = readRegister(0x3F);
  Serial.print("TW1 測試 - 寫入: 0x1234, 讀回: 0x");
  Serial.println(tw1_test, HEX);
  
  // 測試 TW32 暫存器
  Serial.println("測試 TW32 (0x3E) 暫存器...");
  writeRegister(0x3E, 0x0056); // 直接使用暫存器位址
  delay(1);
  uint16_t tw32_test = readRegister(0x3E);
  Serial.print("TW32 測試 - 寫入: 0x0056, 讀回: 0x");
  Serial.println(tw32_test, HEX);
  
  // 嘗試其他可能的暫存器位址
  Serial.println("\n掃描部分暫存器...");
  for (int addr = 0x00; addr <= 0x10; addr++) {
    uint16_t val = readRegister(addr);
    Serial.print("Reg 0x");
    Serial.print(addr, HEX);
    Serial.print(": 0x");
    Serial.println(val, HEX);
  }
  
  // 如果讀回都是 0xFFFF，表示 SPI 沒有正常工作
  if (spi_config == 0xFFFF && powerdown == 0xFFFF && clkcfg == 0xFFFF) {
    Serial.println("⚠️  SPI 通訊失敗！所有讀取都返回 0xFFFF");
    Serial.println("可能原因：");
    Serial.println("- SPI 線路未正確連接");
    Serial.println("- AD9106 沒有供電");
    Serial.println("- CS 或 Reset 腳位錯誤");
  } else if (tw1_test == 0xFFFF && tw32_test == 0xFFFF) {
    Serial.println("⚠️  基本通訊正常，但調諧字暫存器無法存取");
    Serial.println("可能原因：");
    Serial.println("- 暫存器位址錯誤");
    Serial.println("- 需要特殊的解鎖序列");
    Serial.println("- 時鐘或電源問題");
  } else {
    Serial.println("✅ SPI 通訊正常");
  }
}

// 寫入暫存器（加強版）
void writeRegister(uint16_t reg, uint16_t value) {
  SPI.beginTransaction(ad9106Settings);
  digitalWrite(AD9106_CS_PIN, LOW);
  delayMicroseconds(1); // CS setup time
  
  // AD9106 使用 16-bit 位址和 16-bit 資料
  // 寫入指令: bit[15] = 0 (寫入)
  SPI.transfer16((reg & 0x7FFF)); // 確保 bit[15] = 0
  SPI.transfer16(value);
  
  delayMicroseconds(1); // CS hold time
  digitalWrite(AD9106_CS_PIN, HIGH);
  SPI.endTransaction();
  
  delayMicroseconds(10); // 延長等待時間確保寫入完成
}

// 讀取暫存器（加強版）
uint16_t readRegister(uint16_t reg) {
  uint16_t result;
  
  SPI.beginTransaction(ad9106Settings);
  digitalWrite(AD9106_CS_PIN, LOW);
  delayMicroseconds(1); // CS setup time
  
  // 讀取指令: bit[15] = 1 (讀取)
  SPI.transfer16(reg | 0x8000); // 設定 bit[15] = 1
  result = SPI.transfer16(0x0000); // 讀取資料
  
  delayMicroseconds(1); // CS hold time
  digitalWrite(AD9106_CS_PIN, HIGH);
  SPI.endTransaction();
  
  return result;
}

// 設定 AD9106 產生 50kHz 正弦波（修正版）
bool setupAD9106_50kHz_Sine() {
  Serial.println("開始設定 AD9106（修正版）...");
  
  // 1. 軟體重置所有暫存器
  Serial.println("執行軟體重置...");
  writeRegister(0x00, 0x8000); // 軟體重置位元
  delay(10);
  
  // 2. SPI 介面設定
  writeRegister(AD9106_REG_SPI_CONFIG, 0x0000);
  
  // 3. 電源管理 - 啟用所有 DAC
  writeRegister(AD9106_REG_POWERDOWN, 0x0000);
  
  // 4. 時鐘設定 - 使用內部振蕩器
  writeRegister(AD9106_REG_CLKCFG, 0x0000);
  
  // 5. 基準電壓調整
  writeRegister(AD9106_REG_REFADJ, 0x0000);
  
  // 6. 設定 DAC1 為 DDS 正弦波模式
  writeRegister(AD9106_REG_WAV1_CONFIG, 0x0000); // DDS 正弦波
  
  // 7. 計算 50kHz 的 DDS 調諧字（24-bit，修正版）
  float target_freq = 50000.0;      // 50kHz
  float system_clock = 180000000.0; // 180MHz 內部時鐘
  
  // AD9106 使用 24-bit DDS 調諧字，不是 32-bit！
  uint32_t tuning_word_24bit = (uint32_t)((target_freq * 16777216.0) / system_clock); // 2^24 = 16777216
  tuning_word_24bit &= 0xFFFFFF; // 確保只有 24 位
  
  // 正確的位元分配：
  // TW32[7:0] = 調諧字的高 8 位 [23:16]
  // TW1[15:0] = 調諧字的低 16 位 [15:0]
  uint16_t tw_high_8bit = (tuning_word_24bit >> 16) & 0xFF;    // 高 8 位
  uint16_t tw_low_16bit = tuning_word_24bit & 0xFFFF;          // 低 16 位
  
  Serial.print("24-bit 調諧字: 0x");
  Serial.println(tuning_word_24bit, HEX);
  Serial.print("TW32 (高8位): 0x");
  Serial.println(tw_high_8bit, HEX);
  Serial.print("TW1 (低16位): 0x");
  Serial.println(tw_low_16bit, HEX);
  
  // 8. 設定 DDS 調諧字（修正順序）
  writeRegister(AD9106_REG_DDS_TW1, tw_low_16bit);   // 先寫低位
  writeRegister(AD9106_REG_DDS_TW32, tw_high_8bit);  // 再寫高位
  
  // 9. 設定 DDS 相位（0 度）
  writeRegister(AD9106_REG_DDS_PHASE1, 0x0000);
  
  // 10. 設定 DAC1 增益（參考範例程式）
  writeRegister(AD9106_REG_DAC1_DGAIN, 0x2000); // 1/2 增益，如範例所示
  
  // 11. 設定 DDS 配置
  writeRegister(AD9106_REG_DDSx_CONFIG, 0x0002); // 啟用 DDS1
  
  // 12. 設定 DAC 輸出模式
  writeRegister(AD9106_REG_DAC_PAT, 0x0001); // 啟用 DAC1
  
  // 13. 設定模式重複（連續輸出）
  writeRegister(AD9106_REG_PATTERN_RPT, 0x0000); // 連續重複
  
  // 14. 設定觸發延遲
  writeRegister(AD9106_REG_TRIG_DELAY, 0x0000);
  writeRegister(AD9106_REG_START_DELAY, 0x0000);
  
  // 15. 關鍵步驟：RAM UPDATE（使用正確位址 0x1D）
  Serial.println("執行 RAM UPDATE...");
  writeRegister(0x1D, 0x0001); // RAMUPDATE 位於 0x1D
  delay(1);
  
  // 16. 啟動模式：RUN（使用正確位址 0x1E）
  Serial.println("啟動輸出模式...");
  writeRegister(0x1E, 0x0001); // RUN 位於 0x1E
  
  Serial.println("AD9106 設定完成");
  
  // 驗證設定
  delay(10);
  uint16_t readback_tw1 = readRegister(AD9106_REG_DDS_TW1);
  uint16_t readback_tw32 = readRegister(AD9106_REG_DDS_TW32);
  uint16_t pat_status = readRegister(0x1E); // 使用正確位址
  
  Serial.print("讀回 TW1: 0x");
  Serial.println(readback_tw1, HEX);
  Serial.print("讀回 TW32: 0x");
  Serial.println(readback_tw32, HEX);
  Serial.print("模式狀態: 0x");
  Serial.println(pat_status, HEX);
  
  // 驗證：檢查是否成功寫入
  bool tw1_ok = (readback_tw1 == tw_low_16bit);
  bool tw32_ok = (readback_tw32 == tw_high_8bit);
  bool running = (pat_status & 0x0001) != 0;
  
  Serial.print("TW1 設定: ");
  Serial.println(tw1_ok ? "✅" : "❌");
  Serial.print("TW32 設定: ");
  Serial.println(tw32_ok ? "✅" : "❌");
  Serial.print("輸出狀態: ");
  Serial.println(running ? "✅ 運行中" : "❌ 停止");
  
  return tw1_ok && tw32_ok;
}

// 可選：動態改變頻率的函數（修正版）
void setFrequency(float freq_hz) {
  float system_clock = 180000000.0; // 180MHz
  
  // 使用正確的 24-bit 調諧字計算
  uint32_t tuning_word_24bit = (uint32_t)((freq_hz * 16777216.0) / system_clock);
  tuning_word_24bit &= 0xFFFFFF;
  
  uint16_t tw_high_8bit = (tuning_word_24bit >> 16) & 0xFF;
  uint16_t tw_low_16bit = tuning_word_24bit & 0xFFFF;
  
  writeRegister(AD9106_REG_DDS_TW1, tw_low_16bit);
  writeRegister(AD9106_REG_DDS_TW32, tw_high_8bit);
  
  // 更新 RAM
  writeRegister(AD9106_REG_RAMUPDATE, 0x0001);
  
  Serial.print("頻率設定為: ");
  Serial.print(freq_hz);
  Serial.println(" Hz");
}

// 新增：啟動/停止輸出函數（使用正確位址）
void startOutput() {
  writeRegister(0x1E, 0x0001); // RUN 位於 0x1E
  Serial.println("輸出已啟動");
}

void stopOutput() {
  writeRegister(0x1E, 0x0000); // STOP 位於 0x1E
  Serial.println("輸出已停止");
}

// 新增：狀態檢查函數（使用正確位址）
void checkStatus() {
  uint16_t pat_status = readRegister(0x1E); // PAT_STATUS 位於 0x1E
  uint16_t cfg_error = readRegister(AD9106_REG_CFG_ERROR);
  
  Serial.print("模式狀態: 0x");
  Serial.print(pat_status, HEX);
  Serial.println(pat_status & 0x0001 ? " (運行中)" : " (停止)");
  
  if (cfg_error != 0) {
    Serial.print("配置錯誤: 0x");
    Serial.println(cfg_error, HEX);
  } else {
    Serial.println("無配置錯誤");
  }
}

// 新增：觸發信號控制（根據 FAQ 說明）
void setTriggerLow() {
  // 如果你的硬體有連接 TRIGGER 腳位，可以加入這個控制
  // digitalWrite(TRIGGER_PIN, LOW); // 啟動模式生成
  Serial.println("觸發信號設為 LOW（如果有連接觸發腳位）");
}