// Este bloque asegura que el código solo se ejecuta una vez que el DOM esté completamente cargado.
document.getElementById('save-observation').addEventListener('click', function() {
    const modal = document.getElementById('edit-modal');
    const alertId = modal.getAttribute('data-alert-id');
    console.log("Saving with Alert ID:", alertId);

    if (!alertId) {
        console.error("Cannot save. Alert ID is undefined.");
        return;
    }

    const observationText = document.getElementById('observation-input').value;
    sendObservationToServer(alertId, observationText);
    modal.style.display = 'none';
});

    // Añade un event listener al botón 'Cerrar' para ocultar el modal.
    document.getElementById('close-modal').addEventListener('click', function() {
        document.getElementById('edit-modal').style.display = 'none';
    });


// Función que se llama al hacer clic en una fila de la tabla para abrir el modal de edición.
function openEditModal(alertId) {
    const modal = document.getElementById('edit-modal');
    console.log("Opening modal with Alert ID:", alertId);

    if (!alertId) {
        console.error("Alert ID is missing or invalid:", alertId);
        return;
    }

    modal.setAttribute('data-alert-id', alertId);
    document.getElementById('observation-input').value = '';
    modal.style.display = 'block';
}


// Función para enviar la observación editada al servidor.
function sendObservationToServer(alertId, observationText) {
    if (!alertId || isNaN(alertId)) {
        console.error("Alert ID is invalid:", alertId);
        return;
    }

    fetch('/save-observation', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            alerta_id: alertId,
            texto: observationText
        })
    })
    .then(response => response.json())
    .then(data => {
        console.log('Response:', data);
        if (data.status === 'success') {
            console.log('Observación guardada correctamente.');
        } else {
            console.error('No se pudo guardar la observación: ', data.message);
        }
    })
    .catch(error => {
        console.error('Error al hacer la solicitud:', error);
    });
}

