import os
import logging
import psycopg2
import base64
import threading
import pytz
import select
import psycopg2.extensions
import redis
import eventlet
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, send_file, Response, url_for, make_response, request, redirect, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit
from urllib.parse import quote, unquote
from functools import cmp_to_key

# Configura el registro en nivel DEBUG para capturar toda la información posible
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'remoto753524'  # Asegúrate de definir una clave secreta
socketio = SocketIO(app, async_mode='eventlet')
paused = False
selected_date = None
filter_active = False


# Conexión a Redis
redis_client = redis.Redis(host='127.0.0.1', port=6379, db=0)

# Configuración del LoginManager
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
        return redirect(url_for('login'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        password = request.form['password']
        empresa = determine_empresa(correo)  # Determina la empresa basada en el correo
        if empresa is None:
            return "Empresa no encontrada para este correo", 404

        conn = get_db_connection()  # Asegúrate de que esta función obtenga la conexión adecuada
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE correo = %s AND empresa = %s", (correo, empresa))
        user_data = cursor.fetchone()
        if user_data and user_data[3] == password:  # Asegúrate de que la contraseña coincide
            user = User(*user_data)
            login_user(user)
            return redirect(url_for('alerts'))  # Redirige a la página de alertas
        else:
            return "Usuario o contraseña incorrectos"
    return render_template('login.html')

def determine_empresa(correo):
    # Esta es una implementación de ejemplo, necesitarías ajustar esto a tus propios datos.
    if "aquachile" in correo:
        return "aquachile"
    elif "caletabay" in correo:
        return "caletabay"
    else:
        return None

@app.route('/alerts')
@login_required  # Asumiendo que quieres mantener la protección de inicio de sesión
def alerts():
    try:
        alerts_data = get_alerts_data()
        return render_template('index.html', alerts=alerts_data, user=current_user)
    except Exception as e:
        app.logger.error(f"Error accessing alerts data: {e}")
        return make_response("Failed to retrieve data", 500)

@app.route('/get_alarms_data_for_calendar', methods=['POST'])
def get_alarms_data_for_calendar_route():
    if request.method == 'POST':
        data = request.json
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        app.logger.debug(f"Start Date: {start_date}, End Date: {end_date}")  # Agregar este registro

        try:
            if start_date and end_date:
                alarms_data = get_alarms_data_for_calendar(start_date, end_date)
                return jsonify(alarms_data)
            else:
                return jsonify({'error': 'Fechas de inicio y fin no proporcionadas'}), 400
        except Exception as e:
            app.logger.error(f"Error en la obtención de datos de alarmas para el calendario: {e}")
            return jsonify({'error': 'Se produjo un error al obtener los datos de alarmas para el calendario'}), 500
    else:
        return jsonify({'error': 'Método de solicitud no permitido'}), 405


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@socketio.on('connect')
def handle_connect():
    print('Client connected')

def get_db_connection():
    return psycopg2.connect(
        host='179.57.170.61',
        port='24301',
        database='caletabay',
        user='orca',
        password='estadoscam.'
    )

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
        # Si no se proveen tiempos específicos o son incorrectos, enviar los datos de la última hora
        alarms_data = get_alarms_data()
        emit('alarms_update', alarms_data, broadcast=True)

def voz_data_updater():
    while True:
        socketio.sleep(1)  # Intervalo de actualización cada 60 segundos
        voz_data = get_voz_data()  # Obtener los datos actuales de la tabla 'voz'
        socketio.emit('voz_data_update', voz_data)  # Emitir los datos a todos los clientes


# Solo emitir actualizaciones si no hay fecha específica solicitada
def alarm_updater():
    while True:
        socketio.sleep(1)  # Intervalo de actualización
        # Verificar si la transmisión está pausada
        if not paused:
            # Obtener el estado de Redis y convertirlo de bytes a string, luego a boolean
            filter_active_bytes = redis_client.get('filterActive')
            if filter_active_bytes is None:
                filter_active = False  # Asumimos que no está activo si no hay valor en Redis
            else:
                filter_active = filter_active_bytes.decode('utf-8') == 'True'

            if not filter_active:
                alarms_data = get_alarms_data()
                socketio.emit('alarms_update', alarms_data)

# Solo emitir actualizaciones si no hay fecha específica solicitada                
def get_image_by_alarm(date, center):
    conn = psycopg2.connect(
        host='179.57.170.61',
        port='24301',
        database='caletbay',
        user='orca',
        password='estadoscam.'
    )
             
def get_alerts_data(start_time=None, end_time=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    timezone = pytz.timezone('America/Santiago')

    now = datetime.now(timezone)
    if start_time is None or end_time is None:
        if now.time() >= datetime.strptime("12:00", "%H:%M").time():
            # Si es después de las 12:00 PM, el turno comienza en las 12:00 PM de hoy
            start_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
            end_time = (start_time + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
        else:
            # Si es antes de las 12:00 PM, el turno comenzó a las 12:00 PM del día anterior
            end_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
            start_time = (end_time - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    
    query = """
    SELECT timestamp, centro, alerta, contador
    FROM alertas
    WHERE timestamp BETWEEN %s AND %s
    ORDER BY timestamp DESC
    """
    try:
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
    finally:
        cursor.close()
        conn.close()




def alerts_data_updater():
    while True:
        socketio.sleep(60)  # Intervalo de actualización cada 60 segundos, ajusta como sea necesario
        alerts_data = get_alerts_data()  # Obtener los datos actuales de la tabla 'alertas'
        socketio.emit('alerts_data_update', alerts_data)  # Emitir los datos a todos los clientes

def update_observation_in_db(alarm_id, observation):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE alarmas SET observacion = %s WHERE id = %s", (observation, alarm_id))
                conn.commit()
    except psycopg2.Error as e:
        print(f"Error updating observation in the database: {e}")
def get_voz_data():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            # Obtener el tiempo actual en la zona horaria correcta
            now = datetime.now(pytz.timezone('America/Santiago'))
            # Calcular el tiempo de hace 5 minutos
            five_minutes_ago = now - timedelta(minutes=5)
            
            # Convertir el tiempo de hace 5 minutos a una cadena de caracteres para usar en la consulta
            five_minutes_ago_str = five_minutes_ago.strftime('%Y-%m-%d %H:%M:%S')

            # Crear la consulta SQL para seleccionar registros de los últimos 5 minutos
            cursor.execute("""
                SELECT timestamp, centro, zonadealarma 
                FROM voz 
                WHERE timestamp > %s 
                ORDER BY timestamp DESC
                """, (five_minutes_ago_str,))
            
            # Construir una lista de diccionarios con los resultados
            return [{
                'timestamp': record[0].strftime('%Y-%m-%d %H:%M:%S'),
                'centro': record[1],
                'zonadealarma': record[2]
            } for record in cursor.fetchall()]

def get_alarms_data(start_time=None, end_time=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    timezone = pytz.timezone('America/Santiago')

    # Determinar el rango de tiempo basado en la hora actual
    now = datetime.now(timezone)
    if now.time() >= datetime.strptime("12:00", "%H:%M").time():
        # Si es después de las 12:00 PM, el turno comienza en las 12:00 PM de hoy
        start_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
        end_time = (start_time + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    else:
        # Si es antes de las 12:00 PM, el turno comenzó a las 12:00 PM del día anterior
        end_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
        start_time = (end_time - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)

    query = """
    SELECT id, centro, duracion, en_modulo, estado_verificacion, observacion, timestamp
    FROM alarmas
    WHERE timestamp BETWEEN %s AND %s
    ORDER BY timestamp DESC
    """
    cursor.execute(query, (start_time, end_time))
    alarms_data = cursor.fetchall()
    conn.close()

    return [
        {
            'id': a[0],
            'fecha': a[6].strftime('%Y-%m-%d'),
            'hora': a[6].strftime('%H:%M:%S'),
            'centro': a[1],
            'duracion': format_duration(a[2]),
            'en_modulo': "Módulo" if a[3] else "Fuera del Módulo",
            'estado_verificacion': a[4],
            'observacion': a[5] or ""
        } for a in alarms_data
    ]

def format_duration(seconds):
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if hours > 0:
        parts.append(f"{hours} hora{'s' if hours > 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minuto{'s' if minutes > 1 else ''}")
    if seconds > 0 or not parts:
        parts.append(f"{seconds} segundo{'s' if seconds != 1 else ''}")
    return " ".join(parts)

    
def get_alarms_data_in_range():
    conn = get_db_connection()
    cursor = conn.cursor()
    timezone = pytz.timezone('America/Santiago')

    # Obtener la hora actual
    now = datetime.now(timezone)

    # Ajustar el tiempo de inicio y fin
    if now.time() < datetime.strptime("12:00", "%H:%M").time():
        # Si es antes de las 12 PM, ajustar el inicio al día anterior a las 12:00 PM
        end_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
        start_time = (end_time - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    else:
        # Si es después de las 12 PM, iniciar desde las 12:00 PM del día actual
        start_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
        end_time = (start_time + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)

    # Formato ISO para consulta SQL
    start_time_iso = start_time.isoformat()
    end_time_iso = end_time.isoformat()

    query = """
    SELECT id, centro, duracion, en_modulo, estado_verificacion, observacion, timestamp
    FROM alarmas
    WHERE timestamp BETWEEN %s AND %s
    ORDER BY timestamp DESC
    """
    cursor.execute(query, (start_time_iso, end_time_iso))
    alarms = cursor.fetchall()
    conn.close()

    return [
        {
            'id': alarm[0],
            'fecha': alarm[6].strftime('%Y-%m-%d'),
            'hora': alarm[6].strftime('%H:%M:%S'),
            'centro': alarm[1],
            'duracion': format_duration(alarm[2]),
            'en_modulo': "Módulo" if alarm[3] else "Fuera del Módulo",
            'estado_verificacion': alarm[4],
            'observacion': alarm[5] or ""
        } for alarm in alarms
    ]


def get_alarms_data_for_calendar(start_date, end_date):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT id, centro, duracion, en_modulo, estado_verificacion, observacion,
           timestamp::date AS fecha, timestamp::time AS hora
    FROM alarmas
    WHERE timestamp::date BETWEEN %s AND %s
    ORDER BY timestamp DESC
    """
    cursor.execute(query, (start_date, end_date))

    alarms_data = cursor.fetchall()
    conn.close()

    return [
        {
            'id': alarm[0],
            'centro': alarm[1],
            'duracion': alarm[2],
            'en_modulo': alarm[3],
            'estado_verificacion': alarm[4],
            'observacion': alarm[5],
            'fecha': alarm[6].strftime('%Y-%m-%d'),  # Formato de fecha
            'hora': alarm[7].strftime('%H:%M:%S')    # Formato de hora
        } for alarm in alarms_data
    ]


## Echarts
def get_center_detections(filter_status=None):
    alarms_data = get_alarms_data()  # Asegúrate de que esta función devuelve los datos transformados correctamente
    center_counts = {}
    for alarm in alarms_data:
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
        elif filter_status != "Falso-Positivo Verificar" and alarm['estado_verificacion'] == 'Falso-Positivo Verificar':
            continue
        centro = alarm['centro']
        center_counts[centro] = center_counts.get(centro, 0) + 1

    return [{'name': center, 'value': count} for center, count in center_counts.items()]




def get_detections_by_location():
    alarms_data = get_alarms_data()
    # Filtrar solo las alarmas que están en "Zona Crítica"
    critical_zone_alarms = [alarm for alarm in alarms_data if alarm['estado_verificacion'] == 'Zona Crítica']
    
    location_counts = {'Dentro del Módulo': {}, 'Fuera del Módulo': {}}
    for alarm in critical_zone_alarms:
        location_key = 'Dentro del Módulo' if alarm['en_modulo'] == 'Módulo' else 'Fuera del Módulo'
        centro = alarm['centro']
        
        # Inicializar el contador para cada centro si es necesario
        if centro not in location_counts[location_key]:
            location_counts[location_key][centro] = 0
        
        # Incrementar el contador para el centro específico dentro de la ubicación determinada
        location_counts[location_key][centro] += 1

    return location_counts

def background_thread():
    with app.app_context():
        while True:
            socketio.sleep(1)  # Intervalo de 5 segundos
            center_detections_data = get_center_detections()
            socketio.emit('update_data', {
                'center_detections': center_detections_data
            }, namespace='/')

@socketio.on('request_center_detections')
def handle_request_center_detections():
    data = get_center_detections()
    emit('center_detections_data', data)

# Asegúrate de que la función fetch_and_emit_alarm_data emite estos datos
def fetch_and_emit_alarm_data():
    alarms_data = get_alarms_data_in_range()
    socketio.emit('alarms_data_in_range', alarms_data)


# Esta función es un ejemplo de cómo podrías llamar a get_alarms_data_in_range
def fetch_and_emit_alarm_data():
    # Define el rango de tiempo deseado
    end_time = datetime.now(pytz.timezone('America/Santiago'))
    start_time = end_time - timedelta(days=1)
    start_time = start_time.replace(hour=18, minute=30, second=0, microsecond=0)
    if end_time.hour < 7:
        end_time = end_time.replace(hour=7, minute=0, second=0, microsecond=0)
    else:
        end_time += timedelta(days=1)
        end_time = end_time.replace(hour=7, minute=0, second=0, microsecond=0)

    alarms_data = get_alarms_data_in_range(start_time, end_time)
    socketio.emit('alarms_data_in_range', alarms_data)

def listen_notifications():
    conn = get_db_connection()
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute("LISTEN alarms_change;")

    print("Listening for notifications on channel 'alarms_change'")
    try:
        while True:
            if select.select([conn], [], [], 5) == ([], [], []):
                print("Timeout: no new notifications.")
            else:
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    print(f"Received NOTIFY: {notify.pid}, {notify.channel}, {notify.payload}")
                    alarm_data = get_alarms_data()  # Get fresh data
                    socketio.emit('alarms_update', alarm_data)  # Emit updated data
    finally:
        cursor.close()
        conn.close()

def create_sftp_client(host, port, username, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=port, username=username, password=password)
    sftp = client.open_sftp()
    return sftp

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
    update_observation_in_db(alarm_id, new_observation)

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

def get_alarms_from_db_since(time_stamp):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
    SELECT id, centro, duracion, en_modulo, estado_verificacion, observacion, timestamp
    FROM alarmas
    WHERE timestamp >= %s
    ORDER BY timestamp DESC
    """
    cursor.execute(query, (time_stamp,))
    alarms = cursor.fetchall()
    cursor.close()
    conn.close()
    return [{
        'id': a[0],
        'centro': a[1],
        'duracion': format_duration(a[2]),
        'en_modulo': "Módulo" if a[3] else "Fuera del Módulo",
        'estado_verificacion': a[4],
        'observacion': a[5],
        'timestamp': a[6].strftime('%Y-%m-%d %H:%M:%S')
    } for a in alarms]


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
    # Solo retransmitir la fila específica que ha cambiado
    socketio.emit('update_row', data)

@socketio.on('request_data_in_range')
def handle_request_data_in_range(json):
    start_time = datetime.fromisoformat(json['startTime'])
    end_time = datetime.fromisoformat(json['endTime'])
    alarms_data = get_alarms_data_in_range(start_time, end_time)
    emit('alarms_data_in_range', alarms_data)

@socketio.on('request_initial_data')
def handle_request_initial_data():
    initial_data = get_center_detections()  # Suponiendo que esta función devuelve todos los datos sin filtrar
    emit('update_data', initial_data)

@socketio.on('request_filtered_data')
def handle_request_filtered_data(data):
    status = data['status']
    filtered_data = get_center_detections(status)  # Asegúrate que esta función filtre los datos correctamente
    emit('filtered_data', filtered_data)

@socketio.on('update_alert_description')
def handle_update_alert_description(data):
    alert_id = data['alert_id']
    new_description = data['description']
    # Actualiza la base de datos aquí
    emit('alert_description_updated', {'alert_id': alert_id, 'description': new_description}, broadcast=True)

# Configura SocketIO para permitir conexiones desde el origen específico
socketio = SocketIO(app, cors_allowed_origins="https://cms.orcawan.uk")

# Configura SocketIO para permitir conexiones desde el origen específico
socketio = SocketIO(app, cors_allowed_origins=['http://10.11.10.26:8000', 'https://cms.orcawan.uk'])

if __name__ == '__main__':
    socketio.start_background_task(alarm_updater)
    socketio.start_background_task(voz_data_updater)
    socketio.start_background_task(background_thread)
    socketio.start_background_task(alerts_data_updater)
    socketio.run(app, host='0.0.0.0', port=5124)