const connectionStates = {};

// Función para calcular el tiempo de desconexión en un formato legible
function calculateDisconnectionTime(disconnectionTimestamp) {
    const currentTime = Date.now();
    const differenceInMs = currentTime - disconnectionTimestamp;

    const minutes = Math.floor(differenceInMs / 60000);
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;

    if (hours > 0) {
        return `${hours}h${remainingMinutes}m`;
    } else {
        return `${remainingMinutes}m`;
    }
}

// Función para obtener el HTML del icono de alerta
function getAlertWithIconHTML(alerta) {
    let iconHtml = '';
    switch (alerta) {
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
    return `${iconHtml}${alerta}`;
}

// Función para actualizar la segunda tabla
function updateSecondTable() {
    console.log('Fetching latest victron data...');
    fetch('/get_latest_victron_data')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok ' + response.statusText);
            }
            return response.json();
        })
        .then(data => {
            console.log('Received data:', data);
            if (data.error) {
                console.error('Data error:', data.error);
                return;
            }

            // Separar el timestamp en fecha y hora
            const [fecha, hora] = data.timestamp.split(' ');
            console.log('Fecha:', fecha, 'Hora:', hora);

            const tbody = document.querySelector('#alerts-table tbody');
            if (tbody) {
                // Buscar si ya existe una fila para este centro
                let existingRow = tbody.querySelector(`tr[data-center-id="${data.centro}"]`);

                if (data.enlace === 'conectado a internet') {
                    // Si el centro se ha reconectado
                    if (existingRow && connectionStates[data.centro] && connectionStates[data.centro].status === 'disconnected') {
                        // Actualizar estado a conectado
                        connectionStates[data.centro].status = 'connected';
                        connectionStates[data.centro].reconnectedAt = Date.now();

                        // Indicar que está conectado a internet
                        existingRow.querySelector('.link').textContent = 'conectado a internet';
                        existingRow.querySelector('.link-icon').innerHTML = '<i class="fas fa-wifi"></i>';
                        existingRow.classList.remove('disconnected');
                        existingRow.classList.add('connected');

                        // Calcular y mostrar el tiempo total de desconexión
                        const disconnectionTime = calculateDisconnectionTime(connectionStates[data.centro].disconnectedAt);
                        existingRow.querySelector('.total').textContent = disconnectionTime;

                        // No eliminar la fila después de 20 segundos
                    }
                } else {
                    // Si el centro está desconectado
                    if (!existingRow) {
                        // Crear una nueva fila
                        const newRow = document.createElement('tr');
                        newRow.setAttribute('data-center-id', data.centro);
                        newRow.classList.add('disconnected');

                        newRow.innerHTML = `
                            <td class="date">${fecha}</td>
                            <td class="time">${hora}</td>
                            <td>${data.centro}</td>
                            <td class="link">${data.enlace} <span class="link-icon"><i class="fas fa-wifi"></i></span></td> <!-- Icono de desconexión -->
                            <td class="total">${calculateDisconnectionTime(Date.parse(data.timestamp))}</td> <!-- Calcular tiempo de desconexión -->
                        `;

                        tbody.prepend(newRow); // Insertar la fila al principio
                        // Registrar el estado de desconexión
                        connectionStates[data.centro] = { status: 'disconnected', disconnectedAt: Date.parse(data.timestamp) };
                    } else {
                        // Actualizar la fila existente
                        existingRow.querySelector('.date').textContent = fecha;
                        existingRow.querySelector('.time').textContent = hora;
                        existingRow.querySelector('.link').innerHTML = `${data.enlace} <span class="link-icon"><i class="fas fa-wifi"></i></span>`;
                        existingRow.classList.remove('connected');
                        existingRow.classList.add('disconnected');

                        // Calcular y mostrar el tiempo total de desconexión
                        const disconnectionTime = calculateDisconnectionTime(connectionStates[data.centro].disconnectedAt);
                        existingRow.querySelector('.total').textContent = disconnectionTime;

                        // Registrar el estado de desconexión
                        connectionStates[data.centro] = { status: 'disconnected', disconnectedAt: Date.parse(data.timestamp) };
                    }
                }
                console.log('Table updated successfully');
            } else {
                console.error('Table body not found');
            }


        });
}

// Función para actualizar la tabla de alertas
function updateAlertsTable(groupedAlerts) {
    const tbody = document.getElementById('alerts-table').getElementsByTagName('tbody')[0];

    // Limpiar las filas de alertas pero mantener la fila de enlace en la parte superior
    const enlaceRow = tbody.querySelector('tr[data-center-id]');
    tbody.innerHTML = '';
    if (enlaceRow) {
        tbody.appendChild(enlaceRow);
    }

    const sortedAlerts = Object.values(groupedAlerts).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    sortedAlerts.forEach(alert => {
        // Ignorar alertas de centros que se reconectaron recientemente
        if (connectionStates[alert.centro] && connectionStates[alert.centro].status === 'connected') {
            const reconnectedAt = connectionStates[alert.centro].reconnectedAt;
            if (Date.now() - reconnectedAt < 5 * 60 * 1000) { // 5 minutos
                return;
            } else {
                // Si ya pasaron 5 minutos, eliminar el registro
                delete connectionStates[alert.centro];
            }
        }

        const row = document.createElement('tr');
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
}

// Llamar a las funciones para actualizar la tabla cada cierto intervalo
setInterval(updateSecondTable, 10000); // Actualiza cada 10 segundos
setInterval(() => updateAlertsTable({ /* Simular datos aquí */ }), 10000); // Actualiza las alertas cada 10 segundos

// Llamar las funciones una vez para la actualización inicial
updateSecondTable();
updateAlertsTable({ /* Simular datos aquí */ });
