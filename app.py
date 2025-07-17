from gevent import monkey
monkey.patch_all()  # Mover esto al inicio
import os
import logging
import psycopg2
import base64
import threading
import pytz
import select
import psycopg2.extensions
import redis
import json
import re
import time
import logging
import psutil
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, send_file, Response, url_for, make_response, request, redirect, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit
from urllib.parse import quote, unquote
from functools import cmp_to_key
from psycopg2.extras import RealDictCursor
from io import BytesIO
from base64 import b64encode
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from flask_cors import CORS
from pytz import timezone
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from dateutil.parser import isoparse
from tasks import update_observation_in_db  # Importar desde tasks.py
from celery.result import AsyncResult
from sqlalchemy.sql import text
from datetime import datetime, time as datetime_time
from database import db_manager

# Inicializa una variable para almacenar el último timestamp procesado
last_processed_timestamp = None
app = Flask(__name__)
socketio = SocketIO(app) 

# Configuración de la base de datos
DATABASE_URL = 'postgresql+psycopg2://orca:estadoscam.@179.57.170.61:24301/Aquachile'
engine = create_engine(
    DATABASE_URL,
    pool_size=250,
    max_overflow=150,
    pool_timeout=30,
)
db_session = scoped_session(sessionmaker(bind=engine))
cache = redis.Redis(host='10.11.10.26', port=6379, db=0)
try:
    cache.ping()
    print("Conexión a Redis exitosa")
except redis.ConnectionError:
    print("Error al conectar con Redis")

def get_db_session():
    return db_session
def cache_alarms_data(data):
    cache_key = "alarms_data"
    # Guardar los datos en Redis con una expiración de 60 segundos
    cache.set(cache_key, json.dumps(data), ex=60)  # El TTL es de 60 segundos

def get_cached_alarms_data():
    cache_key = "alarms_data"
    # Obtener los datos desde Redis
    cached_data = cache.get(cache_key)
    
    if cached_data:
        return json.loads(cached_data)
    else:
        print(f"No hay datos en caché para la clave: {cache_key}")
        return None

# Configuración de la aplicación Flask y SocketIO
logging.basicConfig(level=logging.INFO)
CORS(app)  # Habilitar CORS para todas las rutas
app.config['SECRET_KEY'] = 'remoto753524'
socketio = SocketIO(app, async_mode='gevent')
paused = False
selected_date = None
filter_active = False

# Configuración básica del logging
logging.basicConfig(level=logging.DEBUG)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, nombre, correo, password, perfil, empresa):
        self.id = id
        self.nombre = nombre
        self.correo = correo
        self.password = password
        self.perfil = perfil
        self.empresa = empresa

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    if user_data:
        return User(*user_data)
    return None

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('alerts'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        password = request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE correo = %s AND password = %s", (correo, password))
        user_data = cursor.fetchone()
        if user_data:
            user = User(*user_data)
            login_user(user)
            return redirect(url_for('alerts'))
        return "Usuario o contraseña incorrectos"
    return render_template('login.html')

@app.route('/alerts')
@login_required
def alerts():
    try:
        alerts_data = get_alerts_data()
        return render_template('index.html', alerts=alerts_data, user=current_user)
    except Exception as e:
        app.logger.error(f"Error accessing alerts data: {e}")
        return make_response("Failed to retrieve data", 500)

def update_alarm_status(alarm_id, observation_timestamp):
    session = get_db_session()

    try:
        # Obtén la alarma de la base de datos
        alarm = session.query(Alarm).filter_by(id=alarm_id).first()
        detection_time = alarm.timestamp
        response_time = observation_timestamp
        time_difference = (response_time - detection_time).total_seconds() / 60.0

        # Determina si la alarma fue gestionada dentro de los 10 minutos
        gestionado_dentro_de_tiempo = time_difference <= 10

        # Actualiza la alarma en la base de datos
        alarm.gestionado_time = response_time
        alarm.gestionado_dentro_de_tiempo = gestionado_dentro_de_tiempo
        session.commit()
        
    finally:
        session.close()


def get_cached_voz_data():
    cache_key = "voz_data"
    
    # Intentar obtener los datos de la caché
    cached_data = cache.get(cache_key)
    if cached_data:
        logging.debug("Datos obtenidos de la caché Redis")
        # Si hay datos en caché, deserializar y devolver
        return json.loads(cached_data)
    else:
        logging.debug("Datos no encontrados en caché, consultando la base de datos")
        # Si no hay datos en caché, consulta la base de datos
        voz_data = get_voz_data()  # Función original que consulta la base de datos
        
        # Guardar los datos en Redis con una expiración de 1 segundo
        cache.set(cache_key, json.dumps(voz_data), ex=300)
        
        logging.debug("Datos guardados en caché Redis")
        # Devolver los datos obtenidos de la base de datos
        return voz_data
    
# Mover la importación aquí si es necesario lanzar la tarea al iniciar la aplicación
def start_voice_data_updater():
    from voz_tasks import voz_data_updater
    voz_data_updater.apply_async()    
    
def get_alarms_data_for_calendar(start_date, end_date, start_time, end_time):
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cursor:
                if start_date == end_date:
                    query = """
                    SELECT id, centro, duracion, en_modulo, estado_verificacion, observacion,
                           timestamp::date AS fecha, timestamp::time AS hora
                    FROM alarmas
                    WHERE timestamp::date = %s AND timestamp::time BETWEEN %s AND %s
                    ORDER BY timestamp DESC
                    """
                    cursor.execute(query, (start_date, start_time, end_time))
                else:
                    query = """
                    SELECT id, centro, duracion, en_modulo, estado_verificacion, observacion,
                           timestamp::date AS fecha, timestamp::time AS hora
                    FROM alarmas
                    WHERE (
                            (timestamp::date = %s AND timestamp::time >= %s) OR
                            (timestamp::date = %s AND timestamp::time <= %s)
                          )
                    ORDER BY timestamp DESC
                    """
                    cursor.execute(query, (start_date, start_time, end_date, end_time))

                alarms_data = cursor.fetchall()
                return [
                    {
                        'id': alarm[0],
                        'centro': alarm[1],
                        'duracion': alarm[2],
                        'en_modulo': alarm[3],
                        'estado_verificacion': alarm[4],
                        'observacion': alarm[5],
                        'fecha': alarm[6].strftime('%Y-%m-%d'),
                        'hora': alarm[7].strftime('%H:%M:%S')
                    } for alarm in alarms_data
                ]
    except Exception as e:
        app.logger.error(f"Error ejecutando la consulta de alarmas: {e}")
        raise e

@app.route('/get_alarms_data_for_calendar', methods=['POST'])
def get_alarms_data_for_calendar_route():
    if request.method == 'POST':
        data = request.json
        app.logger.debug(f"Datos recibidos: {data}")
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        start_time = data.get('start_time')
        end_time = data.get('end_time')

        app.logger.debug(f"Start Date: {start_date}, End Date: {end_date}, Start Time: {start_time}, End Time: {end_time}")

        try:
            if start_date and end_date and start_time and end_time:
                alarms_data = get_alarms_data_for_calendar(start_date, end_date, start_time, end_time)
                return jsonify(alarms_data)
            else:
                app.logger.error('Fechas de inicio, fin y tiempos no proporcionadas')
                return jsonify({'error': 'Fechas de inicio, fin y tiempos no proporcionadas'}), 400
        except Exception as e:
            app.logger.error(f"Error en la obtención de datos de alarmas para el calendario: {e}")
            return jsonify({'error': 'Se produjo un error al obtener los datos de alarmas para el calendario'}), 500
    else:
        app.logger.error('Método de solicitud no permitido')
        return jsonify({'error': 'Método de solicitud no permitido'}), 405


   
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'data': 'Connected'})

@socketio.on('voz_data_update')
def handle_voz_data_update(data):
    print("Recibido voz_data_update:", data)
    # Aquí podrías manejar la actualización de la interfaz, pero por ahora solo imprime los datos.


def get_db_connection(retries=15, delay=2):
    attempt = 0
    while attempt < retries:
        try:
            conn = psycopg2.connect(
                host='179.57.170.61',
                port='24301',
                database='Aquachile',
                user='orca',
                password='estadoscam.'
            )
            return conn
        except psycopg2.OperationalError as e:
            attempt += 1
            print(f"Attempt {attempt} of {retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
            else:
                raise

@app.route('/get_images', methods=['GET'])
def get_images():
    timestamp = request.args.get('timestamp')
    center = request.args.get('center')

    if not timestamp or not center:
        return jsonify({"error": "Faltan parámetros"}), 400

    conn_pgadmin = get_db_connection_pgadmin()
    if conn_pgadmin is None:
        return jsonify({"error": "Error interno al conectar a la base de datos"}), 500

    try:
        with conn_pgadmin.cursor() as cursor:
            cursor.execute("""
                SELECT id 
                FROM cermaq_imagenes 
                WHERE timestamp = %s AND centro = %s
                """, (timestamp, center))
            cermaq_id = cursor.fetchone()
            if not cermaq_id:
                return jsonify({"error": "No se encontró el registro"}), 404

            cursor.execute("""
                SELECT encode(imagen, 'base64') as imagen 
                FROM cermaq_imagenes 
                WHERE id = %s
                """, (cermaq_id,))
            images = [record[0] for record in cursor.fetchall()]
            return jsonify(images)
    except Exception as e:
        print(f"Error al ejecutar la consulta: {e}")
        return jsonify({"error": "Error interno al ejecutar la consulta"}), 500
    finally:
        conn_pgadmin.close()

@app.route('/get_observacion', methods=['GET'])
def get_observacion():
    timestamp = request.args.get('timestamp')
    if not timestamp:
        return jsonify({'error': 'Timestamp is required'}), 400

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT observacion
                FROM alarmas
                WHERE timestamp = %s AND estado_verificacion = 'Persona detectada'
                """, (timestamp,))
            result = cursor.fetchone()
            if result:
                return jsonify({'observacion': result[0]})
            else:
                return jsonify({'observacion': 'Observación no encontrada'}), 404
            
@socketio.on('request_alarms_update')
def handle_alarms_update(data=None):
    if not paused:
        if data and 'startTime' in data and 'endTime' in data:
            start_time = data['startTime']
            end_time = data['endTime']
            if start_time and end_time:
                alarms_data = get_alarms_data(start_time, end_time)
                emit('alarms_update', alarms_data)
                return
        alarms_data = get_alarms_data()
        emit('alarms_update', alarms_data, broadcast=True)

# Mantener el estado anterior para voz_data
last_voz_data_sent = None

def has_voz_data_changed(new_data):
    cache_key = "last_voz_data_sent"
    
    # Obtener el último estado enviado desde Redis
    print("Intentando obtener el estado anterior de Redis...")
    cached_data = cache.get(cache_key)
    if cached_data:
        print("Datos anteriores encontrados en Redis.")
        last_voz_data_sent = json.loads(cached_data)
    else:
        print("No se encontraron datos anteriores en Redis.")
        last_voz_data_sent = None
    
    # Si no hay datos anteriores, consideramos que los datos han cambiado
    if last_voz_data_sent is None or len(new_data) != len(last_voz_data_sent):
        print("Datos nuevos detectados, actualizando el estado en Redis.")
        cache.set(cache_key, json.dumps(new_data))
        return True

    # Comparar los campos relevantes y registrar los cambios
    changes_detected = False
    changes_log = []
    
    for i, item in enumerate(new_data):
        if item['timestamp'] != last_voz_data_sent[i]['timestamp']:
            changes_log.append(f"Cambio en 'timestamp' para el ítem {i}: '{last_voz_data_sent[i]['timestamp']}' -> '{item['timestamp']}'")
            changes_detected = True
        if item['centro'] != last_voz_data_sent[i]['centro']:
            changes_log.append(f"Cambio en 'centro' para el ítem {i}: '{last_voz_data_sent[i]['centro']}' -> '{item['centro']}'")
            changes_detected = True
        # Añadir más campos si es necesario compararlos

    if changes_detected:
        # Registrar los cambios en los logs
        for change in changes_log:
            print(change)
        # Actualizar el estado en Redis
        cache.set(cache_key, json.dumps(new_data))
        return True
    
    print("No se detectaron cambios significativos en los datos.")
    return False

def voz_data_updater():
    chile_tz = pytz.timezone('America/Santiago')
    
    while True:
        # Obtener la hora actual en la zona horaria de Chile
        current_time = datetime.now(chile_tz).time()
        
        # Definir el rango de tiempo permitido (18:30 - 07:00)
        start_time_allowed = datetime_time(18, 30)
        end_time_allowed = datetime_time(7, 0)
        
        # Determinar el intervalo de tiempo basado en el horario
        if start_time_allowed <= current_time or current_time <= end_time_allowed:
            sleep_interval = 2  # 1 segundo durante el turno nocturno
        else:
            sleep_interval = 2  # 5 segundos fuera del turno nocturno
        
        start_time = time.time()
        
        # Obtener los datos de voz y alarma
        voz_data = get_voz_data()
        alarms_data = get_alarm_data_for_voice()
        combined_data = voz_data + alarms_data
        combined_data.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Verificar si los datos han cambiado usando Redis
        if has_voz_data_changed(combined_data):
            print("Datos cambiados, emitiendo actualización.")
            socketio.emit('voz_data_update', combined_data)
        else:
            print("No hay cambios en los datos, no se emite actualización.")
        
        end_time = time.time()
        print(f"voz_data_updater took {end_time - start_time:.4f} seconds")
        
        socketio.sleep(sleep_interval)  # Dormir por el intervalo determinado

def get_alarm_data_for_voice():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            now = datetime.now(pytz.timezone('America/Santiago'))
            five_minutes_ago = now - timedelta(minutes=5)
            five_minutes_ago_str = five_minutes_ago.strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
                SELECT DISTINCT ON (timestamp) timestamp, centro, estado_verificacion AS zonadealarma, '' AS imagen
                FROM alarmas 
                WHERE timestamp > %s AND estado_verificacion = 'Embarcación'
                ORDER BY timestamp DESC
                """, (five_minutes_ago_str,))
            
            records = cursor.fetchall()
            
            # Procesar registros para eliminar duplicados
            processed_data = {}
            for record in records:
                timestamp_str = record[0].strftime('%Y-%m-%d %H:%M:%S')
                if timestamp_str not in processed_data:
                    processed_data[timestamp_str] = {
                        'timestamp': timestamp_str,
                        'centro': record[1],
                        'zonadealarma': record[2],
                        'imagen': record[3]
                    }
            
            return list(processed_data.values())

def alarm_updater():
    timezone = pytz.timezone('America/Santiago')
    last_query_time = datetime.now(timezone)
    
    while True:
        now = datetime.now(timezone)
        start_day = now.replace(hour=7, minute=30, second=0, microsecond=0).time()
        end_day = now.replace(hour=18, minute=30, second=0, microsecond=0).time()

        if start_day <= now.time() < end_day:
            sleep_duration = 300  # 7 segundos
            query_interval = 600  # 10 minutos en segundos
        else:
            sleep_duration = 7  # 7 segundos
            query_interval = 7  # 7 segundos

        socketio.sleep(sleep_duration)
        
        if not paused:
            if (now - last_query_time).total_seconds() >= query_interval:
                filter_active_bytes = redis_client.get('filterActive')
                if filter_active_bytes is None:
                    filter_active = False
                else:
                    filter_active = filter_active_bytes.decode('utf-8') == 'True'
                if not filter_active:
                    alarms_data = get_alarms_data()
                    if has_data_changed(alarms_data):
                        socketio.emit('alarms_update', alarms_data)
                last_query_time = now  # Actualizar el último tiempo de consulta

# Función para calcular el tiempo de desconexión
def calculate_disconnection_time(disconnected_at):
    current_time = datetime.now()
    difference = current_time - disconnected_at
    minutes = difference.total_seconds() // 60
    hours = minutes // 60
    remaining_minutes = minutes % 60

    if hours > 0:
        return f"{int(hours)}h{int(remaining_minutes)}m"
    else:
        return f"{int(remaining_minutes)}m"

# Nueva ruta unificada
@app.route('/get_all_data')
def get_all_data():
    alerts_data = get_alerts_data()
    victron_data = get_victron_data()

    combined_data = {
        "alerts": alerts_data,
        "victron": victron_data
    }
    return jsonify(combined_data)

# Obtener datos de alertas
def get_alerts_data(start_time=None, end_time=None):
    timezone = pytz.timezone('America/Santiago')
    now = datetime.now(timezone)
    if start_time is None or end_time is None:
        if now.time() >= datetime.strptime("18:30", "%H:%M").time():
            start_time = now.replace(hour=18, minute=30, second=0, microsecond=0)
            end_time = (start_time + timedelta(days=1)).replace(hour=7, minute=30, second=0, microsecond=0)
        else:
            end_time = now.replace(hour=7, minute=30, second=0, microsecond=0)
            start_time = (end_time - timedelta(days=1)).replace(hour=18, minute=30, second=0, microsecond=0)
    
    query = """
    SELECT timestamp, centro, alerta, contador
    FROM alertas
    WHERE timestamp BETWEEN %s AND %s
    ORDER BY timestamp DESC
    """
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (start_time, end_time))
                alerts = cursor.fetchall()
                return [{
                    'timestamp': alert[0].strftime('%Y-%m-%d %H:%M:%S'),
                    'centro': alert[1],
                    'alerta': alert[2],
                    'contador': alert[3],
                } for alert in alerts]
    except psycopg2.Error as e:
        print(f"Error retrieving data from alertas table: {e}")
        return []

def update_observation_in_db_sync(alarm_id, observation, observation_timestamp, action):
    """Actualizar observación de alarma y calcular si fue gestionada a tiempo."""
    try:
        chile_tz = timezone('America/Santiago')
        observation_timestamp = observation_timestamp.astimezone(chile_tz)

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Obtener la hora de detección para calcular la diferencia
                cursor.execute("SELECT timestamp FROM alarmas WHERE id = %s", (alarm_id,))
                result = cursor.fetchone()
                detection_time = result[0] if result else None

                gestionado_dentro = None
                if detection_time:
                    diff_minutes = (observation_timestamp - detection_time).total_seconds() / 60.0
                    gestionado_dentro = diff_minutes <= 10

                cursor.execute(
                    """
                    UPDATE alarmas
                    SET observacion = %s, observation_timestamp = %s, observacion_texto = %s,
                        accion = %s, gestionado_time = %s, gestionado_dentro_de_tiempo = %s
                    WHERE id = %s
                    """,
                    (
                        observation,
                        observation_timestamp,
                        observation,
                        action,
                        observation_timestamp,
                        gestionado_dentro,
                        alarm_id,
                    ),
                )
                conn.commit()
    except psycopg2.Error as e:
        print(f"Error updating observation in the database: {e}")

def get_voz_data():
    with db_manager.get_connection() as conn:
        with conn.cursor() as cursor:
            timezone = pytz.timezone('America/Santiago')
            now = datetime.now(timezone)
            
            # Definir los intervalos de tiempo
            start_of_day = now.replace(hour=7, minute=30, second=0, microsecond=0)
            end_of_day = now.replace(hour=18, minute=30, second=0, microsecond=0)

            if start_of_day.time() <= now.time() < end_of_day.time():
                # Período de 07:30 AM a 18:30 PM, intervalos de 1 minuto
                time_interval = now - timedelta(minutes=1)
            else:
                # Período de 18:30 PM a 07:30 AM, intervalos de 5 minutos
                time_interval = now - timedelta(minutes=5)

            time_interval_str = time_interval.strftime('%Y-%m-%d %H:%M:%S')
            now_str = now.strftime('%Y-%m-%d %H:%M:%S')  # Agregar el tiempo actual para la consulta

            cursor.execute("""
                SELECT timestamp, centro, zonadealarma, encode(imagen, 'base64') as imagen
                FROM voz 
                WHERE timestamp BETWEEN %s AND %s 
                ORDER BY timestamp DESC
                """, (time_interval_str, now_str))  # Usar el rango de tiempo correcto
            
            records = cursor.fetchall()
            return [{
                'timestamp': record[0].strftime('%Y-%m-%d %H:%M:%S'),
                'centro': record[1],
                'zonadealarma': record[2],
                'imagen': record[3]
            } for record in records]

# Función para determinar si los datos han cambiado
def has_data_changed(new_data, old_data):
    return new_data != old_data

# Mantenemos un estado de alertas y victron anterior
previous_data = {
    "alerts": [],
    "victron": {}
}

def combined_data_updater():
    global previous_data
    while True:
        # Obtener datos de alertas y victron
        alerts_data = get_alerts_data()
        victron_data = get_victron_data()

        new_data = {
            "alerts": alerts_data,
            "victron": victron_data
        }

        if has_data_changed(new_data, previous_data):  # Asegúrate de que se pasen dos argumentos aquí
            socketio.emit('data_update', new_data)
            previous_data = new_data

        socketio.sleep(120)  # Verificar cada 60 segundos

# Obtener datos de Victron
def get_victron_data():
    conn = get_db_connection()
    if conn is None:
        return {"error": "Error interno al conectar a la base de datos"}

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT timestamp, centro, porcentaje, enlace 
                FROM aquachile_victron 
                ORDER BY timestamp DESC 
                LIMIT 1
            """)
            record = cursor.fetchone()
            if record:
                data = {
                    'timestamp': record[0].strftime('%Y-%m-%d %H:%M:%S'),
                    'centro': record[1],
                    'porcentaje': record[2],
                    'enlace': record[3]
                }
                # Calcular tiempo de desconexión si está desconectado
                if data['enlace'].startswith('sin conexion'):
                    disconnected_at = datetime.strptime(data['timestamp'], '%Y-%m-%d %H:%M:%S')
                    data['disconnection_time'] = calculate_disconnection_time(disconnected_at)
                return data
            else:
                return {"error": "No se encontraron registros"}
    except Exception as e:
        print(f"Error al ejecutar la consulta: {e}")
        return {"error": "Error interno al ejecutar la consulta"}
    finally:
        conn.close()

@app.route('/fetch_image')
def fetch_image():
    alarm_id = request.args.get('alarm_id')
    if not alarm_id:
        return jsonify(error='ID de alarma no proporcionado'), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify(error='Error interno al conectar a la base de datos'), 500

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT imagen FROM alarmas WHERE id = %s", (alarm_id,))
        image_data = cursor.fetchone()
        conn.close()
        if image_data:
            image_base64 = base64.b64encode(image_data[0]).decode('utf-8')
            return jsonify(image=image_base64)
        else:
            return jsonify(error='No se encontró la imagen para el ID proporcionado'), 404
    except Exception as e:
        print(f"Error al ejecutar la consulta: {e}")
        return jsonify(error='Error interno al ejecutar la consulta'), 500

def get_alarms_data(start_time=None, end_time=None):
    session = get_db_session()
    timezone = pytz.timezone('America/Santiago')
    now = datetime.now(timezone)

    if now.time() >= datetime.strptime("18:00", "%H:%M").time():
        start_time = now.replace(hour=18, minute=30, second=0, microsecond=0)
        end_time = (start_time + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)
    else:
        end_time = now.replace(hour=7, minute=0, second=0, microsecond=0)
        start_time = (end_time - timedelta(days=1)).replace(hour=18, minute=30, second=0, microsecond=0)

    query_alarms = text("""
    SELECT id, centro, duracion, en_modulo, estado_verificacion, observacion, timestamp, 
           observation_timestamp, observacion_texto, accion, gestionado_time, gestionado_dentro_de_tiempo
    FROM alarmas
    WHERE estado_verificacion = 'Persona detectada' OR (timestamp BETWEEN :start_time AND :end_time)
    ORDER BY timestamp DESC
    """)
    
    try:
        result_alarms = session.execute(query_alarms, {'start_time': start_time, 'end_time': end_time}).fetchall()

        alarms_data = []
        for a in result_alarms:
            # Calcular si la alarma fue gestionada dentro de los 10 minutos si no está ya calculado
            if a.observation_timestamp and a.gestionado_time is None:
                gestionado_time = a.observation_timestamp
                tiempo_transcurrido = (gestionado_time - a.timestamp).total_seconds() / 60.0
                gestionado_dentro_de_tiempo = tiempo_transcurrido <= 10

                # Actualizar la base de datos con esta información
                session.execute(
                    text("""
                        UPDATE alarmas
                        SET gestionado_time = :gestionado_time, gestionado_dentro_de_tiempo = :gestionado_dentro_de_tiempo
                        WHERE id = :alarm_id
                    """),
                    {
                        'gestionado_time': gestionado_time,
                        'gestionado_dentro_de_tiempo': gestionado_dentro_de_tiempo,
                        'alarm_id': a.id
                    }
                )
                session.commit()

            alarms_data.append({
                'id': a.id,
                'fecha': a.timestamp.strftime('%Y-%m-%d'),
                'hora': a.timestamp.strftime('%H:%M:%S'),
                'centro': a.centro,
                'duracion': format_duration(a.duracion),
                'en_modulo': "Módulo" if a.en_modulo else "Fuera del Módulo",
                'estado_verificacion': a.estado_verificacion,
                'observacion': a.observacion or "",
                'gestionado': bool(a.observacion and a.observacion.strip()),
                'gestionado_time': a.gestionado_time.strftime('%H:%M') if a.gestionado_time else None,
                'gestionado_dentro_de_tiempo': a.gestionado_dentro_de_tiempo,
                'observacion_texto': a.observacion_texto or "",
                'accion': a.accion or ""
            })
        
        return alarms_data
    
    finally:
        session.remove()  # Asegúrate de cerrar la sesión

def format_duration(seconds):
    minutes, seconds = divmod(round(seconds), 60)
    if minutes > 0:
        return f"{minutes} minuto{'s' if minutes != 1 else ''} {seconds} segundo{'s' if seconds != 1 else ''}"
    else:
        return f"{seconds} segundo{'s' if seconds != 1 else ''}"
    
def get_center_detections(filter_status=None):
    alarms_data = get_alarms_data()  
    center_counts = {}
    
    for alarm in alarms_data:
        duracion_str = alarm.get('duracion', '0 segundos')
        duracion_num = int(re.findall(r'\d+', duracion_str)[0])

        if filter_status == "Duración" and duracion_num <= 7:
            continue
        
        if filter_status == "Falso-Positivo" and alarm['estado_verificacion'] == 'Falso-Positivo':
            continue
        elif filter_status == "Dentro del Módulo" and alarm['en_modulo'] != 'Módulo':
            continue
        elif filter_status == "Fuera del Módulo" and alarm['en_modulo'] == 'Módulo':
            continue
        elif filter_status == "Zona Crítica" and alarm['estado_verificacion'] != 'Zona Crítica':
            continue
        elif filter_status == "Embarcación" and alarm['estado_verificacion'] != 'Embarcación':
            continue
        elif filter_status == "Detección en Modulo" and alarm['estado_verificacion'] != 'Detección en Modulo':
            continue
        elif filter_status == "No Gestionado" and alarm['gestionado']:
            continue  # Filtra las alarmas que están gestionadas

        centro = alarm['centro']
        center_counts[centro] = center_counts.get(centro, 0) + 1

    return [{'name': center, 'value': count} for center, count in center_counts.items()]

def get_detections_by_location():
    alarms_data = get_alarms_data()
    critical_zone_alarms = [alarm for alarm in alarms_data if alarm['estado_verificacion'] == 'Zona Crítica']
    
    location_counts = {'Dentro del Módulo': {}, 'Fuera del Módulo': {}}
    for alarm in critical_zone_alarms:
        location_key = 'Dentro del Módulo' if alarm['en_modulo'] == 'Módulo' else 'Fuera del Módulo'
        centro = alarm['centro']
        
        if centro not in location_counts[location_key]:
            location_counts[location_key][centro] = 0
        
        location_counts[location_key][centro] += 1

    return location_counts

# Mantenemos un estado de alertas y victron anterior
previous_data = {
    "alerts": [],
    "victron": {}
}
last_data_sent = None

def has_combined_data_changed(new_data, old_data):
    return new_data != old_data

def has_center_data_changed(new_data):
    global last_data_sent
    if new_data != last_data_sent:
        last_data_sent = new_data
        return True
    return False

def combined_data_updater():
    global previous_data
    while True:
        # Obtener datos de alertas y victron
        alerts_data = get_alerts_data()
        victron_data = get_victron_data()

        new_data = {
            "alerts": alerts_data,
            "victron": victron_data
        }

        if has_combined_data_changed(new_data, previous_data):
            socketio.emit('data_update', new_data)
            previous_data = new_data

        socketio.sleep(60)  # Verificar cada 60 segundos

def background_thread():
    with app.app_context():
        while True:
            socketio.sleep(60)
            current_data = get_center_detections()
            if has_center_data_changed(current_data):
                socketio.emit('update_data', {
                    'center_detections': current_data
                }, namespace='/')


@socketio.on('request_center_detections')
def handle_request_center_detections():
    current_data = get_center_detections()
    if has_data_changed(current_data):
        emit('center_detections_data', current_data)

def listen_notifications():
    while True:
        try:
            conn = get_db_connection()
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            cursor.execute("LISTEN alarms_change;")
            app.logger.info("Listening for notifications on channel 'alarms_change'")

            while True:
                if select.select([conn], [], [], 5) == ([], [], []):
                    app.logger.info("Timeout: no new notifications.")
                else:
                    conn.poll()
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        app.logger.info(f"Received NOTIFY: {notify.pid}, {notify.channel}, {notify.payload}")
                        alarm_data = get_alarms_data()
                        socketio.emit('alarms_update', alarm_data)

        except Exception as e:
            app.logger.error(f"Error in listen_notifications: {e}")
        finally:
            cursor.close()
            conn.close()
        
        app.logger.info("Attempting to reconnect in 5 seconds...")
        time.sleep(15)

@app.route('/video-list')
def video_list_api():
    video_urls = get_video_urls()
    return jsonify(video_urls)

@app.route('/pause-data')
def pause_data():
    global paused
    paused = True
    return 'Data transmission paused'

@socketio.on('update_observation')
def handle_update_observation(data):
    alarm_id = data['id']
    new_observation = data['observation']
    observation_timestamp = isoparse(data['observation_timestamp'])
    action = data['action']

    # Llama a la tarea de Celery para actualizar la base de datos de forma asíncrona
    update_observation_in_db.apply_async(args=[alarm_id, new_observation, observation_timestamp, action])


    # Emitir el evento inmediatamente después de iniciar la tarea
    socketio.emit('observation_updated', {
        'id': alarm_id,
        'observation': new_observation,
        'observation_timestamp': observation_timestamp.isoformat(),
        'action': action
    }, namespace='/')


@app.route('/resume-data')
def resume_data():
    global paused
    paused = False
    return 'Data transmission resumed'

@app.route('/set-selected-date/<date>')
def set_selected_date(date):
    global selected_date
    selected_date = date
    return f'Selected date set to {date}'

@socketio.on('request_last_hour_data')
def handle_last_hour_data():
    now = datetime.now(pytz.timezone('America/Santiago'))
    one_hour_ago = now - timedelta(hours=1)
    alarms = get_alarms_from_db_since(one_hour_ago)
    emit('alarms_update', alarms)

@socketio.on('request_alerts_update')
def handle_alerts_update():
    alerts_data = get_alerts_data()
    emit('alerts_data_update', alerts_data, broadcast=True)

@app.errorhandler(500)
def internal_error(error):
    app.logger.error('Server Error: %s', (error))
    return "Error interno del servidor", 500

@socketio.on('alarms_change')
def handle_alarm_change(data):
    socketio.emit('update_row', data)

@socketio.on('request_data_in_range')
def handle_request_data_in_range(json):
    start_time = datetime.fromisoformat(json['startTime'])
    end_time = datetime.fromisoformat(json['endTime'])
    alarms_data = get_alarms_data(start_time, end_time)
    emit('alarms_data_in_range', alarms_data)

@socketio.on('request_initial_data')
def handle_request_initial_data():
    initial_data = get_center_detections()
    emit('update_data', initial_data)

@socketio.on('request_latest_data')
def handle_request_latest_data():
    latest_data = get_center_detections()
    emit('update_data', latest_data)

@socketio.on('request_filtered_data')
def handle_request_filtered_data(data):
    status = data['status']
    filtered_data = get_center_detections(status)
    emit('filtered_data', filtered_data)

@socketio.on('update_alert_description')
def handle_update_alert_description(data):
    alert_id = data['alert_id']
    new_description = data['description']
    emit('alert_description_updated', {'alert_id': alert_id, 'description': new_description}, broadcast=True)

def log_memory_usage():
    process = psutil.Process(os.getpid())
    print(f"Memory usage: {process.memory_info().rss / (1024 ** 2):.2f} MB")

def monitor_memory_usage():
    while True:
        log_memory_usage()
        time.sleep(60)  # Monitorea cada 60 segundos

def victron_data_updater():
    last_status = None
    last_center = None
    while True:
        conn = get_db_connection()
        if conn is None:
            socketio.sleep(60)  # Verificar más frecuentemente si no hay conexión
            continue

        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT timestamp, centro, porcentaje, enlace 
                    FROM aquachile_victron 
                    ORDER BY timestamp DESC 
                    LIMIT 1
                """)
                record = cursor.fetchone()
                if record:
                    current_status = record[3]
                    current_center = record[1]
                    if last_status != current_status or last_center != current_center:
                        last_status = current_status
                        last_center = current_center
                        data = {
                            'timestamp': record[0].strftime('%Y-%m-%d %H:%M:%S'),
                            'centro': record[1],
                            'porcentaje': record[2],
                            'enlace': record[3]
                        }
                        socketio.emit('victron_data_update', data)
        except Exception as e:
            print(f"Error al ejecutar la consulta: {e}")
        finally:
            conn.close()

        socketio.sleep(120)  # Verificar cada 120 segundos


# Ejecuta la monitorización en segundo plano
if __name__ == '__main__':
    # Hilo para monitorizar la memoria
    monitoring_thread = threading.Thread(target=monitor_memory_usage)
    monitoring_thread.daemon = True  # Para que el hilo se detenga cuando el proceso principal termine
    monitoring_thread.start()

    # Tareas en segundo plano para el manejo de datos y actualizaciones
    socketio.start_background_task(alarm_updater)
    socketio.start_background_task(voz_data_updater)
    start_voice_data_updater()  # Iniciar la tarea de voz
    socketio.start_background_task(background_thread)
    socketio.start_background_task(combined_data_updater)
    socketio.start_background_task(victron_data_updater)  # Asegúrate de que esta tarea esté incluida

    # Ejecutar la aplicación
    socketio.run(app, host='127.0.0.1', port=5300)
