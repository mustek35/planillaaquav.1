import time
import logging
import psycopg2
import psycopg2.pool
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from config import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manejador de conexiones a la base de datos"""
    
    def __init__(self):
        self.config = Config()
        self._pool = None
        self._engine = None
        self._session_factory = None
        self.initialize()
    
    def initialize(self):
        """Inicializar conexiones de base de datos"""
        try:
            # Pool de conexiones psycopg2
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=self.config.DB_POOL_SIZE,
                host=self.config.DB_HOST,
                port=self.config.DB_PORT,
                database=self.config.DB_NAME,
                user=self.config.DB_USER,
                password=self.config.DB_PASSWORD
            )
            
            # SQLAlchemy engine
            self._engine = create_engine(
                self.config.DATABASE_URL,
                pool_size=self.config.DB_POOL_SIZE,
                max_overflow=self.config.DB_POOL_MAX_OVERFLOW,
                pool_timeout=self.config.DB_POOL_TIMEOUT,
                pool_pre_ping=True,
                echo=self.config.DEBUG
            )
            
            # Session factory para SQLAlchemy
            self._session_factory = scoped_session(
                sessionmaker(bind=self._engine)
            )
            
            logger.info("Base de datos inicializada correctamente")
            
        except Exception as e:
            logger.error(f"Error inicializando base de datos: {e}")
            raise
    
    @contextmanager
    def get_connection(self, retries=3, delay=1):
        """Context manager para obtener conexión del pool"""
        conn = None
        attempt = 0
        
        while attempt < retries:
            try:
                conn = self._pool.getconn()
                yield conn
                break
            except Exception as e:
                attempt += 1
                logger.warning(f"Intento {attempt} de conexión falló: {e}")
                if conn:
                    try:
                        self._pool.putconn(conn, close=True)
                    except:
                        pass
                if attempt < retries:
                    time.sleep(delay)
                else:
                    raise
            finally:
                if conn:
                    try:
                        self._pool.putconn(conn)
                    except Exception as e:
                        logger.error(f"Error devolviendo conexión al pool: {e}")
    
    def get_session(self):
        """Obtener sesión de SQLAlchemy"""
        return self._session_factory()
    
    def close_session(self):
        """Cerrar sesión de SQLAlchemy"""
        self._session_factory.remove()
    
    def test_connection(self):
        """Probar conexión a la base de datos"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    logger.info("Conexión a base de datos exitosa")
                    return result[0] == 1
        except Exception as e:
            logger.error(f"Error probando conexión: {e}")
            return False
    
    def close_all(self):
        """Cerrar todas las conexiones"""
        try:
            if self._pool:
                self._pool.closeall()
            if self._session_factory:
                self._session_factory.remove()
            logger.info("Todas las conexiones cerradas")
        except Exception as e:
            logger.error(f"Error cerrando conexiones: {e}")

# Instancia global del manejador de base de datos
db_manager = DatabaseManager()