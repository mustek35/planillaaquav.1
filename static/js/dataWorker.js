self.onmessage = function(e) {
    const { alarmsData, searchTerm, filter } = e.data;

    const matchesSearchTerm = (alarm, term) => {
        return alarm.centro.toLowerCase().includes(term.toLowerCase());
    };

    const matchesFilter = (alarm, filterValue) => {
        switch (filterValue) {
            case 'online':
                return true;
            case 'Duración':
                return Number(alarm.duracion) > 7;
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
                return !alarm.gestionado;
            case 'Gestionado':
                return alarm.gestionado;
            default:
                return true;
        }
    };

    const filteredData = alarmsData.filter(alarm =>
        matchesSearchTerm(alarm, searchTerm) && matchesFilter(alarm, filter)
    );

    self.postMessage(filteredData);
};
