from celery import Celery
import pytz
from datetime import datetime, timedelta, time as datetime_time
from gevent import sleep
import psycopg2
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

# Configuración de Celery
app = Celery('voz_tasks', broker='redis://10.11.10.26:6379/0', backend='redis://10.11.10.26:6379/0')

app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='America/Santiago',
    enable_utc=True,
)

# Función para obtener la conexión a la base de datos
def get_db_connection(retries=15, delay=2):
    attempt = 0
    while attempt < retries:
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASS
            )
            return conn
        except psycopg2.OperationalError as e:
            attempt += 1
            print(f"Attempt {attempt} of {retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
            else:
                raise

@app.task
def voz_data_updater():
    from app import socketio, get_voz_data, get_alarm_data_for_voice, has_voz_data_changed
    
    chile_tz = pytz.timezone('America/Santiago')
    
    while True:
        current_time = datetime.now(chile_tz).time()
        start_time_allowed = datetime_time(18, 30)
        end_time_allowed = datetime_time(7, 0)
        
        if start_time_allowed <= current_time or current_time <= end_time_allowed:
            sleep_interval = 1  # 1 segundo durante el turno nocturno
        else:
            sleep_interval = 5  # 5 segundos fuera del turno nocturno
        
        start_time = time.time()
        voz_data = get_voz_data()
        alarms_data = get_alarm_data_for_voice()
        combined_data = voz_data + alarms_data
        combined_data.sort(key=lambda x: x['timestamp'], reverse=True)
        
        if has_voz_data_changed(combined_data):
            socketio.emit('voz_data_update', combined_data)
        
        end_time = time.time()
        print(f"voz_data_updater took {end_time - start_time:.4f} seconds")
        
        sleep(sleep_interval)