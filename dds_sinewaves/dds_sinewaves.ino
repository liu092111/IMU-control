/*******************************************************************************
    @file:   debug_test.ino
    @brief:  AD9106 Debug Test - 加入除錯訊息來診斷問題
*******************************************************************************/

#include <AD9106.h>

// Initialize AD9106 with CS 10 and default reset, trigger, en_cvddx
AD9106 device(10);

// Toggle OP_AMPS to true/false for on-board amplifiers.
// Set FCLK to 0 to use on-board oscillator, otherwise set to frequency of
// external clock.
const bool OP_AMPS = true;
const float FCLK = 0;

char stop_start = 's';
bool started = false;

void setup() {
  Serial.begin(115200);
  while (!Serial) {
    ;
  }
  Serial.println("*** Serial Port Ready ***");

  Serial.println("開始初始化AD9106...");
  
  //  Begin AD9106.
  device.begin(OP_AMPS, FCLK);
  Serial.println("device.begin() 完成");

  // Start SPI communication at 14MHz
  device.spi_init(14000000);
  Serial.println("SPI初始化完成 (14MHz)");

  // Reset AD9106 registers
  Serial.println("重置AD9106暫存器...");
  device.reg_reset();
  delay(100);  // 增加延遲時間
  Serial.println("暫存器重置完成");
  
  // 測試SPI通訊 - 嘗試讀取一個暫存器
  Serial.println("測試SPI通訊...");
  int16_t test_read = device.spi_read(0x0000);  // 讀取暫存器0x0000
  Serial.print("讀取暫存器0x0000的值: 0x");
  Serial.println(test_read, HEX);
  
  // Configure sinewaves on all channels
  Serial.println("設定正弦波輸出...");
  for (int i = 0; i < 4; i++) {
    Serial.print("設定通道 ");
    Serial.println(i + 1);
    device.setDDSsine(CHNL(i + 1));
    device.set_CHNL_DGAIN(CHNL(i + 1), 0x2000);  // Gain of 1/2
  }

  device.set_CHNL_DOFFSET(CHNL_1, 0x1000);
  device.set_CHNL_DDS_PHASE(CHNL_2, 0x4000);
  device.set_CHNL_START_DELAY(CHNL_3, 0x1500);

  //   Set DDS frequency
  Serial.println("設定DDS頻率為50kHz...");
  device.setDDSfreq(50000);

  // 驗證頻率設定
  float actual_freq = device.getDDSfreq();
  Serial.print("實際DDS頻率: ");
  Serial.print(actual_freq);
  Serial.println(" Hz");

  // Update pattern to start
  Serial.println("啟動波形產生...");
  device.update_pattern();
  started = true;
  Serial.println("*** 初始化完成! Pattern started. Press 's' to start/stop. ***");
}

void loop() {
  if (Serial.available()) {
    stop_start = Serial.read();
    Serial.print("收到字元: ");
    Serial.println(stop_start);
    
    if (stop_start == 's') {
      started = !started;
      if (started) {
        Serial.println("啟動波形輸出...");
        device.start_pattern();
        Serial.println("波形輸出已啟動");
      } else {
        Serial.println("停止波形輸出...");
        device.stop_pattern();
        Serial.println("波形輸出已停止");
      }
    }
  }
}
