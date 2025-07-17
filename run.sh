#!/bin/bash

# Script de inicio para la aplicación CMS

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Iniciando Sistema de Monitoreo Central (CMS)${NC}"

# Verificar si existe .env
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  Archivo .env no encontrado, creando desde .env.example${NC}"
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${YELLOW}📝 Por favor, edita el archivo .env con tus configuraciones${NC}"
    else
        echo -e "${RED}❌ Archivo .env.example no encontrado${NC}"
        exit 1
    fi
fi

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 no está instalado${NC}"
    exit 1
fi

# Verificar pip
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}❌ pip3 no está instalado${NC}"
    exit 1
fi

# Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}📦 Creando entorno virtual...${NC}"
    python3 -m venv venv
fi

# Activar entorno virtual
echo -e "${YELLOW}🔄 Activando entorno virtual...${NC}"
source venv/bin/activate

# Instalar dependencias
echo -e "${YELLOW}📚 Instalando dependencias...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

# Verificar conexión a base de datos
echo -e "${YELLOW}🔍 Verificando conexión a base de datos...${NC}"
python3 -c "
from config import Config
from database import db_manager
try:
    Config.validate_config()
    if db_manager.test_connection():
        print('✅ Conexión a base de datos exitosa')
    else:
        print('❌ Error conectando a base de datos')
        exit(1)
except Exception as e:
    print(f'❌ Error: {e}')
    exit(1)
"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Error en la verificación de base de datos${NC}"
    exit 1
fi

# Función para manejar señales
cleanup() {
    echo -e "\n${YELLOW}🛑 Deteniendo servicios...${NC}"
    if [ ! -z "$CELERY_PID" ]; then
        kill $CELERY_PID 2>/dev/null || true
    fi
    if [ ! -z "$APP_PID" ]; then
        kill $APP_PID 2>/dev/null || true
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

# Modo de ejecución
MODE=${1:-"dev"}

case $MODE in
    "dev")
        echo -e "${GREEN}🔧 Iniciando en modo desarrollo...${NC}"
        python3 app.py
        ;;
    "prod")
        echo -e "${GREEN}🏭 Iniciando en modo producción...${NC}"
        
        # Iniciar Celery worker en background
        echo -e "${YELLOW}🏃 Iniciando Celery worker...${NC}"
        celery -A tasks worker --loglevel=info --detach
        CELERY_PID=$!
        
        # Iniciar aplicación principal
        echo -e "${YELLOW}🌐 Iniciando aplicación Flask...${NC}"
        python3 app.py &
        APP_PID=$!
        
        # Esperar a que terminen los procesos
        wait $APP_PID
        ;;
    "docker")
        echo -e "${GREEN}🐳 Iniciando con Docker...${NC}"
        docker-compose up --build
        ;;
    "test")
        echo -e "${GREEN}🧪 Ejecutando tests...${NC}"
        python3 -m pytest tests/ -v
        ;;
    *)
        echo -e "${RED}❌ Modo no válido: $MODE${NC}"
        echo -e "Modos disponibles: dev, prod, docker, test"
        exit 1
        ;;
esac