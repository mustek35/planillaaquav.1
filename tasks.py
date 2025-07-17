import time
import ujson as json  # Usar ujson para serialización más rápida
import redis
import psycopg2
import psycopg2.pool
import pytz
from celery import Celery
from datetime import datetime

# Configuración de Celery
app = Celery('tasks', broker='redis://10.11.10.26:6379/0', backend='redis://10.11.10.26:6379/0')

# Cliente Redis
redis_client = redis.Redis(host='10.11.10.26', port=6379, db=0)

# Configuración adicional de Celery
app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='America/Santiago',
    enable_utc=True,
)

# Crear un pool de conexiones para la base de datos
db_pool = psycopg2.pool.SimpleConnectionPool(
    1, 20,  # Mínimo 1 y máximo 20 conexiones en el pool
    host='179.57.170.61',
    port='24301',
    database='Aquachile',
    user='orca',
    password='estadoscam.'
)

# Función para obtener una conexión desde el pool de conexiones
def get_db_connection_from_pool():
    try:
        return db_pool.getconn()
    except Exception as e:
        print(f"Error obteniendo conexión del pool: {e}")
        raise

# Función para devolver la conexión al pool
def release_db_connection_to_pool(conn):
    try:
        if conn:
            db_pool.putconn(conn)
    except Exception as e:
        print(f"Error devolviendo la conexión al pool: {e}")

# Tarea de Celery para actualizar la observación en la base de datos
@app.task
def update_observation_in_db(alarm_id, observation, observation_timestamp, action):
    start_time = time.time()  # Marca de tiempo inicial
    try:
        # Convertir la marca de tiempo a la zona horaria de Chile
        chile_tz = pytz.timezone('America/Santiago')
        observation_timestamp = observation_timestamp.astimezone(chile_tz)
        
        # Obtener una conexión del pool de conexiones
        db_connect_start = time.time()
        conn = get_db_connection_from_pool()
        db_connect_end = time.time()  # Marca de tiempo después de la conexión
        print(f"Conexión a la base de datos desde el pool tomó: {db_connect_end - db_connect_start:.4f} segundos")

        cursor_start = time.time()  # Marca de tiempo antes de la consulta
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE alarmas
                SET observacion = %s, observation_timestamp = %s, observacion_texto = %s, accion = %s
                WHERE id = %s
            """, (observation, observation_timestamp, observation, action, alarm_id))
            conn.commit()
            cursor_end = time.time()  # Marca de tiempo después de la consulta
            print(f"Ejecución de la consulta tomó: {cursor_end - cursor_start:.4f} segundos")
        
        # Publicar actualización en Redis
        redis_publish_start = time.time()
        redis_client.publish('observation_updates', json.dumps({
            'id': alarm_id,
            'observation': observation,
            'observation_timestamp': observation_timestamp.isoformat(),
            'action': action
        }))
        redis_publish_end = time.time()  # Marca de tiempo después de la publicación en Redis
        print(f"Publicación en Redis tomó: {redis_publish_end - redis_publish_start:.4f} segundos")

    except psycopg2.Error as e:
        print(f"Error updating observation in the database: {e}")
    finally:
        # Asegurarse de liberar la conexión al pool
        release_db_connection_to_pool(conn)
    
    # Tiempo total de ejecución de la tarea
    total_time = time.time() - start_time
    print(f"Tiempo total para update_observation_in_db: {total_time:.4f} segundos")
