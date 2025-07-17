let socket;
let isSoundOn = true;
let isMultiSelectMode = false;
let alarmsData = [];  // Asegúrate de que está definido como array globalmente
const alertQueue = [];
let isSpeaking = false;
let currentSearchTerm = '';
let currentFilter = 'online'; // El filtro predeterminado
const selectedAlarmIds = new Set(); // Almacena los IDs de las filas seleccionadas
const localObservations = {}; // Almacena las observaciones locales que aún no se han confirmado
let isEditing = false;
let autoHideTimeout;
let lastAnnouncedTimestamp = 0;
let imageFetchTimeout;
let worker;

document.addEventListener('DOMContentLoaded', function() {
    initializeSocket();
    initializeWorker();
    initializeDOMElements();
    attachEventListeners();
    setupAlertTableClickHandlers();
    setupCheckboxHandlers();
    updateClockAndCountdown();
});
    // Inicializar socket cuando el DOM esté completamente cargado
    socket = io(`http://${document.domain}:${location.port}`);

    // Configuración inicial de elementos del DOM
    const overlay = document.querySelector('.overlay');
    const modal = document.querySelector('.modal');
    const saveBtn = document.getElementById('saveObservation');

document.getElementById('logo').addEventListener('click', function() {
        location.reload();
    });

    function initializeSocket() {
       
        socket.on('connect', function() {
            console.log("Conectado al servidor de WebSocket");
        });
        
        socket.on('alarms_update', function(data) {
            console.log("Datos recibidos:", data);
            if (Array.isArray(data) && data.length > 0) {
                alarmsData = data;
                applyFilterAndUpdateTable();  // Actualizar la tabla con los datos
            } else {
                console.warn("No se recibieron datos válidos o el array está vacío.");
            }
        });
        
        socket.on('disconnect', function() {
            console.log("Desconectado del servidor de WebSocket");
        });
    
        socket.on('alerts_data_update', updateAlertsTable);
        socket.on('update_data', function(data) {
            console.log("Datos recibidos para actualización:", data);
            if (Array.isArray(data)) {
                updateBarChart(data);
            }
        });
       
        socket.on('voz_data_update', function(data) {
            console.log("Datos de voz recibidos:", data);
            handleVozDataUpdate(data);
        });
    }

        
function initializeWorker() {
    if (typeof Worker !== 'undefined') {
        // Verificamos si ya existe un worker para evitar crear múltiples instancias
        if (worker) {
            console.warn("El Worker ya está inicializado.");
            return;
        }

        worker = new Worker('/static/js/speechWorker.js');
        console.log("Worker inicializado:", worker);

        worker.onmessage = function(e) {
            if (e.data === 'end') {
                isSpeaking = false;
                processAlertQueue(); // Procesa la siguiente alerta en la cola
            }
        };

        worker.onerror = function(e) {
            console.error("Error en el Worker:", e.message, "en", e.filename, "línea", e.lineno);
        };

    } else {
        console.error('Web Worker no es soportado en este navegador.');
    }
}
// Función para terminar el worker y liberar recursos
function terminateWorker() {
    if (worker) {
        worker.terminate();
        console.log("Worker terminado.");
        worker = undefined;
    } else {
        console.warn("No hay Worker activo para terminar.");
    }
}
function initializeDOMElements() {
    const savedSoundState = localStorage.getItem('isSoundOn');
    isSoundOn = savedSoundState !== null ? savedSoundState === 'true' : true;
    localStorage.setItem('isSoundOn', isSoundOn.toString());

    updateSoundButton(); // Actualizar el botón basado en el estado actual
}

function attachEventListeners() {
    document.getElementById('logo').addEventListener('click', function() {
        location.reload();
    });

    document.getElementById('soundToggle').addEventListener('click', toggleSound);
}

function toggleSound() {
    isSoundOn = !isSoundOn;
    localStorage.setItem('isSoundOn', isSoundOn.toString());
    updateSoundButton();
}

function speak(message, callback) {
    if ('speechSynthesis' in window && isSoundOn) {
        isSpeaking = true;

        const utterance = new SpeechSynthesisUtterance(message);
        const voices = window.speechSynthesis.getVoices();
        const selectedVoice = voices.find(voice => voice.lang === 'es-MX');

        if (selectedVoice) {
            utterance.voice = selectedVoice;
        } else {
            console.error('Voz seleccionada no encontrada.');
        }

        utterance.pitch = 1.4;
        utterance.rate = 1.4;

        utterance.onend = function() {
            isSpeaking = false;
            if (callback) callback();
            processAlertQueue();  // Procesa la siguiente alerta en la cola
        };

        window.speechSynthesis.speak(utterance);
    } else {
        console.error('speechSynthesis no es soportado o sonido desactivado.');
        isSpeaking = false;
        processAlertQueue();  // Continúa con la siguiente alerta si el sonido está desactivado o no es soportado
    }
}

function handleVozDataUpdate(data) {
    console.log("Procesando datos de voz:", data);
    const tbody = document.getElementById('second-table').getElementsByTagName('tbody')[0];
    tbody.innerHTML = '';  // Limpia la tabla antes de insertar nuevos datos
    let latestTimestamp = 0;
    let latestData = null;

    data.forEach(function(item) {
        const row = tbody.insertRow();
        const timestampCell = row.insertCell(0);
        const centroCell = row.insertCell(1);
        const zonaDeAlarmaCell = row.insertCell(2);

        const timeOnly = new Date(item.timestamp).toLocaleTimeString('en-GB', { hour12: false });
        timestampCell.textContent = timeOnly;
        centroCell.textContent = item.centro;
        zonaDeAlarmaCell.textContent = item.zonadealarma;

        const timestampValue = new Date(item.timestamp).valueOf();
        if (timestampValue > latestTimestamp) {
            latestTimestamp = timestampValue;
            latestData = item;
        }
    });

    // Verifica si debe anunciarse una nueva alerta
    if (latestTimestamp > lastAnnouncedTimestamp) {
        lastAnnouncedTimestamp = latestTimestamp;

        const zonasCriticas = ["Embarcación", "Area", "Módulo", "Zona Crítica", "Persona detectada en el area de Combustible"];
        if (latestData && zonasCriticas.includes(latestData.zonadealarma)) {
            const message = `${latestData.zonadealarma} ${latestData.centro}`;
            alertQueue.push({ message });
            processAlertQueue();  // Inicia el procesamiento de la cola
        }
    }
}

function processAlertQueue() {
    if (!isSpeaking && alertQueue.length > 0) {
        const alert = alertQueue.shift();  // Obtener la siguiente alerta en la cola
        speak(alert.message);
    }
}



// Event listener to close the popup when the close button is clicked
document.querySelector('.close').addEventListener('click', function() {
    document.getElementById('image-popup').style.display = 'none';
});

function applyFilterAndUpdateTable() {
    const filteredData = alarmsData.filter(alarm => {
        return matchesSearchTerm(alarm, currentSearchTerm) && matchesFilter(alarm, currentFilter);
    });

    updateAlarmsTable(filteredData);  // Actualiza la tabla

    // Verifica si es necesario actualizar el gráfico
    if (typeof prepareBarChartData === 'function') {
        const barChartData = prepareBarChartData(filteredData);
        updateBarChart(barChartData);  // Actualiza el gráfico de barras
    }
}


    // Actualizar el estado del `<select>` solo si es diferente al filtro actual
    const moduleStatusSelect = document.getElementById('moduleStatus');
    if (moduleStatusSelect && moduleStatusSelect.value !== currentFilter) {
        moduleStatusSelect.value = currentFilter;
    }

// Función para abrir el popup
function openPopup() {
    const popup = document.getElementById('alarms-popup');
    popup.style.display = 'block';
}

// Función para cerrar el popup
function closePopup() {
    const popup = document.getElementById('alarms-popup');
    popup.style.display = 'none';
}

// Función para obtener los intervalos de tiempo según la selección
function getTimeRange() {
    const timeRange = document.getElementById('timeRange').value || 'night'; // Valor por defecto 'night'
    let startTime, endTime;

    if (timeRange === 'night') {
        startTime = '00:00:00';
        endTime = '07:30:00';
    } else if (timeRange === 'day') {
        startTime = '07:30:00';
        endTime = '23:59:59';
    } else if (timeRange === 'fullDay') {
        startTime = '00:00:00';
        endTime = '23:59:59';
    } else {
        // Si hay valores personalizados de inicio y fin
        startTime = document.getElementById('startTime').value || '00:00:00';
        endTime = document.getElementById('endTime').value || '23:59:59';
    }

    return { startTime, endTime };
}

// Función para cargar los datos de alarmas
function loadAlarmsData() {
    const selectedDate = document.getElementById('datePicker').value;
    const { startTime, endTime } = getTimeRange();

    fetch('/get_alarms_data_for_calendar', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            start_date: selectedDate,
            end_date: selectedDate,
            start_time: startTime,
            end_time: endTime
        })
    })
    .then(response => {
        console.log('Respuesta del servidor:', response);  // Verifica la respuesta del servidor
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        console.log('Datos recibidos:', data);  // Verifica los datos recibidos
        const tbody = document.querySelector('#popup-alarms-table tbody');
        tbody.innerHTML = '';
        if (data && data.length > 0) {
            data.forEach(alarm => {
                const row = document.createElement('tr');
                const formattedDuration = formatDuration(alarm.duracion);
                row.innerHTML = `
                    <td>${alarm.fecha || ''}</td>
                    <td>${alarm.hora || ''}</td>
                    <td>${alarm.centro || ''}</td>
                    <td>${formattedDuration}</td>
                    <td>${alarm.en_modulo ? 'En Módulo' : 'Fuera del Módulo'}</td>
                    <td>${alarm.estado_verificacion || ''}
                        ${alarm.estado_verificacion === 'Persona detectada' ? `<i class="fas fa-image fa-lg icon-spacing icon-image" data-alarm-id="${alarm.id}"></i>` : ''}
                    </td>
                    <td>${alarm.observacion || ''}</td>
                `;
                tbody.appendChild(row);
    
                // Añade el evento para descargar la imagen al hacer clic en el icono
                if (alarm.estado_verificacion === 'Persona detectada') {
                    const imageIcon = row.querySelector('.icon-image');
                    imageIcon.addEventListener('click', function() {
                        var alarmId = this.getAttribute('data-alarm-id');
                        downloadImage(alarmId);
                    });
                }
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="7">No se encontraron alarmas para esta fecha.</td></tr>';
        }
    })
    .catch(error => {
        console.error('Error fetching data:', error);
        const tbody = document.querySelector('#popup-alarms-table tbody');
        tbody.innerHTML = `<tr><td colspan="7">Error al cargar datos: ${error.message}</td></tr>`;
    });
    
}

// Añadir el manejador de eventos para el datePicker una vez que el DOM esté completamente cargado
document.getElementById('datePicker').addEventListener('change', function() {
    openPopup();
    loadAlarmsData();
});

// Asignar el manejador de eventos para el botón de filtrar
document.getElementById('filterButton').addEventListener('click', loadAlarmsData);

// Asignar el manejador de eventos para cerrar el popup
document.querySelector('#alarms-popup button').addEventListener('click', closePopup);

// Asignar los manejadores de eventos para los inputs
document.getElementById('searchCenter').addEventListener('input', filterTableByTimeAndStatus);
document.getElementById('startTime').addEventListener('input', filterTableByTimeAndStatus);
document.getElementById('endTime').addEventListener('input', filterTableByTimeAndStatus);
document.getElementById('filterStatus').addEventListener('change', filterTableByTimeAndStatus);
document.getElementById('timeRange').addEventListener('change', filterTableByTimeAndStatus);
document.getElementById('filterButton').addEventListener('click', filterTableByTimeAndStatus);

// Función para formatear la duración
function formatDuration(duration) {
    const totalSeconds = Math.floor(duration);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes > 0 ? `${minutes} min ` : ''}${seconds} seg`;
}

// Función para descargar la imagen
function downloadImage(alarmId) {
    fetch(`/fetch_image?alarm_id=${alarmId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(image => {
            if (image.error) {
                console.error(image.error);
                return;
            }

            console.log('Descargando imagen (base64):', image.image);

            var link = document.createElement('a');
            link.href = 'data:image/jpeg;base64,' + image.image; // Usa la imagen obtenida
            link.download = `image_${alarmId}.jpg`;
            link.click();
        })
        .catch(error => console.error('Error al descargar la imagen:', error));
}



// Función para filtrar la tabla por tiempo, estado y centro
function filterTableByTimeAndStatus() {
    const startTime = document.getElementById('startTime').value;
    const endTime = document.getElementById('endTime').value;
    const filterStatus = document.getElementById('filterStatus').value;
    const searchCenter = document.getElementById('searchCenter').value.toLowerCase();

    const table = document.getElementById('popup-alarms-table').getElementsByTagName('tbody')[0];
    const rows = Array.from(table.getElementsByTagName('tr'));

    // Filtrar y mostrar filas
    rows.forEach(row => {
        const timeCell = row.getElementsByTagName('td')[1].innerText;
        const centerCell = row.getElementsByTagName('td')[2].innerText.toLowerCase();
        const time = timeCell.split(' ')[1]; // Cambiado para tomar solo la hora

        const alarm = {
            duracion: row.getElementsByTagName('td')[3].innerText,
            estado_verificacion: row.getElementsByTagName('td')[5].innerText,
            en_modulo: row.getElementsByTagName('td')[4].innerText.includes('En Módulo') ? 'En Módulo' : 'Fuera del Módulo',
            gestionado: row.getElementsByTagName('td')[6].innerText !== '',
        };

        const matchesTime = (!startTime && !endTime) || (time >= startTime && time <= endTime);
        const matchesStatus = matchesFilter(alarm, filterStatus);
        const matchesCenter = centerCell.includes(searchCenter);

        if (matchesTime && matchesStatus && matchesCenter) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}




// Función para determinar si una alarma coincide con el filtro
function matchesFilter(alarm, filter) {
    switch (filter) {
        case 'online':
            return true;  // muestra todos los datos
        case 'Duración':
            const duracion = Number(alarm.duracion);  // asegúrate de que 'duracion' se recibe como número
            return duracion > 7;
        case 'Falso-Positivo':
            return alarm.estado_verificacion !== 'Falso-Positivo';
        case 'Fuera del Módulo':
            return alarm.en_modulo === 'Fuera del Módulo';
        case 'Dentro del Módulo':
            return alarm.en_modulo === 'Detección en Modulo';
        case 'Zona Crítica':
            return alarm.estado_verificacion === 'Zona Crítica';
        case 'Embarcación':
            return alarm.estado_verificacion === 'Embarcación';
        case 'No Gestionado':
            return !alarm.gestionado;  // Filtra alarmas que no están gestionadas
        case 'Gestionado':  // Nuevo filtro añadido
            return alarm.gestionado;  // Filtra alarmas que están gestionadas
        case 'ticket':
            // Esta opción no debería filtrar, será manejada por redirección
            return false;
        default:
            return true;  // Si el filtro no es reconocido, muestra todas las alarmas
    }
}



// Este manejador de eventos escucha datos específicos del rango de alarmas.
socket.on('alarms_data_in_range', function(data) {
    // Imprime en consola los datos recibidos para depuración.
    console.log('Datos recibidos para el gráfico de detecciones:', data);

    // Llama a la función global `updateBarChart` pasando los datos recibidos.
    // Asegúrate de que los datos están en el formato correcto para ser procesados por `updateBarChart`.
    window.updateBarChart(data);  // Usar la misma función si es apropiado y si los datos están correctamente formateados.
});
socket.on('login_success', function(data) {
    // Mensaje de bienvenida
    speak(data.message);
});

socket.on('connect', function() {
    console.log('Connected to the server');
    // Solicitudes de datos iniciales al servidor
    socket.emit('request_alarms_update');
    socket.emit('request_alerts_update');
    socket.emit('request_initial_data');
});

socket.on('data_update', function(data) {
    updateAlertsTable(data.alerts, data.victron);
});
socket.on('victron_data_update', function(victron) {
    if (victron.enlace === 'sin conexion') {
        handleDisconnection(victron, document.getElementById('alerts-table').getElementsByTagName('tbody')[0]);
    } else if (victron.enlace === 'conectado a internet') {
        handleReconnection(victron, document.getElementById('alerts-table').getElementsByTagName('tbody')[0]);
    }
});
function updateAlertsTable(alerts, victron) {
    const tbody = document.getElementById('alerts-table').getElementsByTagName('tbody')[0];

    // Limpiar la tabla antes de actualizar
    tbody.innerHTML = '';

    // Verificar que alerts sea un array antes de iterar sobre él
    if (Array.isArray(alerts)) {
        // Agregar todas las alertas a la tabla
        alerts.forEach(alert => {
            let row = document.createElement('tr');
            row.setAttribute('data-alert-id', alert.alerta_id);

            row.innerHTML = `
                <td class="date">${new Date(alert.timestamp).toLocaleDateString('es-CL').replace(/\//g, '-')}</td>
                <td class="time">${new Date(alert.timestamp).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</td>
                <td>${alert.centro}</td>
                <td>${getAlertWithIconHTML(alert.alerta)}</td>
                <td>${alert.contador}</td>
            `;

            tbody.appendChild(row);
        });
    } else {
        console.error('alerts no es un array:', alerts);
    }

    // Manejar la información de victron
    if (victron) {
        if (victron.enlace && victron.enlace.startsWith('sin conexion')) {
            handleDisconnection(victron, tbody);
        } else if (victron.enlace === 'conectado a internet') {
            handleReconnection(victron, tbody);
        }
    }

    // Actualizar la tabla con las desconexiones almacenadas en connectionStates
    updateDisconnectionRows(tbody);
}

function handleDisconnection(victron, tbody) {
    let existingRow = tbody.querySelector(`tr[data-center-id="${victron.centro}"]`);
    if (!existingRow) {
        let row = document.createElement('tr');
        row.setAttribute('data-center-id', victron.centro);
        row.classList.add('disconnected');

        row.innerHTML = `
            <td class="date">${victron.timestamp.split(' ')[0]}</td>
            <td class="time">${victron.timestamp.split(' ')[1]}</td>
            <td>${victron.centro}</td>
            <td class="link">sin conexion <span class="link-icon"><i class="fas fa-wifi"></i></span></td>
            <td class="total">${victron.disconnection_time}</td>
        `;

        // Prepend la fila al principio de la tabla
        tbody.prepend(row);

        // Registrar el estado de desconexión
        connectionStates[victron.centro] = { status: 'disconnected', disconnectedAt: new Date(victron.timestamp).getTime() };
    }
}

function handleReconnection(victron, tbody) {
    let existingRow = tbody.querySelector(`tr[data-center-id="${victron.centro}"]`);
    if (existingRow) {
        existingRow.remove();
        delete connectionStates[victron.centro];
    }
}

var connectionStates = {};

// Función para actualizar las filas de desconexión
function updateDisconnectionRows(tbody) {
    Object.keys(connectionStates).forEach(centro => {
        if (connectionStates[centro].status === 'disconnected') {
            let existingRow = tbody.querySelector(`tr[data-center-id="${centro}"]`);
            if (!existingRow) {
                const victronState = connectionStates[centro];
                let row = document.createElement('tr');
                row.setAttribute('data-center-id', centro);
                row.classList.add('disconnected');

                row.innerHTML = `
                    <td class="date">${victronState.disconnectedAt ? new Date(victronState.disconnectedAt).toLocaleDateString('es-CL').replace(/\//g, '-') : ''}</td>
                    <td class="time">${victronState.disconnectedAt ? new Date(victronState.disconnectedAt).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}</td>
                    <td>${centro}</td>
                    <td class="link">sin conexion <span class="link-icon"><i class="fas fa-wifi"></i></span></td>
                    <td class="total">${calculateDisconnectionTime(victronState.disconnectedAt)}</td>
                `;

                tbody.prepend(row);
            }
        } else if (connectionStates[centro].status === 'connected') {
            let existingRow = tbody.querySelector(`tr[data-center-id="${centro}"]`);
            if (existingRow) {
                existingRow.remove();
                delete connectionStates[centro];
            }
        }
    });
}

function calculateDisconnectionTime(disconnectedAt) {
    if (!disconnectedAt) return '';
    const now = new Date().getTime();
    const duration = now - disconnectedAt;
    const minutes = Math.floor(duration / 60000); // Corrección: calcular en minutos correctamente
    const seconds = ((duration % 60000) / 1000).toFixed(0);
    return `${minutes}m ${seconds}s`;
}

function getAlertWithIconHTML(alerta) {
    // Implementa la lógica para generar HTML de la alerta con icono
    return alerta;
}

// Función para actualizar la tabla con datos combinados
function updateAllData() {
    fetch('/get_all_data')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok ' + response.statusText);
            }
            return response.json();
        })
        .then(data => {
            const alerts = data.alerts;
            const victron = data.victron;

            // Actualizar la tabla con datos combinados
            updateAlertsTable(alerts, victron);
        })
        .catch(error => {
            console.error('Error fetching all data:', error);
        });
}

// Llamar a la función para actualizar todos los datos cada cierto intervalo
setInterval(updateAllData, 10000); // Actualiza cada 10 segundos

// Llamar a la función una vez para la actualización inicial
updateAllData();

function getAlertWithIconHTML(alertType) {
    let iconHtml = '';
    switch (alertType) {
        case 'Alerta Crítica':
            iconHtml = '<i class="fas fa-exclamation-triangle fa-lg icon-zona-critica"></i> ';
            break;
        case 'Clima Adverso':
            iconHtml = '<i class="fas fa-wind fa-lg icon-clima-adverso"></i> <i class="fas fa-cloud-rain fa-lg icon-clima-adverso"></i> ';
            break;
        case 'Múltiples alertas: Área':
            iconHtml = '<i class="fas fa-exclamation-circle fa-lg icon-area-multiple"></i> ';
            break;
        case 'Múltiples alertas: Módulo':
            iconHtml = '<i class="fas fa-exclamation-circle fa-lg icon-modulo-multiple"></i> ';
            break;
        default:
            iconHtml = '<i class="fas fa-info-circle fa-lg"></i> ';
            break;
    }
    return `${iconHtml}${alertType}`;
}



socket.on('victron_data_update', function(data) {
    if (data.enlace === 'sin conexion') {
        speak(`Alerta, sin conexión de internet en centro ${data.centro}`);
    } else if (data.enlace === 'conectado a internet') {
        speak(`Se ha vuelto a conectar a internet en centro ${data.centro}`);
    }
});



// Función para actualizar el botón de sonido
function updateSoundButton() {
    const soundToggleButton = document.getElementById('soundToggle');
    if (isSoundOn) {
        soundToggleButton.classList.remove('sound-toggle-off');
        soundToggleButton.classList.add('sound-toggle-on');
        soundToggleButton.innerHTML = '<i class="fas fa-volume-up"></i>';
    } else {
        soundToggleButton.classList.remove('sound-toggle-on');
        soundToggleButton.classList.add('sound-toggle-off');
        soundToggleButton.innerHTML = '<i class="fas fa-volume-mute"></i>';
    }
}




// FILTRADO
document.getElementById('centerSearch').addEventListener('input', function() {
    currentSearchTerm = this.value.toLowerCase();
    applyFilterAndUpdateTable();
});
document.getElementById('moduleStatus').addEventListener('change', function() {
    if (this.value === 'ticket') {
        window.open('https://cc210b891aa7.sn.mynetname.net/home', '_blank');
    } else {
        currentFilter = this.value;
        applyFilterAndUpdateTable();
    }
});



function prepareBarChartData(filteredData) {
    // Asumiendo que tu gráfico de barras necesita una estructura particular.
    // Modifica esta función según lo que tu gráfico necesita.
    return filteredData.map(alarm => {
        return {
            name: alarm.centro,  // o cualquier otro campo relevante
            value: alarm.cantidad  // Asumiendo que `cantidad` es lo que representa el valor de cada barra
        };
    });
}

function matchesSearchTerm(alarm, searchTerm) {
    // Verifica si el centro incluye el término de búsqueda.
    return alarm.centro.toLowerCase().includes(searchTerm.toLowerCase());
}

function getTimeIcon(alarm) {
    if (alarm.gestionado) {
        return alarm.gestionado_dentro_de_tiempo 
            ? `<img src="/static/icons/relojok.png" alt="Dentro de hora" class="time-icon" title="La alarma fue gestionada dentro de los 10 minutos permitidos.">` 
            : `<img src="/static/icons/relojoff.png" alt="Fuera de hora" class="time-icon" title="La alarma fue gestionada fuera de los 10 minutos permitidos.">`;
    }
    return `<img src="/static/icons/relojoff.png" alt="Sin gestionar" class="time-icon" style="visibility: hidden;">`;
}

function updateAlarmsTable(filteredData) {
    console.log("Datos filtrados recibidos:", filteredData);
    const tbody = document.getElementById('alarms-table').getElementsByTagName('tbody')[0];
    tbody.innerHTML = '';

    filteredData.forEach(alarm => {
        const row = tbody.insertRow();

        // Usa la función getTimeIcon en lugar de la lógica duplicada
        const timeIcon = getTimeIcon(alarm);

        row.innerHTML = `
            <td>${alarm.fecha}</td>
            <td>${alarm.hora} ${timeIcon}</td>
            <td>${alarm.centro} ${alarm.gestionado ? "<span class='gestionado'>(Gestionado)</span><span class='checkmark'>&#10003;</span> " + (alarm.gestionado_time || '') : ""}</td>
            <td>${alarm.duracion}</td>
            <td>${alarm.en_modulo}</td>
            <td>${getIconForVerificationState(alarm.estado_verificacion)} ${alarm.estado_verificacion}
                ${alarm.estado_verificacion === 'Persona detectada' ? `<i class="fas fa-image fa-lg icon-spacing icon-image" data-alarm-id="${alarm.id}"></i>` : ''}
            </td>
            <td>${alarm.observacion}</td>`;

        if (alarm.gestionado) {
            row.classList.add('gestionado-row');
        }

        if (selectedAlarmIds.has(alarm.id)) {
            row.classList.add('selected');
        }

        row.setAttribute('data-alarm-id', alarm.id);
        row.setAttribute('data-gestionado-time', alarm.gestionado_time); // Almacena la hora gestionada en el atributo de datos

        row.addEventListener('dblclick', function() {
            isMultiSelectMode = true;
            this.classList.add('selected');
            selectedAlarmIds.add(alarm.id);
        });

        row.addEventListener('click', function() {
            if (isMultiSelectMode) {
                this.classList.toggle('selected');
                if (this.classList.contains('selected')) {
                    selectedAlarmIds.add(alarm.id);
                } else {
                    selectedAlarmIds.delete(alarm.id);
                }
            }
        });
    });
}


// Función para actualizar una sola fila
function updateAlarmRow(alarmId, newObservation, observationTimestamp) {
    requestAnimationFrame(() => {
        const row = document.querySelector(`[data-alarm-id="${alarmId}"]`);
        if (row) {
            const localTime = new Date(observationTimestamp).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' });

            // Actualizar la celda de observación en la tabla
            row.cells[6].textContent = newObservation;

            // Actualizar la celda "centro" para reflejar que la alarma está gestionada o no gestionada
            const centroCell = row.cells[2];
            const centroText = centroCell.innerText.split(" (Gestionado)")[0];

            if (newObservation.trim() !== "") {
                centroCell.innerHTML = `${centroText} <span class='gestionado'>(Gestionado)</span><span class='checkmark'>&#10003;</span> <span class='gestionado-time'>${localTime}</span>`;
                row.classList.add('gestionado-row');
                row.setAttribute('data-gestionado-time', localTime);
            } else {
                const existingTime = row.getAttribute('data-gestionado-time');
                centroCell.innerHTML = `${centroText} <span class='gestionado'>(Gestionado)</span><span class='checkmark'>&#10003;</span> <span class='gestionado-time'>${existingTime || localTime}</span>`;
                row.classList.add('gestionado-row');
                row.setAttribute('data-gestionado-time', existingTime || localTime);
            }
        }
    });
}

// Evento para guardar la observación y actualizar el estado de gestionado
saveBtn.addEventListener('click', function() {
    console.time('Total Save Time');
    const newObservation = document.getElementById('editObservation').value;
    const selectedRows = document.querySelectorAll('.selected');

    if (selectedRows.length > 0) {
        selectedRows.forEach(row => {
            const alarmId = row.getAttribute('data-alarm-id');
            const now = new Date();
            const gestionadoTime = now.toISOString(); // Enviar la hora en formato UTC

            // Preparar los datos para guardar la observación
            const data = {
                id: alarmId,
                observation: newObservation,
                observation_timestamp: gestionadoTime, // Enviar la hora en formato UTC
                action: newObservation.trim() !== "" ? "guardado" : "borrado"
            };

            console.time('Save Observation'); // Inicio del tiempo para guardar la observación
            // Llamar a la función saveObservation que maneja el guardado y continúa procesando la cola de alertas
            saveObservation(data);

            console.timeEnd('Save Observation'); // Fin del tiempo para guardar la observación

            console.time('Update DOM'); // Inicio del tiempo para actualizar el DOM
            // Actualizar la tabla en el lado del cliente
            updateAlarmRow(alarmId, newObservation, gestionadoTime);
            row.classList.remove('selected');
            console.timeEnd('Update DOM'); // Fin del tiempo para actualizar el DOM
        });

        selectedAlarmIds.clear();
        isMultiSelectMode = false;
        overlay.style.display = 'none';
        modal.style.display = 'none';
    }

    console.timeEnd('Total Save Time'); // Fin del tiempo total de guardado
});

// Definir la función saveObservation que envía los datos y continúa procesando la cola de alertas
function saveObservation(data) {
    console.time('Emit Observation');
    // Emitir el evento para actualizar la observación en el servidor
    socket.emit('update_observation', data);
    console.timeEnd('Emit Observation');

    // Procesar la próxima alerta de voz después de un breve retraso
    setTimeout(processAlertQueue, 100); // Esto permite que la interfaz no se bloquee
}


function showImagePopup(alarmId, event) {
    fetch(`/fetch_image?alarm_id=${alarmId}`)
        .then(response => response.json())
        .then(image => {
            if (image.error) {
                console.error(image.error);
                return;
            }

            const popup = document.getElementById('image-popup');
            const popupImage = document.getElementById('popup-image');

            popupImage.src = 'data:image/jpeg;base64,' + image.image;
            popup.style.display = 'block';

            // Posicionar el pop-up cerca del ícono
            const iconRect = event.target.getBoundingClientRect();
            popup.style.top = (iconRect.top + window.scrollY + iconRect.height) + 'px';
            popup.style.left = (iconRect.left + window.scrollX) + 'px';
        })
        .catch(error => console.error('Error al mostrar la imagen:', error));
}

function hideImagePopup() {
    const popup = document.getElementById('image-popup');
    popup.style.display = 'none';
}



// Menú contextual para editar observación
document.addEventListener('contextmenu', function(event) {
    event.preventDefault();
    const existingMenu = document.querySelector('.context-menu');
    if (existingMenu) {
        existingMenu.remove(); // Elimina el menú contextual anterior si existe
    }

    const clickedElement = event.target.closest('tr');
    if (clickedElement && clickedElement.classList.contains('selected')) {
        const contextMenu = document.createElement('div');
        contextMenu.classList.add('context-menu');
        contextMenu.style.left = `${event.pageX}px`;
        contextMenu.style.top = `${event.pageY}px`;

        // Botón para editar observación
        const editButton = document.createElement('div');
        editButton.textContent = 'Editar Observación';
        editButton.classList.add('menu-item');
        contextMenu.appendChild(editButton);

        editButton.addEventListener('click', function() {
            document.getElementById('editObservation').value = '';
            overlay.style.display = 'block';
            modal.style.display = 'block';
            contextMenu.remove(); // Elimina el menú al abrir el modal
        });

        document.body.appendChild(contextMenu);
    }

    // Cierra el menú si se hace clic fuera de él
    document.addEventListener('click', function(event) {
        if (!event.target.closest('.context-menu')) {
            const existingMenu = document.querySelector('.context-menu');
            if (existingMenu) {
                existingMenu.remove();
            }
        }
    }, { once: true });
});



// Función para obtener el icono correspondiente al estado de verificación
function getIconForVerificationState(state) {
    switch(state) {
        case 'Detección en Modulo':
            return '<i class="fas fa-user fa-lg icon-spacing icon-det-modulo"></i>';
        case 'Verificar':
            return '<i class="fas fa-question-circle fa-lg icon-spacing icon-verificar"></i>';
        case 'Falso-Positivo':
            return '<i class="fas fa-exclamation-triangle fa-lg icon-spacing icon-falso-positivo"></i>';
        case 'Zona Crítica':
            return '<i class="fas fa-exclamation-triangle fa-lg icon-spacing icon-zona-critica"></i>';
        case 'Embarcación':
            return '<img src="/static/icons/bote.png" alt="Barco Icono" class="icon-spacing icon-embarcacion" />';
        case 'Persona detectada':
            return '<i class="fas fa-user fa-lg icon-spacing icon-persona-detectada"></i>';
        default:
            return '';
    }
}
        
    // Función para obtener la fecha y hora actual
    function getCurrentDateTime() {
        const now = new Date();
        const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', hour12: true, hour: 'numeric', minute: 'numeric', second: 'numeric' };
        return now.toLocaleDateString('es-ES', options);
    }

    function calculateTimeToNightShift() {
        const now = new Date();
        const nightShiftStart = new Date(now);
        nightShiftStart.setHours(18, 30, 0, 0);
        const nightShiftEnd = new Date(now);
        nightShiftEnd.setDate(nightShiftEnd.getDate() + 1);
        nightShiftEnd.setHours(8, 30, 0, 0);
    
        if (now >= nightShiftStart && now <= nightShiftEnd) {
            // Turno nocturno en curso
            const timeElapsed = now - nightShiftStart;
            const hoursElapsed = Math.floor(timeElapsed / (1000 * 60 * 60));
            const minutesElapsed = Math.floor((timeElapsed % (1000 * 60 * 60)) / (1000 * 60));
            return `Turno Iniciado, llevas ${hoursElapsed} horas y ${minutesElapsed} minutos `;
        } else {
            // Calcula el tiempo restante hasta el turno nocturno
            const timeRemaining = nightShiftStart - now;
            const hoursRemaining = Math.floor(timeRemaining / (1000 * 60 * 60));
            const minutesRemaining = Math.floor((timeRemaining % (1000 * 60 * 60)) / (1000 * 60));
            return `Faltan ${hoursRemaining} horas y ${minutesRemaining} minutos para turno nocturno`;
        }
    }
    
    // Ejemplo de uso
    console.log(calculateTimeToNightShift());
    
// Función para actualizar el reloj y el tiempo restante cada segundo
function updateClockAndCountdown() {
    const clockElement = document.getElementById('clock');
    const countdownElement = document.getElementById('countdown');

    // Actualizar el reloj con la fecha y hora actual
    const currentDateTime = getCurrentDateTime();
    clockElement.textContent = currentDateTime;

    // Calcular y mostrar el tiempo restante para el turno nocturno
    const timeToNightShift = calculateTimeToNightShift();
    countdownElement.textContent = timeToNightShift;

    // Actualizar cada segundo
    setTimeout(updateClockAndCountdown, 1000);
}


    // Actualizar el reloj con la fecha y hora actual
    const currentDateTime = getCurrentDateTime();
    clockElement.textContent = currentDateTime;

    // Calcular y mostrar el tiempo restante para el turno nocturno
    const timeToNightShift = calculateTimeToNightShift();
    countdownElement.textContent = timeToNightShift;

    // Actualizar cada segundo
    setTimeout(updateClockAndCountdown, 1000);

    // Llamar a la función para iniciar el reloj y el conteo regresivo
    updateClockAndCountdown();


// Manejador de eventos para los checkboxes
function setupCheckboxHandlers() {
    const checkboxes = document.querySelectorAll('input[name="response"]');
    checkboxes.forEach(function(checkbox) {
        checkbox.addEventListener('change', function() {
            var textarea = document.getElementById('editObservation');
            // Construir el texto de las opciones seleccionadas
            var selectedOptions = Array.from(checkboxes) 
                .filter(ch => ch.checked)
                .map(ch => ch.value)
                .join('\n');
            textarea.value = selectedOptions;
        });
    });
}
// Suponiendo que tus filas tienen un evento click para seleccionar
document.querySelectorAll('tr').forEach(row => {
    row.addEventListener('click', function() {
        if (isMultiSelectMode) {
            this.classList.toggle('selected');
            const alarmId = this.getAttribute('data-alarm-id');
            if (this.classList.contains('selected')) {
                selectedAlarmIds.add(alarmId);
            } else {
                selectedAlarmIds.delete(alarmId);
            }
        }
    });

    row.addEventListener('dblclick', function() {
        isMultiSelectMode = !isMultiSelectMode; // Alternar el modo de selección múltiple
        if (isMultiSelectMode) {
            this.classList.add('selected');
            selectedAlarmIds.add(this.getAttribute('data-alarm-id'));
        } else {
            this.classList.remove('selected');
            selectedAlarmIds.delete(this.getAttribute('data-alarm-id'));
        }
    });
});

// Manejador de eventos para la tabla de alertas
function setupAlertTableClickHandlers() {
    const alertTableRows = document.getElementById('alerts-table').getElementsByTagName('tbody')[0].rows;
    Array.from(alertTableRows).forEach(row => {
        row.addEventListener('click', function() {
            const alertId = this.getAttribute('data-alert-id');
            const currentText = this.cells[3].textContent; // Asumiendo que el texto está en la cuarta columna
            document.getElementById('editObservation').value = currentText;
            document.querySelector('.modal').style.display = 'block';
            document.querySelector('.overlay').style.display = 'block';
            document.getElementById('saveObservation').setAttribute('data-alert-id', alertId);
        });
    });
}

    const saveAlertButton = document.getElementById('saveObservation');
    if (saveAlertButton) {
        saveAlertButton.addEventListener('click', function() {
            const alertId = this.getAttribute('data-alert-id');
            const newDescription = document.getElementById('editObservation').value;
            socket.emit('update_alert_description', {
                alert_id: alertId,
                description: newDescription
            });

            // Actualizar la fila correspondiente con el estado gestionado
            const row = document.querySelector(`tr[data-alarm-id='${alertId}']`);
            if (row) {
                const centroCell = row.cells[2]; // Asumiendo que el centro está en la tercera columna
                centroCell.innerHTML += ' <span style="color: green;">(Gestionado)</span>';
            }

            document.querySelector('.modal').style.display = 'none';
            document.querySelector('.overlay').style.display = 'none';
        });
    } else {
        console.error('El elemento saveObservation no está disponible en el DOM');
    }

    const closeAlertModalButton = document.getElementById('closeModal');
    if (closeAlertModalButton) {
        closeAlertModalButton.addEventListener('click', function() {
            document.querySelector('.modal').style.display = 'none';
            document.querySelector('.overlay').style.display = 'none';
        });
    } else {
        console.error('El elemento closeModal no está disponible en el DOM');
    }

    setupAlertTableClickHandlers();

function exportTableToExcel(tableID, filename = ''){
    var downloadLink;
    var dataType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    var tableSelect = document.getElementById(tableID);
    var workbook = XLSX.utils.table_to_book(tableSelect, {sheet: "Sheet1"});
    var excelBuffer = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });

    // Crear un Blob con los datos en un formato que Excel pueda leer
    var data = new Blob([excelBuffer], {type: dataType});
    var csvURL = window.URL.createObjectURL(data);

    // Crear un enlace temporal para descargar
    downloadLink = document.createElement("a");
    document.body.appendChild(downloadLink);

    if(navigator.msSaveOrOpenBlob){
        navigator.msSaveOrOpenBlob(data, filename);
    } else {
        downloadLink.href = csvURL;
        downloadLink.download = filename;
        downloadLink.click();
    }

    document.body.removeChild(downloadLink);
}
function formatDuration(duration) {
    const totalSeconds = Math.floor(duration);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes > 0 ? `${minutes} min ` : ''}${seconds} seg`;
}
function showImages(timestamp, center) {
    fetch(`/get_images?timestamp=${timestamp}&center=${center}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                console.error(data.error);
                return;
            }

            const imagesContainer = document.getElementById('images-container');
            imagesContainer.innerHTML = ''; // Limpiar contenedor de imágenes antes de agregar nuevas

            data.forEach(imageBase64 => {
                const img = document.createElement('img');
                img.src = 'data:image/jpeg;base64,' + imageBase64;
                imagesContainer.appendChild(img);
            });

            console.log('Imágenes descargadas:', data);
        })
        .catch(error => console.error('Error al descargar las imágenes:', error));
}
