static const int kRedPin = 9;
static const int kGreenPin = 10;
static const int kBluePin = 11;

static const int kLedPin = 13;

struct Color {
  byte red;
  byte green;
  byte blue;
};

int DEBUG = 0;      // DEBUG counter; if set to 1, will write values back via serial

// State after receiving last byte.
enum State {
  START,
  HEADER_1,
  HEADER_2,
  COLOR_R,
  COLOR_G,
  COLOR_B,
};

State state;
Color color;

// Set up
void setup()
{ 
  pinMode(kRedPin, OUTPUT);
  pinMode(kGreenPin, OUTPUT);
  pinMode(kBluePin, OUTPUT);
  pinMode(kLedPin, OUTPUT);

  Serial.begin(9600);  // ...set up the serial ouput 
  
  // Initial state.
  state = START;
  
  color.red = 0;
  color.blue = 0;
  color.green = 0;
}

// Sends color values to PWM pins.
void writeColor(const struct Color& color) {
  analogWrite(kRedPin, color.red);
  analogWrite(kGreenPin, color.green);
  analogWrite(kBluePin, color.blue);
}

void loop()
{ 
  if (Serial.available() <= 0) {
    return;
  }
  
  // Read in data from serial port, presumably coming from Raspberry Pi.
  const byte incoming_byte = Serial.read();
  
  if (DEBUG) {
    Serial.println(incoming_byte);
  }
  
  switch (state) {
    case START: {
      if (incoming_byte == 0xFF) {
        state = HEADER_1;
      }
      break;
    }

    case HEADER_1: {
      if (incoming_byte == 0xFE) {
        state = HEADER_2;
      } else {
        state = START;
      }
      break;
    }

    case HEADER_2: {
      color.red = incoming_byte;
      state = COLOR_R;
      break;
    }
    
    case COLOR_R: {
      color.green = incoming_byte;
      state = COLOR_G;
      break;
    }

    case COLOR_G: {
      color.blue = incoming_byte;
      state = COLOR_B;
      break;
    }
  
    case COLOR_B: {
      if (incoming_byte == 0x00) {
        // Update live color.
        writeColor(color);
        digitalWrite(kLedPin, 1);
      }
      state = START;
      break;
    }
  }
}
