/**
 * HI04M3 115200→921600 自動切換 + 二進位解碼（Teensy 4.1 / Serial1）
 *
 * 流程：
 *  1) 以 115200 與模組連線
 *  2) LOG HI91 ONTIME 0 先關輸出
 *  3) SERIALCONFIG 921600 立刻換波特率，隨即 Serial1 也改成 921600
 *  4) LOG HI91 ONTIME 0.001 設定 1 kHz 輸出
 *  5) 解析 HI91 二進位封包並輸出（每 N 幀印一筆）
 */

#include <Arduino.h>
#include <string.h>

// ========== PC 與感測器串口 ==========
#define PC_BAUD           115200   // USB CDC 到電腦
#define SENSOR_BAUD_BOOT  115200   // 模組啟動時的速率（先用它接上）
#define SENSOR_BAUD_RUN   921600   // 切換後要跑的速率

// ========== 指令（手冊 3.x） ==========
#define CMD_SERIALCONFIG  "SERIALCONFIG"
#define CMD_SAVECONFIG    "SAVECONFIG"
#define CMD_LOG_OFF       "LOG HI91 ONTIME 0"
#define CMD_LOG_1KHZ      "LOG HI91 ONTIME 0.001"  


// 每 N 幀列印 1 行（1kHz 時避免洗版；要每幀都印就設 1）
#define PRINT_EVERY_N     50

// 嚴格 CRC？0=寬鬆（CRC 不符也嘗試解析），1=嚴格（不符就丟棄）
#ifndef STRICT_CRC
#define STRICT_CRC 0
#endif

// --------- 緩衝與工具 ---------
static uint8_t buf[256];
static size_t  fill = 0;     // 已填入位元組數

static uint16_t crc16_update(uint16_t crc, const uint8_t* src, uint32_t len) {
  for (uint32_t j = 0; j < len; ++j) {
    crc ^= (uint16_t)src[j] << 8;
    for (uint8_t i = 0; i < 8; ++i) {
      uint16_t tmp = crc << 1;
      if (crc & 0x8000) tmp ^= 0x1021;  // CCITT
      crc = tmp;
    }
  }
  return crc;
}

static inline float     R4(const uint8_t* p){ float r; memcpy(&r,p,4); return r; }
static inline uint32_t  U4(const uint8_t* p){ uint32_t u; memcpy(&u,p,4); return u; }

// 送一條 ASCII 指令（自動補 CRLF）
static void send_cmd(const char* s){
  Serial.printf("[cmd] %s\\r\\n\n", s);
  Serial1.print(s);
  Serial1.print("\r\n");
}

// 把目前 Serial1 的輸入「暫時」原樣轉到 USB，方便看回應/確認
static void pump_serial1_to_usb(uint32_t ms){
  uint32_t t0 = millis();
  while (millis() - t0 < ms){
    while (Serial1.available()){
      Serial.write(Serial1.read());
    }
  }
}

// 嘗試從 buf 取出完整幀；成功則回傳丟掉的位元組數
static size_t try_parse_frame() {
  if (fill < 6) return 0;
  size_t i = 0;
  while (i + 1 < fill && !(buf[i]==0x5A && buf[i+1]==0xA5)) ++i;
  if (i){
    memmove(buf, buf + i, fill - i);
    fill -= i;
    if (fill < 6) return 0;
  }
  uint16_t payload_len = (uint16_t)buf[2] | ((uint16_t)buf[3] << 8);
  uint16_t frame_len   = 6 + payload_len;
  if (payload_len > 200 || frame_len > sizeof(buf)){
    memmove(buf, buf + 1, --fill);
    return 0;
  }
  if (fill < frame_len) return 0;

  uint16_t crc_rx = (uint16_t)buf[4] | ((uint16_t)buf[5] << 8);
  uint16_t crc = 0;
  crc = crc16_update(crc, buf, 4);
  crc = crc16_update(crc, buf + 6, payload_len);
  bool ok = (crc == crc_rx);

  if (buf[6] == 0x91 && (ok || !STRICT_CRC)) {
    const uint8_t* p = buf + 6;
    int8_t  tempC   = (int8_t)p[3];
    float   pressure= R4(p + 4);
    uint32_t ts     = U4(p + 8);
    float ax = R4(p + 12), ay = R4(p + 16), az = R4(p + 20);
    float gx = R4(p + 24), gy = R4(p + 28), gz = R4(p + 32);
    float mx = R4(p + 36), my = R4(p + 40), mz = R4(p + 44);
    float roll = R4(p + 48), pitch = R4(p + 52), yaw = R4(p + 56);

    static uint32_t last_ts = 0; 
    static float inst_fps = 0.0f; 
    static uint32_t print_n = 0;
    uint32_t dt = last_ts ? (uint32_t)(ts - last_ts) : 0;
    if (dt > 0 && dt < 1000) inst_fps = 1000.0f / (float)dt;
    last_ts = ts;

    if ((++print_n % PRINT_EVERY_N) == 0) {
      Serial.printf(
        "ts=%lu ms  T=%dC  EUL(deg)=%.2f,%.2f,%.2f  "
        "ACC(g)=%.3f,%.3f,%.3f  GYR(dps)=%.2f,%.2f,%.2f  "
        "MAG(uT)=%.2f,%.2f,%.2f  P=%.2f  FPS(inst)=%.1f\n",
        (unsigned long)ts, tempC, roll, pitch, yaw,
        ax, ay, az, gx, gy, gz, mx, my, mz, pressure, inst_fps
      );
    }

    static uint32_t fps_n = 0, fps_t0 = 0;
    if (fps_t0 == 0) fps_t0 = ts;
    fps_n++;
    if ((uint32_t)(ts - fps_t0) >= 1000) {
      float fps = fps_n * 1000.0f / (float)(ts - fps_t0);
      Serial.printf("[FPS] %.1f\n", fps);
      fps_n = 0;
      fps_t0 = ts;
    }
    if (!ok) Serial.println("[warn] CRC mismatch — 已寬鬆解析");
  }

  memmove(buf, buf + frame_len, fill - frame_len);
  fill -= frame_len;
  return frame_len;
}

void setup() {
  Serial.begin(PC_BAUD);
  while (!Serial) {}
  Serial.println("HI04M3 decoder — booting");

  // 1) 先用模組原始波特率接上
  Serial1.begin(SENSOR_BAUD_BOOT);
  Serial.printf("[boot] Sensor set to %u and LOG HI91 ONTIME 0...\n", SENSOR_BAUD_RUN);

  // 2) 先關掉既有輸出，避免指令被資料流干擾
  send_cmd(CMD_LOG_OFF);
  pump_serial1_to_usb(50);   // 看一下是否有回應字串（可選）

  // 3) 切到 921600（立刻生效），並把 MCU 端也切過去
  char baudCmd[32];
  snprintf(baudCmd, sizeof(baudCmd), "%s %u", CMD_SERIALCONFIG, SENSOR_BAUD_RUN);
  send_cmd(baudCmd);
  Serial1.flush();
  delay(80);                 // 留點時間讓模組切速
  Serial1.end();
  Serial1.begin(SENSOR_BAUD_RUN);
  Serial.println("[boot] Serial1 re-open at 921600");

  // 4) 重新開啟 1kHz 輸出
  delay(50);
  send_cmd(CMD_LOG_1KHZ);
  pump_serial1_to_usb(50);   // 可看到模組回應（若有）

  Serial.println("\n提示：此視窗也可手動輸入指令，例如：");
  Serial.println("  LOG HI91 ONTIME 0.01   (100 Hz)");
  Serial.println("  LOG HI91 ONTIME 0      (關閉 HI91)");
  Serial.println("  SERIALCONFIG 115200    (改回 115200，立即生效)\n");
}

void loop() {
  // 把感測器資料收進緩衝
  while (Serial1.available()) {
    if (fill < sizeof(buf)) buf[fill++] = (uint8_t)Serial1.read();
    else fill = 0; // overflow 防護
  }
  // 盡可能多解析
  while (try_parse_frame()) {}

  // 允許從 PC 丟 ASCII 指令到模組
  while (Serial.available()) {
    char ch = (char)Serial.read();
    Serial1.write(ch);
  }
}

