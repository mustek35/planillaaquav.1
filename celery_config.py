from celery import Celery

app = Celery('tasks', broker='redis://10.11.10.26:6379/0')

app.conf.update(
    result_backend='redis://10.11.10.26:6379/0',
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='America/Santiago',
    enable_utc=True,
    broker_connection_retry_on_startup=True,  # Añadir esta línea para eliminar la advertencia
)
