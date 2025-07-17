"""
Tareas asíncronas con Celery
"""

import logging
import time
from datetime import datetime
from celery import Celery
from config import Config
from database import db_manager
from services import AlarmService, VozService

logger = logging.getLogger(__name__)

# Crear instancia de Celery
celery = Celery('cms_tasks')

def setup_celery(app):
    """Configurar Celery con Flask"""
    
    celery.conf.update(
        broker_url=Config.CELERY_BROKER_URL,
        result_backend=Config.CELERY_RESULT_BACKEND,
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],
        timezone='America/Santiago',
        enable_utc=True,
        task_routes={
            'tasks.update_observation_task': {'queue': 'observations'},
            'tasks.cleanup_old_data': {'queue': 'maintenance'},
        },
        beat_schedule={
            'cleanup-old-data': {
                'task': 'tasks.cleanup_old_data',
                'schedule': 3600.0,  # Cada hora
            },
        }
    )
    
    class ContextTask(celery.Task):
        """Tarea con contexto de Flask"""
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery

@celery.task(bind=True, max_retries=3)
def update_observation_task(self, alarm_id, observation, observation_timestamp, action):
    """Tarea para actualizar observación de alarma"""
    try:
        start_time = time.time()
        
        # Convertir timestamp si es string
        if isinstance(observation_timestamp, str):
            observation_timestamp = datetime.fromisoformat(observation_timestamp)
        
        # Actualizar observación
        AlarmService.update_observation(alarm_id, observation, observation_timestamp, action)
        
        end_time = time.time()
        logger.info(f"Observación actualizada para alarma {alarm_id} en {end_time - start_time:.4f}s")
        
        return {
            'status': 'success',
            'alarm_id': alarm_id,
            'processing_time': end_time - start_time
        }
        
    except Exception as e:
        logger.error(f"Error actualizando observación {alarm_id}: {e}")
        
        # Reintentar si no se ha excedido el límite
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60, exc=e)
        
        return {
            'status': 'error',
            'alarm_id': alarm_id,
            'error': str(e)
        }

@celery.task
def voz_data_updater_task():
    """Tarea para actualizar datos de voz"""
    try:
        start_time = time.time()
        
        # Obtener datos de voz
        voz_data = VozService.get_voz_data()
        
        # Aquí podrías emitir eventos de SocketIO si tienes configurado Redis
        # o usar otro mecanismo de comunicación
        
        end_time = time.time()
        logger.debug(f"Datos de voz actualizados en {end_time - start_time:.4f}s")
        
        return {
            'status': 'success',
            'records_count': len(voz_data),
            'processing_time': end_time - start_time
        }
        
    except Exception as e:
        logger.error(f"Error actualizando datos de voz: {e}")
        return {
            'status': 'error',
            'error': str(e)
        }

@celery.task
def cleanup_old_data():
    """Tarea de mantenimiento para limpiar datos antiguos"""
    try:
        start_time = time.time()
        
        # Aquí puedes implementar la lógica de limpieza
        # Por ejemplo, eliminar registros antiguos, optimizar tablas, etc.
        
        with db_manager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Ejemplo: eliminar datos de voz mayores a 30 días
                cursor.execute("""
                    DELETE FROM voz 
                    WHERE timestamp < NOW() - INTERVAL '30 days'
                """)
                deleted_voz = cursor.rowcount
                
                # Ejemplo: eliminar alertas mayores a 90 días
                cursor.execute("""
                    DELETE FROM alertas 
                    WHERE timestamp < NOW() - INTERVAL '90 days'
                """)
                deleted_alerts = cursor.rowcount
                
                conn.commit()
        
        end_time = time.time()
        logger.info(f"Limpieza completada: {deleted_voz} registros de voz, {deleted_alerts} alertas eliminadas en {end_time - start_time:.4f}s")
        
        return {
            'status': 'success',
            'deleted_voz': deleted_voz,
            'deleted_alerts': deleted_alerts,
            'processing_time': end_time - start_time
        }
        
    except Exception as e:
        logger.error(f"Error en limpieza de datos: {e}")
        return {
            'status': 'error',
            'error': str(e)
        }

@celery.task
def health_check():
    """Tarea de verificación de salud del sistema"""
    try:
        # Verificar base de datos
        db_status = db_manager.test_connection()
        
        # Verificar otras dependencias aquí
        
        return {
            'status': 'healthy',
            'database': 'ok' if db_status else 'error',
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error en health check: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }