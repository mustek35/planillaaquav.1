document.addEventListener('DOMContentLoaded', function () {
    var socket = io.connect(location.protocol + '//' + document.domain + ':' + location.port);

    window.updateBarChart = function(data) {}

    const moduleStatusSelector = document.getElementById('moduleStatus');
    var barChartDom = document.getElementById('bar-chart');
    var barChart = echarts.init(barChartDom);
    
    var barOption = {
        title: {
            text: 'Detecciones en los centros de cultivo',
            subtext: '18:30 - 07:00',
            left: 'center',
            textStyle: { color: 'white' }
        },
        grid: {
            left: '3%',
            right: '4%',
            bottom: '3%',
            containLabel: true
        },
        xAxis: {
            type: 'category',
            data: ['centro 1', 'centro 2', 'centro 3', 'centro 4', 'centro 5', 'centro 6', 'centro 7', 'centro 8', 'centro 9', 'centro 10', 'centro 11', 'centro 12', 'centro 13', 'centro 14', 'centro 15', 'centro 16'],
            axisTick: { alignWithLabel: true },
            axisLabel: { color: 'white', interval: 0, rotate: 45, margin: 20 } // Aumenta el margen para más espacio
        },
        yAxis: {
            type: 'value',
            axisLabel: { color: 'white' }
        },
        series: [{
            name: 'Detecciones',
            type: 'bar',
            barWidth: '40%', // Ajusta el ancho de las columnas
            barCategoryGap: '80%', // Aumenta el espacio entre columnas
            data: [10, 20, 30, 40, 50, 45, 33, 22, 18, 15, 10, 12, 11, 9, 6, 5],
            itemStyle: {
                color: function(params) {
                    var colorList = ['#c23531', '#2f4554', '#61a0a8', '#d48265', '#91c7ae'];
                    return colorList[params.dataIndex % colorList.length];
                }
            },
            label: { show: true, position: 'top', color: 'white' }
        }]
    };
    barChart.setOption(barOption);

    function updateBarChart(data) {
        console.log("Actualizando gráfico con datos:", data);
        if (!Array.isArray(data)) {
            return; // Termina la ejecución si no es un arreglo
        }
    
        // Ordenar los datos por valor de menor a mayor
        data.sort((a, b) => a.value - b.value);
    
        var barCenters = data.map(item => item.name);
        var barCounts = data.map(item => item.value);
    
        // Calcular el total de detecciones
        var totalDetections = barCounts.reduce((a, b) => a + b, 0);
    
        // Obtener los Top 3 centros
        var top1 = data[data.length - 1]; // El de mayor valor
        var top2 = data[data.length - 2]; // El segundo mayor valor
        var top3 = data[data.length - 3]; // El tercer mayor valor
    
        // Obtener el total de centros
        var totalCenters = data.length;
    
        // Crear el texto del subtítulo con los Top 3 y la cantidad total de centros
        var subtitleText = `18:30 - 07:00 | Top 1: ${top1.name} (${top1.value}), Top 2: ${top2.name} (${top2.value}), Top 3: ${top3.name} (${top3.value}) | Centros: ${totalCenters}`;
    
        // Actualizar el gráfico con los nuevos datos
        barChart.setOption({
            title: {
                text: 'Detecciones en los centros de cultivo - Total: ' + totalDetections,
                subtext: subtitleText,
                left: 'center',
                textStyle: { color: 'white' },
                subtextStyle: { color: 'white' }
            },
            xAxis: { data: barCenters },
            series: [{
                data: barCounts,
                barWidth: '40%', // Ajusta el ancho de las columnas
                barCategoryGap: '80%' // Aumenta el espacio entre columnas
            }]
        });
    }
    
    moduleStatusSelector.addEventListener('change', function() {
        const selectedStatus = this.value;
        if (selectedStatus === 'Módulo') {
            var filteredData = window.fullData.filter(data => data.en_modulo === 'Módulo');
            updateBarChart(filteredData);
        } else {
            socket.emit('request_filtered_data', { status: selectedStatus });
        }
    });

    // Función para verificar si es de noche
    function isNightTime() {
        const now = new Date();
        const hours = now.getHours();
        // Consideramos noche desde las 18:00 (6 PM) hasta las 07:00 (7 AM)
        return (hours >= 18 || hours < 7);
    }
    
    // Establece la actualización automática cada 18 segundos después de que se establezca la conexión solo de noche
    socket.on('connect', function() {
        socket.emit('request_latest_data');

        if (isNightTime()) {
            setInterval(function() {
                if (isNightTime()) {
                    console.log("Solicitando datos actualizados...");  // Agrega esto para depuración
                    socket.emit('request_latest_data');
                }
            }, 18000); // 18000 milisegundos = 18 segundos
        }
    });

    socket.on('update_data', function(data) {
        console.log("Datos recibidos para actualización:", data);
        if (Array.isArray(data)) {
            updateBarChart(data);  // Actualiza el gráfico con los nuevos datos
        }
    });

    socket.on('filtered_data', function(filteredData) {
        updateBarChart(filteredData);
    });

    function resizeCharts() {
        barChart.resize();
    }

    window.addEventListener('resize', resizeCharts);
});
