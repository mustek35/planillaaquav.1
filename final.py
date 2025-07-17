import os
import logging
import paramiko
import psycopg2
from config import (
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASS,
    SFTP_HOST,
    SFTP_PORT,
    SFTP_USER,
    SFTP_PASS,
)
import base64
import threading
from flask import Flask, jsonify, render_template, send_file, Response, url_for, make_response
from urllib.parse import quote, unquote
from datetime import datetime
from functools import cmp_to_key
from flask_socketio import SocketIO, emit
# Configura el registro en nivel DEBUG para capturar toda la información posible
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
socketio = SocketIO(app)


@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('request_alarms_update')
def handle_alarms_update():
    alarm_data = get_alarms_data()  # Debes implementar esta función.
    emit('alarms_update', alarm_data)
def get_alarms_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, fecha, hora, centro, duracion, en_modulo, estado_verificacion, observacion FROM alarmas ORDER BY fecha DESC, hora DESC')
    alarms = cursor.fetchall()
    cursor.close()
    conn.close()
    
    alarms_data = [
        {
            'id': a[0],  # Incluye el 'id' en los datos.
            'fecha': str(a[1]),
            'hora': str(a[2]),
            'centro': a[3],
            'duracion': str(a[4]),  # Asegúrate de convertir los tipos de datos correctos, por ejemplo, numerics a string si es necesario.
            'en_modulo': a[5],
            'estado_verificacion': a[6],
            'observacion': a[7]
        } for a in alarms
    ]
    return alarms_data

def get_alerts_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT fecha, hora, centro, alerta, contador FROM alertas ORDER BY fecha DESC, hora DESC')
    alerts = cursor.fetchall()
    cursor.close()
    conn.close()
    return [
        {
            'fecha': a[0].strftime('%Y-%m-%d'), 
            'hora': a[1].strftime('%H:%M:%S'), 
            'centro': a[2], 
            'alerta': a[3], 
            'contador': a[4]
        } for a in alerts
    ]

def alarm_updater():
    with app.app_context():
        while True:
            socketio.sleep(10)  # Esperar 10 segundos
            alarms_data = get_alarms_data()
            socketio.emit('alarms_update', alarms_data)
def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )
    return conn

def get_initial_video_url():
    # Suponiendo que tienes una lista de videos o una forma de obtener el último video
    latest_video = get_latest_video()  # Asegúrate de que esta función exista y devuelva el nombre del último video
    if latest_video:
        encoded_video = quote(latest_video)
        return f"http://10.11.10.26:5123/videos/{encoded_video}"
    return None

def get_latest_image():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT imagen, fecha, hora, centro FROM imagenaquapangal3 ORDER BY fecha DESC, hora DESC LIMIT 1')
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        # Asegúrate de que la fecha y la hora estén en formato de cadena para que puedan ser JSON serializables
        fecha = row[1].strftime('%Y-%m-%d') if row[1] else None
        hora = row[2].strftime('%H:%M:%S') if row[2] else None
        return {'imagen_bytes': row[0], 'fecha': fecha, 'hora': hora, 'centro': row[3]}
    else:
        return None

def create_sftp_client(host, port, username, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=port, username=username, password=password)
    sftp = client.open_sftp()
    return sftp

def parse_video_datetime(filename):
    try:
        parts = filename.split('_')
        if len(parts) == 3:
            date_part = parts[1]
            time_part = parts[2].split('.')[0]
            return datetime.strptime(date_part + '_' + time_part, '%d-%m-%Y_%H-%M-%S')
    except ValueError:
        pass
    return None

def compare_videos(video1, video2):
    datetime1 = parse_video_datetime(video1)
    datetime2 = parse_video_datetime(video2)
    if datetime1 and datetime2:
        return (datetime1 > datetime2) - (datetime1 < datetime2)
    elif datetime1:
        return -1
    elif datetime2:
        return 1
    return 0

def get_video_urls():
    sftp = create_sftp_client(SFTP_HOST, SFTP_PORT, SFTP_USER, SFTP_PASS)
    videos = sftp.listdir('/home/videos')
    sftp.close()
    # Filtrar y ordenar los videos que siguen el formato correcto
    videos = [video for video in videos if parse_video_datetime(video)]
    videos.sort(key=cmp_to_key(compare_videos), reverse=True)
    video_urls = [f"http://10.11.10.26:5123/videos/{quote(video)}" for video in videos]
    return video_urls

    # Ordenar los videos por fecha y hora descendente
    sorted_videos = sorted(videos_with_dates, key=lambda x: x[1], reverse=True)
    
    # Solo devolver las URLs de los videos ordenados
    video_urls = [f"http://10.11.10.26:5123/videos/{video[0]}" for video in sorted_videos]
    return video_urls

def get_latest_video():
    sftp = create_sftp_client(SFTP_HOST, SFTP_PORT, SFTP_USER, SFTP_PASS)
    videos = sftp.listdir('/home/videos')
    sftp.close()
    latest_video = None
    latest_date = None
    for video in videos:
        parts = video.split('_')
        if len(parts) == 3:
            video_date = parts[1]
            video_time = parts[2].split('.')[0]
            try:
                video_datetime = datetime.strptime(video_date + '_' + video_time, '%d-%m-%Y_%H-%M-%S')
                if latest_date is None or video_datetime > latest_date:
                    latest_date = video_datetime
                    latest_video = video
            except ValueError:
                continue
    return latest_video

@app.route('/')
def index():
    video_urls = get_video_urls()
    initial_video_url = get_initial_video_url()
    return render_template('index.html', video_urls=video_urls, initial_video_url=initial_video_url)

@app.route('/get-image-list')
def get_image_list():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, fecha, hora, centro FROM imagenaquapangal3 ORDER BY fecha DESC, hora DESC')
    images = cursor.fetchall()
    cursor.close()
    conn.close()
    image_list = [
        {'id': img[0], 'fecha': img[1].strftime('%Y-%m-%d'), 'hora': img[2].strftime('%H:%M:%S'), 'centro': img[3]}
        for img in images
    ]
    return jsonify(image_list)
@app.route('/get-closest-image/<video_datetime>')
def get_closest_image(video_datetime):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Reemplaza los guiones bajos entre la fecha con guiones antes de convertir a objeto datetime
        formatted_video_datetime = video_datetime[:10].replace('_', '-') + video_datetime[10:]
        video_datetime_obj = datetime.strptime(formatted_video_datetime, '%d-%m-%Y_%H-%M-%S')

        query = """SELECT imagen, fecha, hora, centro
                   FROM imagenaquapangal3
                   WHERE (fecha, hora) <= (%s, %s)
                   ORDER BY fecha DESC, hora DESC
                   LIMIT 1"""
        cursor.execute(query, (video_datetime_obj.date(), video_datetime_obj.time()))
        row = cursor.fetchone()
        
        if row:
            imagen_base64 = base64.b64encode(row[0]).decode('utf-8')
            fecha = row[1].strftime('%Y-%m-%d') if row[1] else ''
            hora = row[2].strftime('%H:%M:%S') if row[2] else ''
            centro = row[3] if row[3] else ''
            
            image_details = {
                'imagen_base64': imagen_base64,
                'fecha': fecha,
                'hora': hora,
                'centro': centro
            }
            return jsonify(image_details)
        else:
            return jsonify({'error': 'Imagen no encontrada'}), 404

    except ValueError as e:
        app.logger.error(f'Error al convertir fecha y hora: {e}')
        return jsonify({'error': 'Formato de fecha y hora incorrecto'}), 400
    except Exception as e:
        app.logger.error(f'Error al obtener la imagen más cercana: {e}')
        return jsonify({'error': 'Error interno del servidor'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/alerts')
def alerts():
    alerts_data = get_alerts_data()
    return render_template('alerts.html', alerts=alerts_data)

@app.route('/videos/<path:filename>')
def video(filename):
    decoded_filename = unquote(filename)
    local_file_path = os.path.join('/home/estadoscam/mi_flask_env/proyecto2/videos', decoded_filename)
    if not os.path.isfile(local_file_path):
        sftp = create_sftp_client(SFTP_HOST, SFTP_PORT, SFTP_USER, SFTP_PASS)
        try:
            sftp.get(f'/home/videos/{filename}', local_file_path)
        except Exception as e:
            app.logger.error(f"Error al descargar el archivo: {e}")
            return f"Error al descargar el archivo: {e}", 500
        finally:
            sftp.close()
    return send_file(local_file_path, mimetype='video/mp4')
@app.route('/get-image-details/<int:image_id>')
def get_image_details(image_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Asegúrate de que la consulta corresponda con la estructura de tu base de datos
        cursor.execute('SELECT imagen, fecha, hora, centro FROM imagenaquapangal3 WHERE id = %s', (image_id,))
        row = cursor.fetchone()
        if row:
            # Convierte el campo binario a una cadena en base64 para enviar en JSON
            imagen_base64 = base64.b64encode(row[0]).decode('utf-8')
            fecha = row[1].strftime('%Y-%m-%d') if row[1] else ''
            hora = row[2].strftime('%H:%M:%S') if row[2] else ''
            centro = row[3] if row[3] else ''
            image_details = {
                'imagen_base64': imagen_base64,
                'fecha': fecha,
                'hora': hora,
                'centro': centro
            }
            return jsonify(image_details)
        else:
            return jsonify({'error': 'Imagen no encontrada'}), 404
    except Exception as e:
        # Es importante lograr cualquier excepción para poder depurar problemas
        app.logger.error(f'Error al obtener detalles de la imagen: {e}')
        return jsonify({'error': 'Error al obtener detalles de la imagen'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/video-list')
def video_list_api():
    video_urls = get_video_urls()
    return jsonify(video_urls)

@app.errorhandler(500)
def internal_error(error):
    app.logger.error('Server Error: %s', (error))
    return "Error interno del servidor", 500

if __name__ == '__main__':
    socketio.start_background_task(alarm_updater)
    socketio.run(app, host='10.11.10.26', port=5123)