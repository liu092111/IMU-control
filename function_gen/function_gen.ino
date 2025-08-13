#include <SPI.h>

const int PIN_CS = 10;
const int PIN_RST = 9;

void writeReg(uint16_t addr, uint16_t data) {
  digitalWrite(PIN_CS, LOW);
  SPI.transfer16(addr);
  SPI.transfer16(data);
  digitalWrite(PIN_CS, HIGH);
}

void hwReset() {
  digitalWrite(PIN_RST, LOW); delay(5);
  digitalWrite(PIN_RST, HIGH); delay(5);
}

void setup() {
  pinMode(PIN_CS, OUTPUT);
  pinMode(PIN_RST, OUTPUT);
  digitalWrite(PIN_CS, HIGH);
  digitalWrite(PIN_RST, HIGH);

  SPI.begin();
  SPI.beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));

  hwReset();

  // ======== 以下是初始化範例（實際數值需查 datasheet）========
  // 設 DDS 頻率，例如 1MHz
  writeReg(0x1E, 0x1234); // 假設寄存器 0x1E 設定頻率
  // 啟用 DAC1
  writeReg(0x00, 0x0001); // 假設寄存器 0x00 控制 DAC 開啟
}

void loop() {
  // 不需做任何事，AD9106 會持續輸出
}
