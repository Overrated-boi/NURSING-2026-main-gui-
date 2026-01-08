# hardware.py
import serial
import threading

SERIAL_PORT = "COM6"   # Adjust if different
BAUD_RATE = 9600

# Dictionary to hold the latest sensor values
prev_values = {
    "HR": "--",
    "RR": "--",
    "SpO2": "--",
    "BP:SYS": "--",
    "BP:DYS": "--",
    "TEMP": "--"
}

# Last button scenario detected ("ECG1", "ECG2", "ECG3")
button_scenario = None

# Serial connection
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print(f"Connected to {SERIAL_PORT}")
except serial.SerialException as e:
    print(f"Could not open serial port: {e}")
    ser = None

def read_serial():
    """ Continuously reads data from Arduino and updates button_scenario + prev_values. """
    global button_scenario

    while ser:
        try:
            raw_bytes = ser.readline()
            if not raw_bytes:
                continue

            raw = raw_bytes.decode(errors="ignore").strip()
            if not raw:
                continue

            # --- Detect ECG button messages ---
            if raw in ("ECG1", "ECG2", "ECG3"):
                if button_scenario != raw:
                    button_scenario = raw
                    # print(f" Button Press Detected → {button_scenario}")
                    # print(f" Button Press Detected → {button_scenario}")
                continue

            # --- Parse sensor values ---
            if "," in raw:
                parts = raw.split(",")
                if len(parts) % 2 == 0:  # valid key,value pairs
                    values = dict(zip(parts[::2], parts[1::2]))
                    for key in prev_values:
                        if key in values:
                            prev_values[key] = values[key]

                    # Debug (optional)
                    # print(f"Sensors → {prev_values}")

        except Exception as e:
            print(f"Serial Error: {e}")


def start_reader():
    """Start background thread for serial reading."""
    if ser:
        t = threading.Thread(target=read_serial, daemon=True)
        t.start()
