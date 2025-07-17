# Sistema de Monitoreo Central (CMS)

Una aplicación web moderna para el monitoreo de alarmas y alertas en centros de cultivo acuícola.

## 🚀 Características

- **Dashboard en tiempo real** con WebSockets
- **Gestión de alarmas** con estados y observaciones
- **Sistema de autenticación** con roles de usuario
- **Procesamiento asíncrono** con Celery
- **Base de datos PostgreSQL** con pool de conexiones
- **Cache Redis** para optimización
- **API RESTful** para integración
- **Interfaz responsive** con SocketIO

## 📋 Requisitos

- Python 3.11+
- PostgreSQL 12+
- Redis 6+
- Node.js 16+ (para assets frontend)

## 🛠️ Instalación

### Método 1: Instalación manual

1. **Clonar el repositorio**

```bash
git clone <tu-repositorio>
cd cms-aquachile
```

2. **Configurar variables de entorno**

```bash
cp .env.example .env
# Editar .env con tus configuraciones
```

3. **Ejecutar script de instalación**

```bash
chmod +x run.sh
./run.sh dev
```

### Método 2: Docker (Recomendado)

```bash
# Iniciar todos los servicios
./run.sh docker

# O manualmente
docker-compose up --build
```

## ⚙️ Configuración

### Variables de entorno (.env)

```env
# Base de datos
DB_HOST=localhost
DB_PORT=5432
DB_NAME=aquachile
DB_USER=orca
DB_PASSWORD=tu_password

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Flask
SECRET_KEY=tu_clave_secreta_muy_segura
FLASK_ENV=development
FLASK_DEBUG=True

# Aplicación
APP_HOST=127.0.0.1
APP_PORT=5300
```

### Estructura de base de datos

La aplicación requiere las siguientes tablas:

- `usuarios` - Gestión de usuarios y autenticación
- `alarmas` - Registro de alarmas del sistema
- `alertas` - Alertas múltiples y notificaciones
- `voz` - Datos de detección por voz
- `aquachile_victron` - Datos de conexión Victron

## 🏃 Uso

### Desarrollo

```bash
# Modo desarrollo con auto-reload
./run.sh dev

# O directamente
python app.py
```

### Producción

```bash
# Modo producción con Celery
./run.sh prod

# Celery worker separado
celery -A tasks worker --loglevel=info

# Celery beat para tareas programadas
celery -A tasks beat --loglevel=info
```

### Tests

```bash
# Ejecutar tests
./run.sh test

# Tests específicos
python -m pytest tests/test_services.py -v
```

## 📁 Estructura del proyecto

```
cms-aquachile/
├── app.py                 # Aplicación principal
├── config.py             # Configuración
├── database.py           # Manejador de base de datos
├── models.py             # Modelos de datos
├── services.py           # Lógica de negocio
├── tasks.py              # Tareas asíncronas
├── requirements.txt      # Dependencias Python
├── docker-compose.yml    # Configuración Docker
├── Dockerfile           # Imagen Docker
├── run.sh               # Script de inicio
├── .env.example         # Ejemplo de variables de entorno
├── static/              # Archivos estáticos
│   ├── css/
│   ├── js/
│   └── icons/
├── templates/           # Templates HTML
│   ├── index.html
│   └── login.html
└── tests/              # Tests automatizados
```

## 🔧 API

### Endpoints principales

- `GET /` - Página principal (redirige según autenticación)
- `POST /login` - Autenticación de usuario
- `GET /logout` - Cerrar sesión
- `GET /alerts` - Dashboard principal
- `GET /api/alarms` - Obtener alarmas (JSON)
- `GET /api/alerts` - Obtener alertas (JSON)
- `GET /api/voz` - Obtener datos de voz (JSON)

### WebSocket Events

- `connect` - Conexión establecida
- `request_alarms_update` - Solicitar actualización de alarmas
- `update_observation` - Actualizar observación de alarma
- `alarms_update` - Datos de alarmas actualizados
- `observation_updated` - Observación actualizada

## 🎛️ Monitoreo

### Health Check

```bash
# Verificar estado de la aplicación
curl http://localhost:5300/api/health

# Verificar Celery
celery -A tasks inspect ping
```

### Logs

```bash
# Logs de la aplicación
tail -f logs/app.log

# Logs de Celery
tail -f logs/celery.log
```

## 🚀 Despliegue

### Docker Production

```yaml
# docker-compose.prod.yml
version: "3.8"
services:
  app:
    image: cms-aquachile:latest
    environment:
      - FLASK_ENV=production
    ports:
      - "80:5300"
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name tu-dominio.com;

    location / {
        proxy_pass http://127.0.0.1:5300;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /socket.io/ {
        proxy_pass http://127.0.0.1:5300;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 🧪 Testing

```bash
# Ejecutar todos los tests
pytest

# Tests con cobertura
pytest --cov=. --cov-report=html

# Tests de integración
pytest tests/integration/
```

## 🤝 Contribuir

1. Fork el proyecto
2. Crear rama feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Agregar nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Crear Pull Request

## 📝 Licencia

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para detalles.

## 📞 Soporte

- Email: soporte@orcatecnologia.cl
- Documentación: [docs/](docs/)
- Issues: [GitHub Issues](https://github.com/tu-repo/issues)

## 🔄 Changelog

### v2.0.0 (2024-07-17)

- ✨ Refactorización completa de la arquitectura
- 🔧 Configuración con variables de entorno
- 🐳 Soporte para Docker
- 📊 Mejoras en el dashboard
- 🔒 Seguridad mejorada
- 🧪 Tests automatizados
