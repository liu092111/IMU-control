/*******************************************************************************
    @file:   dds_sinewaves_with_adc.ino
    @brief:  AD9106 DDS sine wave generator + Teensy ADC monitoring
    @note:   Modified for Teensy 4.1 with ADC monitoring on A0
*******************************************************************************/

#include <AD9106.h>

// Initialize AD9106 with CS 10 and default reset, trigger, en_cvddx
AD9106 device(10);

// Toggle OP_AMPS to true/false for on-board amplifiers.
// Set FCLK to 0 to use on-board oscillator, otherwise set to frequency of
// external clock.
const bool OP_AMPS = true;
const float FCLK = 0;

// ADC settings
const int ADC_PIN = A0;           // ADC input pin
const int SAMPLE_RATE = 10000;    // 10kHz sampling rate (adjust based on your sine wave frequency)
const int NUM_SAMPLES = 1000;     // Number of samples to collect
const float ADC_RESOLUTION = 4095.0; // 12-bit ADC for Teensy 4.1
const float ADC_VOLTAGE_REF = 3.3;   // Teensy 4.1 ADC reference voltage

char stop_start = 's';
char measure_cmd = 'm';
bool started = false;
unsigned long last_sample_time = 0;
unsigned long sample_interval;

void setup() {
  Serial.begin(115200); // Higher baud rate for faster data transfer
  while (!Serial) {
    delay(10);
  }
  Serial.println("*** Teensy 4.1 + AD9106 DDS + ADC Monitor Ready ***");

  // Calculate sampling interval in microseconds
  sample_interval = 1000000 / SAMPLE_RATE; // Convert to microseconds

  // Configure ADC for Teensy 4.1
  analogReadResolution(12); // 12-bit resolution (0-4095) for better precision
  // Note: Teensy 4.1 uses 3.3V reference by default, no need to set analogReference

  //  Begin AD9106.
  device.begin(OP_AMPS, FCLK);

  // Start SPI communication at 14MHz
  device.spi_init(14000000);

  // Reset AD9106 registers
  device.reg_reset();
  delay(1);
  
  // Configure sinewaves on all channels
  for (int i = 0; i < 4; i++) {
    device.setDDSsine(CHNL(i + 1));
    device.set_CHNL_DGAIN(CHNL(i + 1), 0x2000);  // Gain of 1/2
  }

  device.set_CHNL_DOFFSET(CHNL_1, 0x1000);
  device.set_CHNL_DDS_PHASE(CHNL_2, 0x4000);
  device.set_CHNL_START_DELAY(CHNL_3, 0x1500);

  //   Set DDS frequency - 你可以修改這個頻率
  device.setDDSfreq(1000); // 1kHz sine wave for testing

  // Update pattern to start
  device.update_pattern();
  started = true;
  
  Serial.println(F("Commands:"));
  Serial.println(F("'s' - Start/Stop pattern"));
  Serial.println(F("'m' - Measure and send ADC data"));
  Serial.println(F("Pattern started."));
}

void loop() {
  if (Serial.available()) {
    char command = Serial.read();
    
    if (command == 's') {
      started = !started;
      if (started) {
        device.start_pattern();
        Serial.println(F("Pattern started"));
      } else {
        device.stop_pattern();
        Serial.println(F("Pattern stopped"));
      }
    }
    
    else if (command == 'm') {
      if (started) {
        measureAndSendData();
      } else {
        Serial.println(F("Error: Pattern not started. Press 's' first."));
      }
    }
  }
}

void measureAndSendData() {
  Serial.println(F("START_DATA"));
  Serial.print(F("SAMPLE_RATE:"));
  Serial.println(SAMPLE_RATE);
  Serial.print(F("NUM_SAMPLES:"));
  Serial.println(NUM_SAMPLES);
  Serial.print(F("ADC_REF_VOLTAGE:"));
  Serial.println(ADC_VOLTAGE_REF);
  Serial.println(F("DATA_BEGIN"));
  
  unsigned long start_time = micros();
  
  for (int i = 0; i < NUM_SAMPLES; i++) {
    // Wait for next sample time
    while (micros() - start_time < i * sample_interval) {
      // Wait
    }
    
    // Read ADC value
    int adc_raw = analogRead(ADC_PIN);
    
    // Convert to voltage
    float voltage = (adc_raw / ADC_RESOLUTION) * ADC_VOLTAGE_REF;
    
    // Send timestamp (microseconds) and voltage
    Serial.print(micros() - start_time);
    Serial.print(F(","));
    Serial.print(voltage, 4); // 4 decimal places
    Serial.println();
  }
  
  Serial.println(F("DATA_END"));
}