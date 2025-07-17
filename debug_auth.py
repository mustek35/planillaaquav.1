import logging
import pytz
from datetime import datetime, timedelta
from database import db_manager

logger = logging.getLogger(__name__)

class UserService:
    """Servicio para manejar usuarios - CORREGIDO para tabla sin columna 'activo'"""
    
    @staticmethod
    def authenticate_user(correo, password):
        """Autenticar usuario"""
        logger.info(f"Intentando autenticar usuario: {correo}")
        
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Query SIN columna 'activo' (que no existe en tu tabla)
                    cursor.execute("""
                        SELECT id, nombre, correo, password, perfil, empresa
                        FROM usuarios 
                        WHERE correo = %s AND password = %s
                    """, (correo, password))
                    
                    user_data = cursor.fetchone()
                    
                    if user_data:
                        # Crear objeto User simple
                        class SimpleUser:
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
                        
                        user = SimpleUser(user_data)
                        logger.info(f"Usuario autenticado exitosamente: {correo}")
                        return user
                    else:
                        logger.warning(f"Credenciales incorrectas para: {correo}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error autenticando usuario {correo}: {e}")
            return None
    
    @staticmethod
    def get_user_by_id(user_id):
        """Obtener usuario por ID"""
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, nombre, correo, password, perfil, empresa
                        FROM usuarios 
                        WHERE id = %s
                    """, (user_id,))
                    
                    user_data = cursor.fetchone()
                    
                    if user_data:
                        # Crear objeto User simple
                        class SimpleUser:
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
                        
                        return SimpleUser(user_data)
                    else:
                        return None
                        
        except Exception as e:
            logger.error(f"Error obteniendo usuario {user_id}: {e}")
            return None

class AlarmService:
    """Servicio para manejar alarmas"""
    
    @staticmethod
    def get_alarms_data(start_time=None, end_time=None):
        """Obtener datos de alarmas"""
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
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
                    
                    alarms_data = []
                    for alarm in alarms:
                        alarms_data.append({
                            'id': alarm[0],
                            'fecha': alarm[6].strftime('%Y-%m-%d'),
                            'hora': alarm[6].strftime('%H:%M:%S'),
                            'centro': alarm[1],
                            'duracion': AlarmService._format_duration(alarm[2]),
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
    
    @staticmethod
    def _format_duration(seconds):
        """Formatear duración en formato legible"""
        if not seconds:
            return "0 segundos"
        
        minutes, seconds = divmod(round(seconds), 60)
        if minutes > 0:
            return f"{minutes} minuto{'s' if minutes != 1 else ''} {seconds} segundo{'s' if seconds != 1 else ''}"
        else:
            return f"{seconds} segundo{'s' if seconds != 1 else ''}"
    
    @staticmethod
    def update_observation(alarm_id, observation, observation_timestamp, action):
        """Actualizar observación de alarma"""
        try:
            chile_tz = pytz.timezone('America/Santiago')
            if observation_timestamp.tzinfo is None:
                observation_timestamp = chile_tz.localize(observation_timestamp)
            else:
                observation_timestamp = observation_timestamp.astimezone(chile_tz)

            with db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE alarmas
                        SET observacion = %s
                        WHERE id = %s
                    """, (observation, alarm_id))
                    
                    conn.commit()
                    logger.info(f"Observación actualizada para alarma {alarm_id}")
                    
        except Exception as e:
            logger.error(f"Error actualizando observación: {e}")
            raise

class AlertService:
    """Servicio para manejar alertas"""
    
    @staticmethod
    def get_alerts_data(start_time=None, end_time=None):
        """Obtener datos de alertas"""
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
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
                    
                    return [{
                        'timestamp': alert[0].strftime('%Y-%m-%d %H:%M:%S'),
                        'centro': alert[1],
                        'alerta': alert[2],
                        'contador': alert[3],
                    } for alert in alerts]
                    
        except Exception as e:
            logger.error(f"Error obteniendo datos de alertas: {e}")
            raise

class VozService:
    """Servicio para manejar datos de voz"""
    
    @staticmethod
    def get_voz_data():
        """Obtener datos de voz recientes"""
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    timezone = pytz.timezone('America/Santiago')
                    now = datetime.now(timezone)
                    
                    # Definir intervalos de tiempo
                    start_of_day = now.replace(hour=7, minute=30, second=0, microsecond=0)
                    end_of_day = now.replace(hour=18, minute=30, second=0, microsecond=0)

                    if start_of_day.time() <= now.time() < end_of_day.time():
                        time_interval = now - timedelta(minutes=1)
                    else:
                        time_interval = now - timedelta(minutes=5)

                    cursor.execute("""
                        SELECT timestamp, centro, zonadealarma, imagen
                        FROM voz 
                        WHERE timestamp BETWEEN %s AND %s 
                        ORDER BY timestamp DESC
                    """, (time_interval, now))
                    
                    records = cursor.fetchall()
                    
                    return [{
                        'timestamp': record[0].strftime('%Y-%m-%d %H:%M:%S'),
                        'centro': record[1],
                        'zonadealarma': record[2],
                        'imagen': record[3] or ''
                    } for record in records]
                    
        except Exception as e:
            logger.error(f"Error obteniendo datos de voz: {e}")
            raise