from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from flask_login import UserMixin

Base = declarative_base()

class User(UserMixin, Base):
    """Modelo de usuario"""
    __tablename__ = 'usuarios'
    
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)
    correo = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    perfil = Column(String(50), nullable=False)
    empresa = Column(String(50), nullable=False)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    
    def __repr__(self):
        return f'<User {self.correo}>'

class Alarma(Base):
    """Modelo de alarma"""
    __tablename__ = 'alarmas'
    
    id = Column(Integer, primary_key=True)
    centro = Column(String(100), nullable=False)
    duracion = Column(Float, nullable=False)
    en_modulo = Column(Boolean, default=False)
    estado_verificacion = Column(String(50), nullable=False)
    observacion = Column(Text)
    timestamp = Column(DateTime, nullable=False)
    observation_timestamp = Column(DateTime)
    observacion_texto = Column(Text)
    accion = Column(String(50))
    gestionado_time = Column(DateTime)
    gestionado_dentro_de_tiempo = Column(Boolean)
    imagen = Column(Text)  # Base64 de la imagen
    
    def __repr__(self):
        return f'<Alarma {self.id} - {self.centro}>'
    
    @property
    def gestionado(self):
        """Propiedad que indica si la alarma está gestionada"""
        return bool(self.observacion and self.observacion.strip())

class Alerta(Base):
    """Modelo de alerta"""
    __tablename__ = 'alertas'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    centro = Column(String(100), nullable=False)
    alerta = Column(String(200), nullable=False)
    contador = Column(Integer, default=1)
    
    def __repr__(self):
        return f'<Alerta {self.id} - {self.centro}>'

class Voz(Base):
    """Modelo de datos de voz"""
    __tablename__ = 'voz'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    centro = Column(String(100), nullable=False)
    zonadealarma = Column(String(100), nullable=False)
    imagen = Column(Text)  # Base64 de la imagen
    
    def __repr__(self):
        return f'<Voz {self.id} - {self.centro}>'

class Victron(Base):
    """Modelo de datos Victron"""
    __tablename__ = 'aquachile_victron'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    centro = Column(String(100), nullable=False)
    porcentaje = Column(Float)
    enlace = Column(String(100), nullable=False)
    
    def __repr__(self):
        return f'<Victron {self.id} - {self.centro}>'