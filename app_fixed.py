#!/usr/bin/env python3
"""
Aplicación completa del Sistema de Monitoreo Central (CMS)
Con todas las rutas y funcionalidades
"""

import logging
import signal
import sys
import psycopg2
import pytz
import base64
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuración de base de datos
DB_CONFIG = {
    'host': '179.57.170.61',
    'port': '24301',
    'database': 'Aquachile',
    'user': 'orca',
    'password': 'estadoscam.'
}

def get_db_connection():
    """Obtener conexión a la base de datos"""
    return psycopg2.connect(**DB_CONFIG)

# Crear aplicación Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'remoto753524'

# Habilitar CORS
CORS(app)

# SocketIO sin Redis
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Configurar Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class SimpleUser:
    """Usuario simple para Flask-Login"""
    def __init__(self, data):
        self.id = data[0]
        self.nombre = data[1]
        self.correo = data[2]
        self.password = data[3]
        self.perfil = data[4]
        self.empresa = data[5]
        # Propiedades requeridas por Flask-Login
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False
    
    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, nombre, correo, password, perfil, empresa
            FROM usuarios 
            WHERE id = %s
        """, (user_id,))
        
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return SimpleUser(user_data) if user_data else None
        
    except Exception as e:
        logger.error(f"Error cargando usuario {user_id}: {e}")
        return None

# RUTAS PRINCIPALES
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('alerts'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo')
        password = request.form.get('password')
        
        if not correo or not password:
            return render_template('login.html', error='Correo y contraseña requeridos')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, nombre, correo, password, perfil, empresa
                FROM usuarios 
                WHERE correo = %s AND password = %s
            """, (correo, password))
            
            user_data = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user_data:
                user = SimpleUser(user_data)
                login_user(user)
                logger.info(f"Usuario {correo} autenticado exitosamente")
                return redirect(url_for('alerts'))
            else:
                return render_template('login.html', error='Credenciales incorrectas')
                
        except Exception as e:
            logger.error(f"Error en autenticación: {e}")
            return render_template('login.html', error='Error interno del servidor')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logger.info(f"Usuario {current_user.correo} cerró sesión")
    logout_user()
    return redirect(url_for('login'))

@app.route('/alerts')
@login_required
def alerts():
    try:
        return render_template('index.html', user=current_user)
    except Exception as e:
        logger.error(f"Error cargando página de alertas: {e}")
        return "Error interno del servidor", 500

# API ENDPOINTS
@app.route('/get_all_data')
@login_required
def get_all_data():
    """Ruta unificada para obtener todos los datos"""
    try:
        alerts_data = get_alerts_data()
        victron_data = get_victron_data()

        combined_data = {
            "alerts": alerts_data,
            "victron": victron_data
        }
        return jsonify(combined_data)
    except Exception as e:
        logger.error(f"Error obteniendo datos combinados: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

@app.route('/api/alarms')
@login_required
def api_get_alarms():
    try:
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        
        if start_time:
            start_time = datetime.fromisoformat(start_time)
        if end_time:
            end_time = datetime.fromisoformat(end_time)
        
        alarms = get_alarms_data(start_time, end_time)
        return jsonify(alarms)
    except Exception as e:
        logger.error(f"Error obteniendo alarmas: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

@app.route('/api/alerts')
@login_required
def api_get_alerts():
    """API para obtener alertas"""
    try:
        alerts = get_alerts_data()
        return jsonify(alerts)
    except Exception as e:
        logger.error(f"Error obteniendo alertas: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

@app.route('/api/voz')
@login_required
def api_get_voz():
    """API para obtener datos de voz"""
    try:
        voz_data = get_voz_data()
        return jsonify(voz_data)
    except Exception as e:
        logger.error(f"Error obteniendo datos de voz: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

@app.route('/get_alarms_data_for_calendar', methods=['POST'])
def get_alarms_data_for_calendar_route():
    if request.method == 'POST':
        data = request.json
        app.logger.debug(f"Datos recibidos: {data}")
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        start_time = data.get('start_time')
        end_time = data.get('end_time')

        try:
            if start_date and end_date and start_time and end_time:
                alarms_data = get_alarms_data_for_calendar(start_date, end_date, start_time, end_time)
                return jsonify(alarms_data)
            else:
                return jsonify({'error': 'Fechas de inicio, fin y tiempos no proporcionadas'}), 400
        except Exception as e:
            app.logger.error(f"Error en la obtención de datos de alarmas para el calendario: {e}")
            return jsonify({'error': 'Se produjo un error al obtener los datos de alarmas para el calendario'}), 500

@app.route('/fetch_image')
def fetch_image():
    alarm_id = request.args.get('alarm_id')
    if not alarm_id:
        return jsonify(error='ID de alarma no proporcionado'), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT imagen FROM alarmas WHERE id = %s", (alarm_id,))
        image_data = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if image_data and image_data[0]:
            image_base64 = base64.b64encode(image_data[0]).decode('utf-8')
            return jsonify(image=image_base64)
        else:
            return jsonify(error='No se encontró la imagen para el ID proporcionado'), 404
    except Exception as e:
        logger.error(f"Error al ejecutar la consulta: {e}")
        return jsonify(error='Error interno al ejecutar la consulta'), 500

# FUNCIONES DE SERVICIO
def get_alarms_data(start_time=None, end_time=None):
    """Obtener datos de alarmas"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        timezone = pytz.timezone('America/Santiago')
        now = datetime.now(timezone)

        if not start_time or not end_time:
            if now.time() >= datetime.strptime("18:00", "%H:%M").time():
                start_time = now.replace(hour=18, minute=30, second=0, microsecond=0)
                end_time = (start_time + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)
            else:
                end_time = now.replace(hour=7, minute=0, second=0, microsecond=0)
                start_time = (end_time - timedelta(days=1)).replace(hour=18, minute=30, second=0, microsecond=0)

        cursor.execute("""
            SELECT id, centro, duracion, en_modulo, estado_verificacion, observacion, timestamp
            FROM alarmas
            WHERE timestamp BETWEEN %s AND %s
            ORDER BY timestamp DESC
        """, (start_time, end_time))
        
        alarms = cursor.fetchall()
        cursor.close()
        conn.close()
        
        alarms_data = []
        for alarm in alarms:
            alarms_data.append({
                'id': alarm[0],
                'fecha': alarm[6].strftime('%Y-%m-%d'),
                'hora': alarm[6].strftime('%H:%M:%S'),
                'centro': alarm[1],
                'duracion': format_duration(alarm[2]),
                'en_modulo': "Módulo" if alarm[3] else "Fuera del Módulo",
                'estado_verificacion': alarm[4],
                'observacion': alarm[5] or "",
                'gestionado': bool(alarm[5] and alarm[5].strip()),
                'gestionado_time': None,
                'gestionado_dentro_de_tiempo': None,
                'observacion_texto': alarm[5] or "",
                'accion': ""
            })
        
        return alarms_data
        
    except Exception as e:
        logger.error(f"Error obteniendo datos de alarmas: {e}")
        raise

def get_alarms_data_for_calendar(start_date, end_date, start_time, end_time):
    """Obtener datos de alarmas para calendario"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
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
        logger.error(f"Error ejecutando la consulta de alarmas: {e}")
        raise e
    finally:
        cursor.close()
        conn.close()

def get_alerts_data(start_time=None, end_time=None):
    """Obtener datos de alertas"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        timezone = pytz.timezone('America/Santiago')
        now = datetime.now(timezone)
        
        if not start_time or not end_time:
            if now.time() >= datetime.strptime("18:30", "%H:%M").time():
                start_time = now.replace(hour=18, minute=30, second=0, microsecond=0)
                end_time = (start_time + timedelta(days=1)).replace(hour=7, minute=30, second=0, microsecond=0)
            else:
                end_time = now.replace(hour=7, minute=30, second=0, microsecond=0)
                start_time = (end_time - timedelta(days=1)).replace(hour=18, minute=30, second=0, microsecond=0)
        
        cursor.execute("""
            SELECT timestamp, centro, alerta, contador
            FROM alertas
            WHERE timestamp BETWEEN %s AND %s
            ORDER BY timestamp DESC
        """, (start_time, end_time))
        
        alerts = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return [{
            'timestamp': alert[0].strftime('%Y-%m-%d %H:%M:%S'),
            'centro': alert[1],
            'alerta': alert[2],
            'contador': alert[3],
        } for alert in alerts]
        
    except Exception as e:
        logger.error(f"Error obteniendo datos de alertas: {e}")
        raise

def get_voz_data():
    """Obtener datos de voz recientes"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        timezone = pytz.timezone('America/Santiago')
        now = datetime.now(timezone)
        
        # Últimos 5 minutos
        time_interval = now - timedelta(minutes=5)

        cursor.execute("""
            SELECT timestamp, centro, zonadealarma, imagen
            FROM voz 
            WHERE timestamp BETWEEN %s AND %s 
            ORDER BY timestamp DESC
        """, (time_interval, now))
        
        records = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return [{
            'timestamp': record[0].strftime('%Y-%m-%d %H:%M:%S'),
            'centro': record[1],
            'zonadealarma': record[2],
            'imagen': record[3] or ''
        } for record in records]
        
    except Exception as e:
        logger.error(f"Error obteniendo datos de voz: {e}")
        raise

def get_victron_data():
    """Obtener datos de Victron"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT timestamp, centro, porcentaje, enlace 
            FROM aquachile_victron 
            ORDER BY timestamp DESC 
            LIMIT 1
        """)
        record = cursor.fetchone()
        cursor.close()
        conn.close()
        
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
        logger.error(f"Error al obtener datos de Victron: {e}")
        return {"error": "Error interno al ejecutar la consulta"}

def calculate_disconnection_time(disconnected_at):
    """Calcular tiempo de desconexión"""
    current_time = datetime.now()
    difference = current_time - disconnected_at
    minutes = difference.total_seconds() // 60
    hours = minutes // 60
    remaining_minutes = minutes % 60

    if hours > 0:
        return f"{int(hours)}h{int(remaining_minutes)}m"
    else:
        return f"{int(remaining_minutes)}m"

def get_center_detections(filter_status=None):
    """Obtener detecciones por centro para el gráfico"""
    alarms_data = get_alarms_data()  
    center_counts = {}
    
    for alarm in alarms_data:
        # Aplicar filtros si es necesario
        if filter_status == "Dentro del Módulo" and alarm['en_modulo'] != 'Módulo':
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
            continue

        centro = alarm['centro']
        center_counts[centro] = center_counts.get(centro, 0) + 1

    return [{'name': center, 'value': count} for center, count in center_counts.items()]

def format_duration(seconds):
    """Formatear duración en formato legible"""
    if not seconds:
        return "0 segundos"
    
    minutes, seconds = divmod(round(seconds), 60)
    if minutes > 0:
        return f"{minutes} minuto{'s' if minutes != 1 else ''} {seconds} segundo{'s' if seconds != 1 else ''}"
    else:
        return f"{seconds} segundo{'s' if seconds != 1 else ''}"

def update_observation_in_db_sync(alarm_id, observation, observation_timestamp=None, action=None):
    """Actualizar observación de alarma de forma síncrona"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE alarmas
            SET observacion = %s
            WHERE id = %s
        """, (observation, alarm_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Observación actualizada para alarma {alarm_id}")
        
    except Exception as e:
        logger.error(f"Error actualizando observación: {e}")
        raise

# EVENTOS SOCKETIO
@socketio.on('connect')
def handle_connect():
    logger.info(f"Cliente conectado: {request.sid}")
    emit('status', {'data': 'Conectado'})

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"Cliente desconectado: {request.sid}")

@socketio.on('request_alarms_update')
def handle_alarms_update(data=None):
    try:
        start_time = None
        end_time = None
        
        if data and 'startTime' in data and 'endTime' in data:
            start_time = datetime.fromisoformat(data['startTime'])
            end_time = datetime.fromisoformat(data['endTime'])
        
        alarms_data = get_alarms_data(start_time, end_time)
        emit('alarms_update', alarms_data)
    except Exception as e:
        logger.error(f"Error actualizando alarmas: {e}")
        emit('error', {'message': 'Error obteniendo datos'})

@socketio.on('update_observation')
def handle_update_observation(data):
    try:
        alarm_id = data['id']
        observation = data['observation']
        observation_timestamp = data.get('observation_timestamp')
        action = data.get('action')
        
        # Convertir timestamp si es necesario
        if observation_timestamp:
            from dateutil.parser import isoparse
            observation_timestamp = isoparse(observation_timestamp)
        
        # Actualizar observación de forma síncrona
        update_observation_in_db_sync(alarm_id, observation, observation_timestamp, action)
        
        emit('observation_updated', {
            'id': alarm_id,
            'observation': observation,
            'observation_timestamp': observation_timestamp.isoformat() if observation_timestamp else None,
            'action': action
        }, broadcast=True)
        
    except Exception as e:
        logger.error(f"Error actualizando observación: {e}")
        emit('error', {'message': 'Error actualizando observación'})

@socketio.on('request_initial_data')
def handle_request_initial_data():
    """Solicitar datos iniciales para gráficos"""
    try:
        initial_data = get_center_detections()
        emit('update_data', initial_data)
    except Exception as e:
        logger.error(f"Error obteniendo datos iniciales: {e}")
        emit('error', {'message': 'Error obteniendo datos iniciales'})

@socketio.on('request_latest_data')
def handle_request_latest_data():
    """Solicitar datos más recientes"""
    try:
        latest_data = get_center_detections()
        emit('update_data', latest_data)
    except Exception as e:
        logger.error(f"Error obteniendo datos recientes: {e}")
        emit('error', {'message': 'Error obteniendo datos'})

@socketio.on('request_filtered_data')
def handle_request_filtered_data(data):
    """Solicitar datos filtrados"""
    try:
        status = data['status']
        filtered_data = get_center_detections(status)
        emit('filtered_data', filtered_data)
    except Exception as e:
        logger.error(f"Error obteniendo datos filtrados: {e}")
        emit('error', {'message': 'Error obteniendo datos filtrados'})

@socketio.on('request_alerts_update')
def handle_alerts_update():
    """Solicitar actualización de alertas"""
    try:
        alerts_data = get_alerts_data()
        emit('alerts_data_update', alerts_data, broadcast=True)
    except Exception as e:
        logger.error(f"Error obteniendo alertas: {e}")
        emit('error', {'message': 'Error obteniendo alertas'})

# ERROR HANDLERS
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Página no encontrada'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Error interno del servidor: {error}")
    return jsonify({'error': 'Error interno del servidor'}), 500

def setup_signal_handlers():
    """Configurar manejadores de señales para cierre limpio"""
    def signal_handler(signum, frame):
        logger.info(f"Señal {signum} recibida, cerrando aplicación...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    setup_signal_handlers()
    logger.info("Iniciando aplicación completa en 127.0.0.1:5300")
    socketio.run(app, host='127.0.0.1', port=5300, debug=True)