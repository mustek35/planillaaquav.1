#!/usr/bin/env python3
"""
Aplicación simplificada sin Redis para desarrollo local
"""

import logging
import psycopg2
from datetime import datetime, timedelta
import pytz

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

# SocketIO SIN Redis (solo para desarrollo local)
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

# RUTAS
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
@app.route('/api/alarms')
@login_required
def api_get_alarms():
    try:
        alarms = get_alarms_data()
        return jsonify(alarms)
    except Exception as e:
        logger.error(f"Error obteniendo alarmas: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

@app.route('/api/alerts')
@login_required
def api_get_alerts():
    try:
        alerts = get_alerts_data()
        return jsonify(alerts)
    except Exception as e:
        logger.error(f"Error obteniendo alertas: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

@app.route('/api/voz')
@login_required
def api_get_voz():
    try:
        voz_data = get_voz_data()
        return jsonify(voz_data)
    except Exception as e:
        logger.error(f"Error obteniendo datos de voz: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

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

def format_duration(seconds):
    """Formatear duración en formato legible"""
    if not seconds:
        return "0 segundos"
    
    minutes, seconds = divmod(round(seconds), 60)
    if minutes > 0:
        return f"{minutes} minuto{'s' if minutes != 1 else ''} {seconds} segundo{'s' if seconds != 1 else ''}"
    else:
        return f"{seconds} segundo{'s' if seconds != 1 else ''}"

def update_observation(alarm_id, observation):
    """Actualizar observación de alarma"""
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
        
        update_observation(alarm_id, observation)
        
        emit('observation_updated', {
            'id': alarm_id,
            'observation': observation
        }, broadcast=True)
        
    except Exception as e:
        logger.error(f"Error actualizando observación: {e}")
        emit('error', {'message': 'Error actualizando observación'})

# ERROR HANDLERS
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Página no encontrada'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Error interno del servidor: {error}")
    return jsonify({'error': 'Error interno del servidor'}), 500

if __name__ == '__main__':
    logger.info("Iniciando aplicación simplificada...")
    socketio.run(app, host='127.0.0.1', port=5300, debug=True)