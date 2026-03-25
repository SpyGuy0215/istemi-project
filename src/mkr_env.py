import serial
import json
import time
from prometheus_client import start_http_server, Gauge

TEMP_GAUGE = Gauge('mkr_env_temp_f', 'Temperature in Fahrenheit')
HUM_GAUGE = Gauge('mkr_env_humidity', 'Humidity in Percent')
LIGHT_GAUGE = Gauge('mkr_env_light', 'Light Level')
UVA_GAUGE = Gauge('mkr_env_uva', 'UVA Level')
UVB_GAUGE = Gauge('mkr_env_uvb', 'UVB Level')
UV_INDEX_GAUGE = Gauge('mkr_env_uv_index', 'UV Index')
PRESSURE_GAUGE = Gauge('mkr_env_pressure', 'Pressure')

start_http_server(8000)
print('[PROMETHEUS] Exporter started on port 8000')

def connect_serial():
    while True:
        try:
            ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
            ser.reset_input_buffer()
            print("[MKR_ENV] Connected to Arduino.")
            return ser
        except serial.SerialException as e:
            print(f"[MKR_ENV] Failed to connect: {e}")
            time.sleep(5)

ser = connect_serial()
while True:
    try:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line == "TIME_REQUEST":
                current_epoch = int(time.mktime(time.localtime()))-18000; 
                ser.write(f"T{current_epoch}\n".encode())
                print(f"Sent time sync: {current_epoch}")
            try:
                data = json.loads(line)
                print(f"[MKR_ENV] Received data: {data}")

                TEMP_GAUGE.set(data.get('temperature', 0))
                HUM_GAUGE.set(data.get('humidity', 0))
                LIGHT_GAUGE.set(data.get('light', 0))
                UVA_GAUGE.set(data.get('uva', 0))
                UVB_GAUGE.set(data.get('uvb', 0))
                UV_INDEX_GAUGE.set(data.get('uv_index', 0))
                PRESSURE_GAUGE.set(data.get('pressure', 0))
                print('[PROMETHEUS] Metrics updated.')
            except json.JSONDecodeError:
                print(f"[MKR_ENV] Invalid JSON: {line}")
            
    except (OSError, serial.SerialException) as e:
        print(f"Connection lost: {e}")
        ser.close()
        time.sleep(1)
        ser = connect_serial() # This restarts the connection