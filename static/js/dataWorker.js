self.onmessage = function(e) {
    // Procesar los datos aquí. Este es un ejemplo simple que solo pasa los datos de vuelta.
    self.postMessage(e.data);
};
