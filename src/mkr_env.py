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

# Buffers for averaging data
data_buffers = {
    'temperature': [],
    'humidity': [],
    'light': [],
    'uva': [],
    'uvb': [],
    'uv_index': [],
    'pressure': []
}

PUSH_INTERVAL = 60  # Push to Prometheus every 60 seconds
last_push_time = time.time()

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
        current_time = time.time()
        
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line == "TIME_REQUEST":
                current_epoch = int(time.mktime(time.localtime()))-18000; 
                ser.write(f"T{current_epoch}\n".encode())
                print(f"Sent time sync: {current_epoch}")
            try:
                data = json.loads(line)
                print(f"[MKR_ENV] Received data: {data}")

                # Buffer the data instead of pushing immediately
                data_buffers['temperature'].append(data.get('temperature', 0))
                data_buffers['humidity'].append(data.get('humidity', 0))
                data_buffers['light'].append(data.get('light', 0))
                data_buffers['uva'].append(data.get('uva', 0))
                data_buffers['uvb'].append(data.get('uvb', 0))
                data_buffers['uv_index'].append(data.get('uv_index', 0))
                data_buffers['pressure'].append(data.get('pressure', 0))
                
            except json.JSONDecodeError:
                print(f"[MKR_ENV] Invalid JSON: {line}")
        
        # Push to Prometheus every PUSH_INTERVAL seconds
        if current_time - last_push_time >= PUSH_INTERVAL:
            if any(data_buffers.values()):  # Only push if we have data
                # Calculate averages
                TEMP_GAUGE.set(sum(data_buffers['temperature']) / len(data_buffers['temperature']) if data_buffers['temperature'] else 0)
                HUM_GAUGE.set(sum(data_buffers['humidity']) / len(data_buffers['humidity']) if data_buffers['humidity'] else 0)
                LIGHT_GAUGE.set(sum(data_buffers['light']) / len(data_buffers['light']) if data_buffers['light'] else 0)
                UVA_GAUGE.set(sum(data_buffers['uva']) / len(data_buffers['uva']) if data_buffers['uva'] else 0)
                UVB_GAUGE.set(sum(data_buffers['uvb']) / len(data_buffers['uvb']) if data_buffers['uvb'] else 0)
                UV_INDEX_GAUGE.set(sum(data_buffers['uv_index']) / len(data_buffers['uv_index']) if data_buffers['uv_index'] else 0)
                PRESSURE_GAUGE.set(sum(data_buffers['pressure']) / len(data_buffers['pressure']) if data_buffers['pressure'] else 0)
                
                print(f'[PROMETHEUS] Metrics updated with averages from {sum(len(v) for v in data_buffers.values()) // 7} data points.')
                
                # Clear buffers for next interval
                for key in data_buffers:
                    data_buffers[key] = []
            
            last_push_time = current_time
            
    except (OSError, serial.SerialException) as e:
        print(f"Connection lost: {e}")
        ser.close()
        time.sleep(1)
        ser = connect_serial() # This restarts the connection