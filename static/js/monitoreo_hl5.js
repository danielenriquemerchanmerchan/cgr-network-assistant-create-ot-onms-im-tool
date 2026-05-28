// ============================================
// MONITOREO HL5 - JAVASCRIPT CON GRÁFICA MODERNA
// ============================================

let mapaHL5;
let markersLayer;
let chartHistorico;
let chartDepartamentos;
let chartCiudades;
let chartRBSDepartamentos;
let chartRBSMunicipios;
let datosDetalle = [];
let datosHistoricoCompletos = []; // Almacenar todos los datos históricos
let horasFiltro = 12; // Filtro por defecto: 12 horas

// ── Histórico por Departamento ──────────────────────────────────
let chartHistoricoDepto = null;
let horasHistoricoDepto = 12;
let departamentoSeleccionado = '';

// ── Histórico por Ciudad ────────────────────────────────────────
let chartHistoricoCiudad = null;
let horasHistoricoCiudad = 12;
let ciudadSeleccionada = '';

const COLORES_DEPTO = [
    '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6',
    '#06b6d4', '#ec4899', '#84cc16', '#f97316', '#6366f1',
    '#14b8a6', '#e11d48', '#0ea5e9', '#d97706', '#7c3aed',
    '#64748b', '#22c55e', '#a855f7', '#fb923c', '#38bdf8'
];
const columnasDetalle = [
    'HORA_INICIO',
    'NODE',
    'CINUM',
    'CINAME',
    'CIUDAD',
    'DEPARTAMENTO',
    '3G',
    '4G',
    'TOTAL_RB',
    'B2B',
    'INC_HL5',
    'INC_MOVIL',
    'CEXP'
];
const filtrosActivos = {}; // Almacenar filtros activos por columna
let columnaFiltroActual = null; // Columna siendo filtrada actualmente
let tiempoUltimaActualizacion = null; // Para mostrar el tiempo transcurrido

// ============================================
// INICIALIZACIÓN
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Iniciando Monitoreo HL5...');
    inicializarMapa();
    inicializarGrafica();
    inicializarGraficosUbicacion();
    inicializarGraficosRBS();
    inicializarFiltrosGrafica(); // Agregar event listeners a los botones
    inicializarFiltrosTabla(); // Nuevo sistema de filtros con modal
    inicializarFiltrosGraficaDepto(); // Botones 12h/24h + selector del histórico por departamento
    inicializarFiltrosGraficaCiudad(); // Botones 12h/24h + selector del histórico por ciudad
    cargarDatos();
    
    // ⚡ AUTO-RECARGA CADA 10 MINUTOS (600000 ms)
    setInterval(cargarDatos, 600000);
    
    // Mostrar notificación de auto-recarga
    console.log('⏰ Auto-recarga configurada: cada 10 minutos');
    
    // Actualizar contador de tiempo cada minuto
    setInterval(actualizarContadorTiempo, 60000);
});

// ============================================
// FUNCIÓN PARA ACTUALIZAR CONTADOR DE TIEMPO
// ============================================

function actualizarContadorTiempo() {
    if (!tiempoUltimaActualizacion) return;
    
    const ahora = new Date();
    const diferencia = Math.floor((ahora - tiempoUltimaActualizacion) / 60000); // minutos
    
    const horaElement = document.getElementById('hora-actualizacion');
    if (horaElement && diferencia < 60) {
        const textoOriginal = horaElement.textContent;
        if (textoOriginal && !textoOriginal.includes('hace')) {
            horaElement.textContent = `${textoOriginal} (hace ${diferencia} min)`;
        }
    }
}

// ============================================
// INICIALIZACIÓN DEL MAPA
// ============================================

function inicializarMapa() {
    console.log('🗺️ Inicializando mapa...');
    
    // Centrar en Colombia
    mapaHL5 = L.map('mapa-hl5').setView([4.5709, -74.2973], 6);
    
    // Añadir capa de OpenStreetMap
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 18
    }).addTo(mapaHL5);
    
    // Crear capa para los marcadores
    markersLayer = L.layerGroup().addTo(mapaHL5);
    
    console.log('✅ Mapa inicializado correctamente');
}

// ============================================
// INICIALIZACIÓN DE FILTROS DE GRÁFICA
// ============================================

function inicializarFiltrosGrafica() {
    console.log('🔘 Inicializando filtros de gráfica...');
    
    const filterButtons = document.querySelectorAll('.filter-btn[data-horas]');
    
    filterButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Remover clase active de todos los botones
            filterButtons.forEach(btn => btn.classList.remove('active'));
            
            // Agregar clase active al botón clickeado
            this.classList.add('active');
            
            // Obtener el valor de horas del botón
            horasFiltro = parseInt(this.dataset.horas);
            
            console.log(`📊 Filtro cambiado a ${horasFiltro} horas`);
            
            // Actualizar la gráfica con el nuevo filtro
            if (datosHistoricoCompletos.length > 0) {
                actualizarGrafica(datosHistoricoCompletos);
            }
        });
    });
    
    console.log('✅ Filtros de gráfica inicializados');
}

// ============================================
// INICIALIZACIÓN DE FILTROS DE TABLA
// ============================================

function inicializarFiltrosTabla() {
    console.log('🔍 Inicializando sistema de filtros de tabla...');
    
    const modal = document.getElementById('filter-modal');
    const modalClose = document.querySelector('.filter-modal-close');
    const btnOk = document.getElementById('filter-btn-ok');
    const btnCancel = document.getElementById('filter-btn-cancel');
    const searchInput = document.getElementById('filter-search-input');
    const optionsContainer = document.getElementById('filter-options-container');
    const btnLimpiarFiltros = document.getElementById('btn-limpiar-filtros');
    
    // Event listeners para iconos de filtro
    document.querySelectorAll('.filter-icon').forEach(icon => {
        icon.addEventListener('click', function(e) {
            e.stopPropagation();
            const columna = this.dataset.col;
            columnaFiltroActual = columna;
            abrirModalFiltro(columna);
        });
    });
    
    // Cerrar modal
    modalClose.addEventListener('click', cerrarModalFiltro);
    btnCancel.addEventListener('click', cerrarModalFiltro);
    
    // Cerrar al hacer clic fuera del modal
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            cerrarModalFiltro();
        }
    });
    
    // Aplicar filtro
    btnOk.addEventListener('click', aplicarFiltroModal);
    
    // Buscar en opciones de filtro
    searchInput.addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase();
        const options = optionsContainer.querySelectorAll('.filter-option');
        
        options.forEach(option => {
            const label = option.querySelector('label').textContent.toLowerCase();
            if (label.includes(searchTerm)) {
                option.style.display = 'flex';
            } else {
                option.style.display = 'none';
            }
        });
    });
    
    // Limpiar todos los filtros
    btnLimpiarFiltros.addEventListener('click', limpiarTodosFiltros);
    
    console.log('✅ Sistema de filtros de tabla inicializado');
}

function abrirModalFiltro(columna) {
    const modal = document.getElementById('filter-modal');
    const optionsContainer = document.getElementById('filter-options-container');
    const searchInput = document.getElementById('filter-search-input');
    
    // Limpiar búsqueda anterior
    searchInput.value = '';
    
    // Obtener valores únicos de la columna
    const valoresUnicos = Array.from(
        new Set(
            datosDetalle
                .map(item => String(item[columna] || ''))
                .filter(v => v !== '')
        )
    ).sort((a, b) => a.localeCompare(b, 'es', { sensitivity: 'base' }));
    
    // Crear opciones de checkbox
    optionsContainer.innerHTML = '';
    valoresUnicos.forEach(valor => {
        const isChecked = filtrosActivos[columna] && filtrosActivos[columna].includes(valor);
        
        const optionDiv = document.createElement('div');
        optionDiv.className = 'filter-option';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `filter-${valor}`;
        checkbox.value = valor;
        checkbox.checked = isChecked;
        
        const label = document.createElement('label');
        label.htmlFor = `filter-${valor}`;
        label.textContent = valor;
        
        optionDiv.appendChild(checkbox);
        optionDiv.appendChild(label);
        
        // Hacer clic en la opción también selecciona el checkbox
        optionDiv.addEventListener('click', function(e) {
            if (e.target !== checkbox) {
                checkbox.checked = !checkbox.checked;
            }
        });
        
        optionsContainer.appendChild(optionDiv);
    });
    
    // Mostrar modal
    modal.classList.add('show');
}

function cerrarModalFiltro() {
    const modal = document.getElementById('filter-modal');
    modal.classList.remove('show');
    columnaFiltroActual = null;
}

function aplicarFiltroModal() {
    if (!columnaFiltroActual) return;
    
    const optionsContainer = document.getElementById('filter-options-container');
    const checkboxes = optionsContainer.querySelectorAll('input[type="checkbox"]:checked');
    
    const valoresSeleccionados = Array.from(checkboxes).map(cb => cb.value);
    
    if (valoresSeleccionados.length > 0) {
        filtrosActivos[columnaFiltroActual] = valoresSeleccionados;
        console.log(`✅ Filtro aplicado a ${columnaFiltroActual}:`, valoresSeleccionados);
    } else {
        delete filtrosActivos[columnaFiltroActual];
        console.log(`🗑️ Filtro removido de ${columnaFiltroActual}`);
    }
    
    // Actualizar icono de filtro activo
    actualizarIconosFiltro();
    
    // Renderizar tabla con los filtros aplicados
    renderizarTablaFiltrada();
    
    cerrarModalFiltro();
}

function limpiarTodosFiltros() {
    console.log('🗑️ Limpiando todos los filtros...');
    
    // Limpiar objeto de filtros
    Object.keys(filtrosActivos).forEach(key => delete filtrosActivos[key]);
    
    // Actualizar iconos
    actualizarIconosFiltro();
    
    // Re-renderizar tabla
    renderizarTablaFiltrada();
    
    console.log('✅ Todos los filtros limpiados');
}

function actualizarIconosFiltro() {
    document.querySelectorAll('.filter-icon').forEach(icon => {
        const columna = icon.dataset.col;
        if (filtrosActivos[columna] && filtrosActivos[columna].length > 0) {
            icon.style.color = '#e74c3c'; // Color rojo para filtro activo
        } else {
            icon.style.color = '#7f8c8d'; // Color gris por defecto
        }
    });
}

// ============================================
// FUNCIÓN PARA MANEJAR CLICKS EN TIEMPO
// ============================================

function manejarClickTiempo(tipo) {
    console.log(`⌛ Click en tiempo: ${tipo}`);
    
    const columna = 'HORA_INICIO';
    if (!columna) return;

    let minHoras = null; // límite inferior (horas o días convertidos a horas)
    let maxHoras = null; // límite superior

    switch (tipo) {
        case 'menor_4h':
            maxHoras = 4;
            break;
        case 'menor_8h':
            minHoras = 4;
            maxHoras = 8;
            break;
        case 'menor_24h':
            minHoras = 8;
            maxHoras = 24;
            break;
        case 'mayor_1d':
            minHoras = 24;
            maxHoras = 48;
            break;
        case 'mayor_2d':
            minHoras = 48;
            maxHoras = 72;
            break;
        case 'mayor_3d':
            minHoras = 72;
            maxHoras = 96;
            break;
        case 'mayor_4d':
            minHoras = 96;
            maxHoras = 120;
            break;
        case 'mayor_5d':
            minHoras = 120;
            maxHoras = 144;
            break;
        case 'mayor_6d':
            minHoras = 144;
            maxHoras = 168;
            break;
        case 'mayor_7d':
            minHoras = 168;
            maxHoras = 360; // hasta <15 días
            break;
        case 'mayor_15d':
            minHoras = 360;
            break;
        default:
            return;
    }

    const ahora = new Date();

    filtrosActivos[columna] = datosDetalle
        .filter(row => {
            if (!row.HORA_INICIO) return false;
            const fecha = parsearFecha(row.HORA_INICIO);
            if (!fecha) return false;

            if (minHoras !== null) {
                const limiteInferior = new Date(ahora.getTime() - minHoras * 60 * 60 * 1000);
                if (fecha > limiteInferior) return false; // demasiado reciente
            }

            if (maxHoras !== null) {
                const limiteSuperior = new Date(ahora.getTime() - maxHoras * 60 * 60 * 1000);
                if (fecha <= limiteSuperior) return false; // demasiado antiguo
            }

            return true;
        })
        .map(row => row.HORA_INICIO);

    actualizarIconosFiltro();
    renderizarTablaFiltrada();
}
// ============================================
// INICIALIZACIÓN DE GRÁFICA HISTÓRICA
// ============================================

function inicializarGrafica() {
    console.log('📈 Inicializando gráfica histórica...');
    
    const ctx = document.getElementById('chart-historico');
    if (!ctx) {
        console.error('❌ No se encontró el canvas chart-historico');
        return;
    }
    
    chartHistorico = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'HL5 Afectados',
                    data: [],
                    borderColor: '#e74c3c',
                    backgroundColor: 'rgba(231, 76, 60, 0.05)',
                    borderWidth: 3,
                    tension: 0.4,
                    fill: true,
                    pointRadius: 2,
                    pointHoverRadius: 4
                },
                {
                    label: '3G',
                    data: [],
                    borderColor: '#3498db',
                    backgroundColor: 'rgba(52, 152, 219, 0.05)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    pointRadius: 2,
                    pointHoverRadius: 4
                },
                {
                    label: '4G',
                    data: [],
                    borderColor: '#2ecc71',
                    backgroundColor: 'rgba(46, 204, 113, 0.05)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    pointRadius: 2,
                    pointHoverRadius: 4
                },
                {
                    label: 'Total RBS',
                    data: [],
                    borderColor: '#f39c12',
                    backgroundColor: 'rgba(243, 156, 18, 0.05)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true,
                    pointRadius: 2,
                    pointHoverRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false, // Desactivar animaciones para mejor rendimiento
            interaction: {
                mode: 'nearest',
                intersect: true
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        font: {
                            size: 12,
                            weight: 'bold'
                        },
                        padding: 15,
                        usePointStyle: true
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    },
                    ticks: {
                        maxRotation: 45,
                        minRotation: 45,
                        font: {
                            size: 10
                        }
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    },
                    ticks: {
                        font: {
                            size: 11
                        }
                    }
                }
            }
        }
    });
    
    console.log('✅ Gráfica histórica inicializada');
}

// ============================================
// INICIALIZACIÓN DE GRÁFICOS DE UBICACIÓN (HL5)
// ============================================

function inicializarGraficosUbicacion() {
    console.log('📊 Inicializando gráficos de ubicación HL5...');
    
    // Gráfico de Departamentos
    const ctxDep = document.getElementById('chart-departamentos');
    if (ctxDep) {
        chartDepartamentos = new Chart(ctxDep, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'HL5 Afectados',
                    data: [],
                    backgroundColor: '#e74c3c',
                    borderColor: '#c0392b',
                    borderWidth: 2,
                    borderRadius: 5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                animation: false, // ⚡ Sin animaciones para mejor rendimiento
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        titleColor: '#fff',
                        bodyColor: '#fff',
                        borderWidth: 1,
                        padding: 10
                    },
                    datalabels: {
                        anchor: 'end',
                        align: 'end',
                        color: '#333',
                        font: {
                            weight: 'bold',
                            size: 11
                        }
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        ticks: {
                            font: { size: 11 }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    y: {
                        ticks: {
                            font: { size: 10 }
                        },
                        grid: {
                            display: false
                        }
                    }
                }
            },
            plugins: [ChartDataLabels]
        });
        console.log('✅ Gráfico de departamentos (HL5) inicializado');
    }
    
    // Gráfico de Ciudades
    const ctxCiu = document.getElementById('chart-ciudades');
    if (ctxCiu) {
        chartCiudades = new Chart(ctxCiu, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'HL5 Afectados',
                    data: [],
                    backgroundColor: '#3498db',
                    borderColor: '#2980b9',
                    borderWidth: 2,
                    borderRadius: 5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                animation: false, // ⚡ Sin animaciones para mejor rendimiento
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        titleColor: '#fff',
                        bodyColor: '#fff',
                        borderWidth: 1,
                        padding: 10
                    },
                    datalabels: {
                        anchor: 'end',
                        align: 'end',
                        color: '#333',
                        font: {
                            weight: 'bold',
                            size: 11
                        }
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        ticks: {
                            font: { size: 11 }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    y: {
                        ticks: {
                            font: { size: 10 }
                        },
                        grid: {
                            display: false
                        }
                    }
                }
            },
            plugins: [ChartDataLabels]
        });
        console.log('✅ Gráfico de ciudades (HL5) inicializado');
    }
    
    console.log('✅ Gráficos de ubicación HL5 inicializados correctamente');
}

// ============================================
// INICIALIZACIÓN DE GRÁFICOS DE RBS
// ============================================

function inicializarGraficosRBS() {
    console.log('📊 Inicializando gráficos de RBS...');
    
    // Gráfico de RBS por Departamentos
    const ctxRbsDep = document.getElementById('chart-rbs-departamentos');
    if (ctxRbsDep) {
        chartRBSDepartamentos = new Chart(ctxRbsDep, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [
                    {
                        label: '3G',
                        data: [],
                        backgroundColor: 'rgba(52, 152, 219, 0.7)',  // Azul
                        borderColor: 'rgba(52, 152, 219, 1)',
                        borderWidth: 2,
                        borderRadius: 5
                    },
                    {
                        label: '4G',
                        data: [],
                        backgroundColor: 'rgba(46, 204, 113, 0.7)',  // Verde
                        borderColor: 'rgba(46, 204, 113, 1)',
                        borderWidth: 2,
                        borderRadius: 5
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                animation: false, // ⚡ Sin animaciones para mejor rendimiento
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            font: {
                                size: 11,
                                weight: 'bold'
                            },
                            padding: 10
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        titleColor: '#fff',
                        bodyColor: '#fff',
                        borderWidth: 1,
                        padding: 10,
                        displayColors: true,
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + context.parsed.x;
                            },
                            footer: function(tooltipItems) {
                                let sum = 0;
                                tooltipItems.forEach(function(tooltipItem) {
                                    sum += tooltipItem.parsed.x;
                                });
                                return 'Total: ' + sum;
                            }
                        }
                    },
                    datalabels: {
                        display: false  // No mostrar labels individuales en barras apiladas
                    }
                },
                scales: {
                    x: {
                        stacked: true,
                        beginAtZero: true,
                        ticks: {
                            font: {
                                size: 11
                            },
                            stepSize: 5
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    y: {
                        stacked: true,
                        ticks: {
                            font: {
                                size: 10
                            }
                        },
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
        console.log('✅ Gráfico de RBS por departamentos inicializado');
    }
    
    // Gráfico de RBS por Municipios
    const ctxRbsMun = document.getElementById('chart-rbs-municipios');
    if (ctxRbsMun) {
        chartRBSMunicipios = new Chart(ctxRbsMun, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [
                    {
                        label: '3G',
                        data: [],
                        backgroundColor: 'rgba(52, 152, 219, 0.7)',  // Azul
                        borderColor: 'rgba(52, 152, 219, 1)',
                        borderWidth: 2,
                        borderRadius: 5
                    },
                    {
                        label: '4G',
                        data: [],
                        backgroundColor: 'rgba(46, 204, 113, 0.7)',  // Verde
                        borderColor: 'rgba(46, 204, 113, 1)',
                        borderWidth: 2,
                        borderRadius: 5
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',  // Horizontal bars
                animation: false, // ⚡ Sin animaciones para mejor rendimiento
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            font: {
                                size: 11,
                                weight: 'bold'
                            },
                            padding: 10
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        titleColor: '#fff',
                        bodyColor: '#fff',
                        borderWidth: 1,
                        padding: 10,
                        displayColors: true,
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + context.parsed.x;
                            },
                            footer: function(tooltipItems) {
                                let sum = 0;
                                tooltipItems.forEach(function(tooltipItem) {
                                    sum += tooltipItem.parsed.x;
                                });
                                return 'Total: ' + sum;
                            }
                        }
                    },
                    datalabels: {
                        display: false  // No mostrar labels individuales en barras apiladas
                    }
                },
                scales: {
                    x: {
                        stacked: true,
                        beginAtZero: true,
                        ticks: {
                            font: {
                                size: 11
                            },
                            stepSize: 5
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    y: {
                        stacked: true,
                        ticks: {
                            font: {
                                size: 10
                            }
                        },
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
        console.log('✅ Gráfico de RBS por municipios inicializado');
    }
    
    console.log('✅ Gráficos de RBS inicializados correctamente');
}

// ============================================
// CARGAR DATOS - MEJORADO CON PARALELIZACIÓN
// ============================================

async function cargarDatos() {
    console.log('🔄 Iniciando carga asíncrona progresiva...');
    tiempoUltimaActualizacion = new Date();
    
    // ⚡ OPTIMIZACIÓN: Cargar en paralelo las secciones menos pesadas
    // Las secciones de RBS se cargan al final para no bloquear el resto
    Promise.all([
        cargarMetricas(),
        cargarDatosMapa(),
        cargarDatosHistoricos(),
        cargarDatosDetalle(),
        cargarTiempoAfectacion(),
        cargarDatosUbicacion(),
        cargarHistoricoDepartamento(),
        cargarHistoricoCiudad()
    ]).then(() => {
        console.log('✅ Carga paralela completada, iniciando carga de RBS...');
        // Cargar RBS al final después de que todo lo demás esté listo
        cargarDatosRBS();
    });
}

// ============================================
// CARGAR MÉTRICAS
// ============================================

async function cargarMetricas() {
    try {
        console.log('📊 [1/7] Cargando métricas...');
        mostrarCargando('metricas');
        
        const response = await fetch('/api/hl5/metricas-debug');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        actualizarMetricas(data.metricas);
        ocultarCargando('metricas');
        
        console.log('✅ [1/7] Métricas cargadas');
    } catch (error) {
        console.error('❌ Error cargando métricas:', error);
        mostrarErrorSeccion('metricas', 'Error al cargar métricas');
    }
}

// ============================================
// CARGAR DATOS DEL MAPA
// ============================================

async function cargarDatosMapa() {
    try {
        console.log('🗺️ [2/7] Cargando datos del mapa...');
        mostrarCargando('mapa');
        
        const response = await fetch('/api/hl5/mapa-debug');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        actualizarMapa(data.datos);
        ocultarCargando('mapa');
        
        console.log(`✅ [2/7] Mapa cargado (${data.datos.length} registros)`);
    } catch (error) {
        console.error('❌ Error cargando mapa:', error);
        mostrarErrorSeccion('mapa', 'Error al cargar mapa');
    }
}

// ============================================
// CARGAR DATOS HISTÓRICOS
// ============================================

async function cargarDatosHistoricos() {
    try {
        console.log('📈 [3/7] Cargando datos históricos...');
        mostrarCargando('grafica');
        
        const response = await fetch('/api/hl5/historico-debug');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        actualizarGrafica(data.datos);
        ocultarCargando('grafica');
        
        console.log(`✅ [3/7] Gráfica histórica cargada (${data.datos.length} registros)`);
    } catch (error) {
        console.error('❌ Error cargando históricos:', error);
        mostrarErrorSeccion('grafica', 'Error al cargar gráfica');
    }
}

// ============================================
// CARGAR DATOS DE DETALLE
// ============================================

async function cargarDatosDetalle() {
    try {
        console.log('📋 [4/7] Cargando tabla de detalle...');
        mostrarCargando('tabla');
        
        const response = await fetch('/api/hl5/detalle-debug');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        actualizarTabla(data.datos);
        ocultarCargando('tabla');
        
        console.log(`✅ [4/7] Tabla cargada (${data.datos.length} registros)`);
    } catch (error) {
        console.error('❌ Error cargando detalle:', error);
        mostrarErrorSeccion('tabla', 'Error al cargar tabla');
    }
}

// ============================================
// CARGAR TIEMPO DE AFECTACIÓN
// ============================================

async function cargarTiempoAfectacion() {
    try {
        console.log('⏱️ [5/7] Cargando tiempo de afectación...');
        mostrarCargando('tiempo');
        
        const response = await fetch('/api/hl5/tiempo-afectacion');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        actualizarTiempoAfectacion(data.datos);
        ocultarCargando('tiempo');
        
        console.log('✅ [5/7] Tiempo de afectación cargado');
    } catch (error) {
        console.error('❌ Error cargando tiempo:', error);
        mostrarErrorSeccion('tiempo', 'Error al cargar tiempo');
    }
}

// ============================================
// CARGAR DATOS DE UBICACIÓN (HL5)
// ============================================

async function cargarDatosUbicacion() {
    try {
        console.log('📍 [6/7] Cargando gráficos de ubicación HL5...');
        mostrarCargando('ubicacion');
        
        const response = await fetch('/api/hl5/ubicacion');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        actualizarGraficosUbicacion(data.departamentos, data.ciudades);
        ocultarCargando('ubicacion');
        
        console.log(`✅ [6/7] Gráficos HL5 cargados (${data.departamentos.length} depts)`);
    } catch (error) {
        console.error('❌ Error cargando ubicación HL5:', error);
        mostrarErrorSeccion('ubicacion', 'Error al cargar gráficos HL5');
    }
}

// ============================================
// CARGAR DATOS DE RBS - OPTIMIZADO
// ============================================

async function cargarDatosRBS() {
    try {
        console.log('📡 [7/7] Cargando gráficos de RBS...');
        const inicio = performance.now();
        mostrarCargando('rbs');
        
        const response = await fetch('/api/hl5/rbs-ubicacion');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        actualizarGraficosRBS(data.departamentos, data.municipios);
        ocultarCargando('rbs');
        
        const tiempo = ((performance.now() - inicio) / 1000).toFixed(2);
        console.log(`✅ [7/7] Gráficos RBS cargados (${data.departamentos.length} depts) en ${tiempo}s`);
        console.log('🎉 Carga completa finalizada');
    } catch (error) {
        console.error('❌ Error cargando RBS:', error);
        mostrarErrorSeccion('rbs', 'Error al cargar gráficos RBS');
    }
}

// ============================================
// FUNCIONES DE INDICADORES DE CARGA
// ============================================

function mostrarCargando(seccion) {
    const elementos = {
        'metricas': '.metricas-section',
        'mapa': '#mapa-hl5',
        'grafica': '#chart-historico',
        'tabla': '.detalle-section',
        'tiempo': '.tiempo-afectacion-section',
        'ubicacion': '.graficos-ubicacion-section:first-of-type',
        'rbs': '.graficos-ubicacion-section:last-of-type'
    };
    
    const selector = elementos[seccion];
    if (!selector) return;
    
    const elemento = document.querySelector(selector);
    if (elemento && !elemento.classList.contains('cargando')) {
        elemento.classList.add('cargando');
        elemento.style.position = 'relative';
        elemento.style.minHeight = '100px';
        elemento.style.opacity = '0.6';
    }
}

function ocultarCargando(seccion) {
    const elementos = {
        'metricas': '.metricas-section',
        'mapa': '#mapa-hl5',
        'grafica': '#chart-historico',
        'tabla': '.detalle-section',
        'tiempo': '.tiempo-afectacion-section',
        'ubicacion': '.graficos-ubicacion-section:first-of-type',
        'rbs': '.graficos-ubicacion-section:last-of-type'
    };
    
    const selector = elementos[seccion];
    if (!selector) return;
    
    const elemento = document.querySelector(selector);
    if (elemento) {
        elemento.classList.remove('cargando');
        elemento.style.opacity = '1';
    }
}

function mostrarErrorSeccion(seccion, mensaje) {
    ocultarCargando(seccion);
    console.error(`❌ [${seccion}] ${mensaje}`);
}

// ============================================
// ACTUALIZAR MÉTRICAS
// ============================================

function actualizarMetricas(metricas) {
    console.log('📊 Actualizando métricas...', metricas);
    
    if (!metricas) {
        console.error('❌ No hay datos de métricas');
        return;
    }
    
    // Actualizar hora de última actualización (ya viene en GMT-5)
    const horaElement = document.getElementById('hora-actualizacion');
    if (horaElement) {
        horaElement.textContent = metricas.HORA_ULTIMA_ACTUALIZACION || '--';
    }
    
    // Actualizar contadores
    const hl5Element = document.getElementById('hl5-afectados');
    if (hl5Element) {
        hl5Element.textContent = metricas.HL5_AFECTADOS || 0;
    }
    
    const rbsElement = document.getElementById('total-rbs');
    if (rbsElement) {
        rbsElement.textContent = metricas.TOTAL_RBS || 0;
    }
    
    const g3Element = document.getElementById('total-3g');
    if (g3Element) {
        g3Element.textContent = metricas.TOTAL_3G || 0;
    }
    
    const g4Element = document.getElementById('total-4g');
    if (g4Element) {
        g4Element.textContent = metricas.TOTAL_4G || 0;
    }
    
    const b2bElement = document.getElementById('total-b2b');
    if (b2bElement) {
        b2bElement.textContent = metricas.TOTAL_B2B || 0;
    }
    
    console.log('✅ Métricas actualizadas');
}

// ============================================
// ACTUALIZAR TIEMPO DE AFECTACIÓN
// ============================================

function actualizarTiempoAfectacion(datos) {
    console.log('✅ Actualizando tiempo de afectación...', datos);
    
    if (!datos || !datos[0]) {
        console.error('❌ No hay datos de tiempo de afectación');
        return;
    }
    
    const data = datos[0];
    
    // Mapeo de campos acorde a los rangos exclusivos de la consulta
    const tiempos = [
        { id: 'tiempo-menor-4h', campo: 'menor_4h' },
        { id: 'tiempo-menor-8h', campo: 'menor_8h' },
        { id: 'tiempo-menor-24h', campo: 'menor_24h' },
        { id: 'tiempo-mayor-1d', campo: 'mayor_1d' },
        { id: 'tiempo-mayor-2d', campo: 'mayor_2d' },
        { id: 'tiempo-mayor-3d', campo: 'mayor_3d' },
        { id: 'tiempo-mayor-4d', campo: 'mayor_4d' },
        { id: 'tiempo-mayor-5d', campo: 'mayor_5d' },
        { id: 'tiempo-mayor-6d', campo: 'mayor_6d' },
        { id: 'tiempo-mayor-7d', campo: 'mayor_7d' },
        { id: 'tiempo-mayor-15d', campo: 'mayor_15d' }
    ];
    
    tiempos.forEach(tiempo => {
        const elemento = document.getElementById(tiempo.id);
        if (elemento) {
            const valor = Number(data[tiempo.campo]) || 0;
            elemento.textContent = valor;
            
            const card = elemento.closest('.tiempo-card');
            if (card) {
                card.classList.remove('verde', 'amarillo', 'naranja', 'rojo');
                
                if (valor > 30) {
                    card.classList.add('rojo');
                } else if (valor > 20) {
                    card.classList.add('naranja');
                } else if (valor > 10) {
                    card.classList.add('amarillo');
                } else {
                    card.classList.add('verde');
                }
                
                card.onclick = () => manejarClickTiempo(tiempo.campo);
            }
        }
    });
    
    console.log('✅ Tiempo de afectación actualizado');
}
// ============================================
// ACTUALIZAR MAPA
// ============================================

function actualizarMapa(datos) {
    console.log('🗺️ Actualizando mapa con', datos.length, 'registros');
    
    if (!markersLayer) {
        console.error('❌ markersLayer no inicializado');
        return;
    }
    
    // Limpiar marcadores existentes
    markersLayer.clearLayers();
    
    if (!datos || !datos.length) {
        console.warn('⚠️ No hay datos para mostrar en el mapa');
        return;
    }
    
    // Agrupar datos por ubicación (LATITUD + LONGITUD)
    const ubicacionesAgrupadas = {};
    
    datos.forEach(item => {
        if (item.LATITUD && item.LONGITUD) {
            const lat = parseFloat(item.LATITUD);
            const lng = parseFloat(item.LONGITUD);
            
            if (!isNaN(lat) && !isNaN(lng)) {
                // Crear clave única para la ubicación
                const claveUbicacion = `${lat.toFixed(4)}_${lng.toFixed(4)}`;
                
                if (!ubicacionesAgrupadas[claveUbicacion]) {
                    ubicacionesAgrupadas[claveUbicacion] = {
                        lat: lat,
                        lng: lng,
                        registros: []
                    };
                }
                
                ubicacionesAgrupadas[claveUbicacion].registros.push(item);
            }
        }
    });
    
    // Crear un marcador por cada ubicación única
    Object.values(ubicacionesAgrupadas).forEach(ubicacion => {
        const { lat, lng, registros } = ubicacion;
        
        // Crear marcador más pequeño (15x15 píxeles)
        const marker = L.marker([lat, lng], {
            icon: L.divIcon({
                className: 'custom-marker',
                html: `<div style="background-color: #e74c3c; color: white; 
                        border-radius: 50%; width: 15px; height: 15px; 
                        display: flex; align-items: center; justify-content: center; 
                        font-weight: bold; font-size: 10px; border: 2px solid white; 
                        box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
                       </div>`,
                iconSize: [15, 15]
            })
        });
        
        // Consolidar información de múltiples registros
        const tecnologias = new Set();
        const cinumRbs = new Set();
        let horaInicio = registros[0].HORA_INICIO;
        let cinum = registros[0].CINUM;
        let cinalidad = registros[0].CINALIDAD;
        let ciudad = registros[0].CIUDAD;
        
        // Recopilar todas las tecnologías y CINUM_RBS únicos
        registros.forEach(reg => {
            if (reg.TECNOLOGIA) {
                tecnologias.add(reg.TECNOLOGIA);
            }
            if (reg.CINUM_RBS) {
                cinumRbs.add(reg.CINUM_RBS);
            }
        });
        
        // Convertir sets a arrays y ordenar
        const tecnologiasArray = Array.from(tecnologias).sort();
        const cinumRbsArray = Array.from(cinumRbs).sort();
        
        // Crear contenido del popup con los campos especificados
        const popupContent = `
            <div style="min-width: 220px; font-family: Arial, sans-serif;">
                <div style="background-color: #2c3e50; color: white; padding: 8px; margin: -10px -10px 10px -10px; border-radius: 4px 4px 0 0;">
                    <h4 style="margin: 0; font-size: 14px;">HL5</h4>
                </div>
                <p style="margin: 5px 0; font-size: 12px;"><strong>HORA_INICIO:</strong> ${horaInicio || 'N/A'}</p>
                <p style="margin: 5px 0; font-size: 12px;"><strong>CINUM:</strong> ${cinum || 'N/A'}</p>
                <p style="margin: 5px 0; font-size: 12px;"><strong>CINUM_RBS:</strong> ${cinumRbsArray.join(', ') || 'N/A'}</p>
                <p style="margin: 5px 0; font-size: 12px;"><strong>TECNOLOGIA:</strong> ${tecnologiasArray.join(', ') || 'N/A'}</p>
                <p style="margin: 5px 0; font-size: 12px;"><strong>CINALIDAD:</strong> ${cinalidad || 'N/A'}</p>
                <p style="margin: 5px 0; font-size: 12px;"><strong>CIUDAD:</strong> ${ciudad || 'N/A'}</p>
                <p style="margin: 5px 0; font-size: 12px;"><strong>LATITUD:</strong> ${lat.toFixed(4)}</p>
                <p style="margin: 5px 0; font-size: 12px;"><strong>LONGITUD:</strong> ${lng.toFixed(4)}</p>
                ${registros.length > 1 ? `<p style="margin: 8px 0 0 0; font-size: 11px; color: #7f8c8d; font-style: italic;">* ${registros.length} registros en esta ubicación</p>` : ''}
            </div>
        `;
        
        marker.bindPopup(popupContent);
        marker.addTo(markersLayer);
    });
    
    console.log(`✅ Mapa actualizado con ${markersLayer.getLayers().length} marcadores (de ${datos.length} registros)`);
}

// ============================================
// ACTUALIZAR GRÁFICA
// ============================================

function actualizarGrafica(datos) {
    console.log('📈 Actualizando gráfica con', datos.length, 'registros históricos');
    
    if (!datos || !datos.length) {
        console.warn('⚠️ No hay datos históricos');
        return;
    }
    
    // Guardar datos completos para futuras actualizaciones
    datosHistoricoCompletos = datos;
    
    // Filtrar datos según las horas seleccionadas
    const ahora = new Date();
    const limiteTiempo = new Date(ahora.getTime() - (horasFiltro * 60 * 60 * 1000));
    
    const datosFiltrados = datos.filter(row => {
        try {
            const fecha = new Date(row.HORA_LECTURA);
            return fecha >= limiteTiempo;
        } catch (e) {
            return true;
        }
    }).sort((a, b) => new Date(a.HORA_LECTURA) - new Date(b.HORA_LECTURA));
    
    console.log(`📊 Mostrando ${datosFiltrados.length} registros de las últimas ${horasFiltro} horas`);
    
    // Formatear labels (DD/MM HH:MM en GMT-5)
    const labels = datosFiltrados.map(row => {
        const fecha = new Date(row.HORA_LECTURA);
        const dia = String(fecha.getDate()).padStart(2, '0');
        const mes = String(fecha.getMonth() + 1).padStart(2, '0');
        const hora = String(fecha.getHours()).padStart(2, '0');
        const minuto = String(fecha.getMinutes()).padStart(2, '0');
        return `${dia}/${mes} ${hora}:${minuto}`;
    });
    
    const dataHL5 = datosFiltrados.map(row => row.HL5 || 0);
    const data3G = datosFiltrados.map(row => row['3G'] || 0);
    const data4G = datosFiltrados.map(row => row['4G'] || 0);
    const dataTotalRBS = datosFiltrados.map(row => row.TOTAL_RBS || 0);
    
    // Actualizar datos de la gráfica
    chartHistorico.data.labels = labels;
    chartHistorico.data.datasets[0].data = dataHL5;
    chartHistorico.data.datasets[1].data = data3G;
    chartHistorico.data.datasets[2].data = data4G;
    chartHistorico.data.datasets[3].data = dataTotalRBS;
    
    // Re-renderizar sin animación
    chartHistorico.update('none');
    
    console.log('✅ Gráfica actualizada');
}

// ============================================
// ACTUALIZAR TABLA
// ============================================

function actualizarTabla(datos) {
    console.log('📋 Actualizando tabla con', datos.length, 'registros');
    datosDetalle = Array.isArray(datos) ? datos : [];
    renderizarTablaFiltrada();
}

function renderizarTablaFiltrada() {
    const tbody = document.getElementById('tbody-hl5');
    if (!tbody) {
        console.error('❌ No se encontró el elemento tbody-hl5');
        return;
    }

    const datosFiltrados = aplicarFiltrosDetalle();

    if (!datosFiltrados.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="13" style="text-align: center; padding: 20px; color: #999;">
                    Sin resultados con los filtros aplicados
                </td>
            </tr>
        `;
        return;
    }

    let html = '';
    datosFiltrados.forEach(row => {
        const esCexp = row.CEXP && row.CEXP.toString().trim() !== '';
        const rowStyle = esCexp ? ' style="background-color: #d6eaf8;"' : '';
        html += `
            <tr${rowStyle}>
                <td>${row.HORA_INICIO || ''}</td>
                <td>${row.NODE || ''}</td>
                <td>${row.CINUM || ''}</td>
                <td>${row.CINAME || ''}</td>
                <td>${row.CIUDAD || ''}</td>
                <td>${row.DEPARTAMENTO || ''}</td>
                <td style="text-align: center;">${row['3G'] || 0}</td>
                <td style="text-align: center;">${row['4G'] || 0}</td>
                <td style="text-align: center;">${row.TOTAL_RB || 0}</td>
                <td style="text-align: center;">${row.B2B || 0}</td>
                <td>${row.INC_HL5 || ''}</td>
                <td>${row.INC_MOVIL || ''}</td>
                <td style="text-align: center;">${row.CEXP || ''}</td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
    console.log('✅ Tabla actualizada con', datosFiltrados.length, 'filas (filtrado)');
}

function aplicarFiltrosDetalle() {
    if (!datosDetalle || !datosDetalle.length) {
        return [];
    }

    return datosDetalle.filter(row => {
        return columnasDetalle.every(col => {
            // Si no hay filtro para esta columna, pasar
            if (!filtrosActivos[col] || filtrosActivos[col].length === 0) {
                return true;
            }
            
            // Obtener valor de la fila
            const valor = normalizarValorFiltro(row[col]);
            
            // Verificar si el valor está en los seleccionados
            return filtrosActivos[col].includes(valor);
        });
    });
}

function normalizarValorFiltro(valor) {
    if (valor === null || valor === undefined) {
        return '';
    }
    return String(valor);
}

// ============================================
// MOSTRAR ERROR
// ============================================

function mostrarError(mensaje) {
    console.error('❌', mensaje);
    
    // Crear elemento de notificación
    const notificacion = document.createElement('div');
    notificacion.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        background: #e74c3c;
        color: white;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        z-index: 10000;
        font-size: 14px;
        max-width: 400px;
    `;
    notificacion.innerHTML = `
        <strong>Error:</strong> ${mensaje}<br>
        <small>Revisa la consola (F12) para más detalles</small>
    `;
    
    document.body.appendChild(notificacion);
    
    // Remover después de 10 segundos
    setTimeout(() => {
        notificacion.remove();
    }, 10000);
}

// ============================================
// ACTUALIZAR GRÁFICOS DE UBICACIÓN
// ============================================

function actualizarGraficosUbicacion(departamentos, ciudades) {
    console.log('📊 Actualizando gráficos de ubicación...');
    
    if (!departamentos || !ciudades) {
        console.warn('⚠️ No hay datos de ubicación');
        return;
    }
    
    // Actualizar gráfico de departamentos
    if (chartDepartamentos && departamentos.length > 0) {
        const labelsDep = departamentos.map(d => d.DEPARTAMENTO);
        const datasDep = departamentos.map(d => d.HL5);
        
        chartDepartamentos.data.labels = labelsDep;
        chartDepartamentos.data.datasets[0].data = datasDep;
        chartDepartamentos.update('none'); // Sin animación
        
        console.log(`✅ Gráfico de departamentos actualizado con ${departamentos.length} departamentos`);
    }
    
    // Actualizar gráfico de ciudades (Top 10)
    if (chartCiudades && ciudades.length > 0) {
        const labelsCiu = ciudades.map(c => c.MUNICIPIO);
        const datasCiu = ciudades.map(c => c.HL5);
        
        chartCiudades.data.labels = labelsCiu;
        chartCiudades.data.datasets[0].data = datasCiu;
        chartCiudades.update('none'); // Sin animación
        
        console.log(`✅ Gráfico de ciudades actualizado con ${ciudades.length} ciudades`);
    }
    
    console.log('✅ Gráficos de ubicación actualizados');
}

// ============================================
// ACTUALIZAR GRÁFICOS DE RBS - OPTIMIZADO
// ============================================

function actualizarGraficosRBS(departamentos, municipios) {
    console.log('?? Actualizando graficos de RBS (v2)...');

    if ((!departamentos || !departamentos.length) && (!municipios || !municipios.length)) {
        console.warn('?? No hay datos de RBS para graficar');
        return;
    }

    if (chartRBSDepartamentos && departamentos && departamentos.length > 0) {
        const labelsDep = departamentos.map(d => d.DEPARTAMENTO);
        const data3G = departamentos.map(d => Number(d['3G']) || 0);
        const data4G = departamentos.map(d => Number(d['4G']) || 0);
        chartRBSDepartamentos.data.labels = labelsDep;
        chartRBSDepartamentos.data.datasets[0].data = data3G;
        chartRBSDepartamentos.data.datasets[1].data = data4G;
        chartRBSDepartamentos.update('none');
        console.log(`? Grafico de RBS por departamentos actualizado con ${departamentos.length} departamentos`);
    }

    if (chartRBSMunicipios && municipios && municipios.length > 0) {
        const top10 = municipios.slice(0, 10);
        const labelsMun = top10.map(m => m.MUNICIPIO);
        const data3G = top10.map(m => Number(m['3G']) || 0);
        const data4G = top10.map(m => Number(m['4G']) || 0);
        chartRBSMunicipios.data.labels = labelsMun;
        chartRBSMunicipios.data.datasets[0].data = data3G;
        chartRBSMunicipios.data.datasets[1].data = data4G;
        chartRBSMunicipios.update('none');
        console.log(`? Grafico de RBS por municipios actualizado con ${top10.length} municipios`);
    }

    console.log('? Graficos de RBS actualizados');
}
// Log de inicio
console.log('✅ Módulo Monitoreo HL5 cargado (v2.0 - Auto-recarga 10 min, optimizado)');

// ============================================
// HISTÓRICO AFECTACIÓN HL5 POR DEPARTAMENTO
// ============================================

/**
 * Registra los event listeners para los botones de tiempo y el
 * selector de departamento de la sección de histórico por departamento.
 * Se llama una sola vez desde DOMContentLoaded.
 */
function inicializarFiltrosGraficaDepto() {
    console.log('🔘 Inicializando filtros gráfica departamento...');

    // Botones 12h / 24h (usan data-horas-depto para no colisionar con los botones del histórico principal)
    document.querySelectorAll('.filter-btn[data-horas-depto]').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.filter-btn[data-horas-depto]').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            horasHistoricoDepto = parseInt(this.dataset.horasDepto, 10);
            cargarHistoricoDepartamento();
        });
    });

    // Selector de departamento
    const select = document.getElementById('select-departamento');
    if (select) {
        select.addEventListener('change', function () {
            departamentoSeleccionado = this.value;
            cargarHistoricoDepartamento();
        });
    }

    console.log('✅ Filtros gráfica departamento inicializados');
}

/**
 * Llama al endpoint y actualiza la gráfica + el selector.
 */
async function cargarHistoricoDepartamento() {
    const loading = document.getElementById('historico-depto-loading');
    try {
        if (loading) loading.classList.remove('hidden');

        let url = `/api/hl5/historico-departamento-debug?horas=${horasHistoricoDepto}`;
        if (departamentoSeleccionado) {
            url += `&departamento=${encodeURIComponent(departamentoSeleccionado)}`;
        }

        console.log(`📊 [HistDepto] Cargando: ${url}`);

        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        if (!data.success) {
            console.error('[HistDepto] Error en API:', data.error);
            return;
        }

        // Poblar selector solo la primera vez (o cuando cambian las horas)
        if (data.departamentos && data.departamentos.length > 0) {
            poblarSelectorDepartamento(data.departamentos);
        }

        renderHistoricoDepto(data.datos);
        console.log(`✅ [HistDepto] Renderizado con ${data.datos.length} registros`);

    } catch (error) {
        console.error('❌ Error cargando histórico departamento:', error);
    } finally {
        if (loading) loading.classList.add('hidden');
    }
}

/**
 * Rellena el <select> con la lista de departamentos recibida de la API.
 * Conserva el valor actualmente seleccionado si sigue existiendo.
 */
function poblarSelectorDepartamento(departamentos) {
    const select = document.getElementById('select-departamento');
    if (!select) return;

    const valorActual = select.value;

    // Limpiar opciones dinámicas (dejar solo "Todos los Departamentos")
    while (select.options.length > 1) select.remove(1);

    departamentos.forEach(depto => {
        const opt = document.createElement('option');
        opt.value = depto;
        opt.textContent = depto;
        if (depto === valorActual) opt.selected = true;
        select.appendChild(opt);
    });
}

/**
 * Construye / actualiza el Chart.js de histórico por departamento.
 * - Sin departamento seleccionado → una línea por cada departamento.
 * - Con departamento seleccionado → una sola línea.
 */
function renderHistoricoDepto(datos) {
    const canvas = document.getElementById('chart-historico-depto');
    if (!canvas) return;

    // Destruir instancia previa para evitar memory leaks
    if (chartHistoricoDepto) {
        chartHistoricoDepto.destroy();
        chartHistoricoDepto = null;
    }

    if (!datos || datos.length === 0) {
        // Renderizar vacío con mensaje
        chartHistoricoDepto = new Chart(canvas, {
            type: 'line',
            data: { labels: ['Sin datos en el rango seleccionado'], datasets: [] },
            options: {
                plugins: {
                    legend: { display: false },
                    datalabels: { display: false }
                }
            }
        });
        return;
    }

    let labels, datasets;

    if (departamentoSeleccionado) {
        // ── Un solo departamento ─────────────────────────────────
        labels   = datos.map(d => formatHoraDepto(d.HORA_LECTURA));
        datasets = [{
            label: departamentoSeleccionado,
            data: datos.map(d => d.HL5 || 0),
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,0.08)',
            tension: 0.35,
            fill: true,
            pointRadius: 3,
            pointHoverRadius: 6,
            borderWidth: 2
        }];

    } else {
        // ── Todos los departamentos (multi-línea) ────────────────
        // Pivotar: obtener horas únicas y departamentos únicos
        const horasUnicas = [...new Set(datos.map(d => d.HORA_LECTURA))].sort();
        const deptos      = [...new Set(datos.map(d => d.DEPARTAMENTO))].sort();

        labels = horasUnicas.map(h => formatHoraDepto(h));

        // Mapa rápido "hora||depto" → HL5 para O(1) de lookup
        const mapa = {};
        datos.forEach(d => {
            mapa[`${d.HORA_LECTURA}||${d.DEPARTAMENTO}`] = d.HL5 || 0;
        });

        datasets = deptos.map((depto, i) => {
            const color = COLORES_DEPTO[i % COLORES_DEPTO.length];
            return {
                label: depto,
                data: horasUnicas.map(h => mapa[`${h}||${depto}`] ?? 0),
                borderColor: color,
                backgroundColor: 'transparent',
                tension: 0.3,
                fill: false,
                pointRadius: 2,
                pointHoverRadius: 5,
                borderWidth: 2
            };
        });
    }

    chartHistoricoDepto = new Chart(canvas, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: 'nearest', intersect: true },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#555',
                        font: { size: 11 },
                        usePointStyle: true,
                        pointStyleWidth: 10,
                        padding: 14,
                        // Si hay demasiados departamentos, mostrar solo los primeros 10 en leyenda
                        filter: (item) => {
                            if (!departamentoSeleccionado && datasets.length > 10) {
                                return item.datasetIndex < 10;
                            }
                            return true;
                        }
                    }
                },
                datalabels: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderWidth: 1,
                    padding: 10,
                    displayColors: true,
                    callbacks: {
                        label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y} HL5`
                    }
                }
            },
            scales: {
                x: {
                    ticks: {
                        color: '#666',
                        maxTicksLimit: horasHistoricoDepto === 12 ? 12 : 16,
                        font: { size: 10 },
                        maxRotation: 45,
                        minRotation: 45
                    },
                    grid: { color: 'rgba(0,0,0,0.05)' }
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: '#666',
                        font: { size: 11 },
                        precision: 0
                    },
                    grid: { color: 'rgba(0,0,0,0.05)' },
                    title: {
                        display: true,
                        text: 'HL5 Afectados',
                        color: '#888',
                        font: { size: 11 }
                    }
                }
            }
        }
    });
}

/**
 * Convierte un timestamp 'YYYY-MM-DD HH:MM:SS' a 'DD/MM HH:MM'
 * igual que el formato del histórico principal.
 */
function formatHoraDepto(ts) {
    if (!ts) return '';
    // Reemplazar espacio por T para compatibilidad con Safari
    const d = new Date(ts.replace(' ', 'T'));
    const dia    = String(d.getDate()).padStart(2, '0');
    const mes    = String(d.getMonth() + 1).padStart(2, '0');
    const hora   = String(d.getHours()).padStart(2, '0');
    const minuto = String(d.getMinutes()).padStart(2, '0');
    return `${dia}/${mes} ${hora}:${minuto}`;
}
// ============================================
// HISTÓRICO AFECTACIÓN HL5 POR CIUDAD
// ============================================

/**
 * Registra los event listeners de la sección histórico por ciudad.
 */
function inicializarFiltrosGraficaCiudad() {
    console.log('🔘 Inicializando filtros gráfica ciudad...');

    document.querySelectorAll('.filter-btn[data-horas-ciudad]').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.filter-btn[data-horas-ciudad]').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            horasHistoricoCiudad = parseInt(this.dataset.horasCiudad, 10);
            cargarHistoricoCiudad();
        });
    });

    const select = document.getElementById('select-ciudad');
    if (select) {
        select.addEventListener('change', function () {
            ciudadSeleccionada = this.value;
            cargarHistoricoCiudad();
        });
    }

    console.log('✅ Filtros gráfica ciudad inicializados');
}

/**
 * Fetch al endpoint de histórico por ciudad y actualiza la gráfica.
 */
async function cargarHistoricoCiudad() {
    const loading = document.getElementById('historico-ciudad-loading');
    try {
        if (loading) loading.classList.remove('hidden');

        let url = `/api/hl5/historico-ciudad-debug?horas=${horasHistoricoCiudad}`;
        if (ciudadSeleccionada) {
            url += `&ciudad=${encodeURIComponent(ciudadSeleccionada)}`;
        }

        console.log(`🏙️ [HistCiudad] Cargando: ${url}`);

        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        if (!data.success) {
            console.error('[HistCiudad] Error en API:', data.error);
            return;
        }

        if (data.ciudades && data.ciudades.length > 0) {
            poblarSelectorCiudad(data.ciudades);
        }

        renderHistoricoCiudad(data.datos);
        console.log(`✅ [HistCiudad] Renderizado con ${data.datos.length} registros`);

    } catch (error) {
        console.error('❌ Error cargando histórico ciudad:', error);
    } finally {
        if (loading) loading.classList.add('hidden');
    }
}

/**
 * Rellena el <select> de ciudades conservando el valor actual.
 */
function poblarSelectorCiudad(ciudades) {
    const select = document.getElementById('select-ciudad');
    if (!select) return;

    const valorActual = select.value;

    while (select.options.length > 1) select.remove(1);

    ciudades.forEach(ciudad => {
        const opt = document.createElement('option');
        opt.value = ciudad;
        opt.textContent = ciudad;
        if (ciudad === valorActual) opt.selected = true;
        select.appendChild(opt);
    });
}

/**
 * Construye / actualiza el Chart.js de histórico por ciudad.
 * - Sin ciudad seleccionada → una línea por cada ciudad (Top 15 por volumen).
 * - Con ciudad seleccionada → una sola línea.
 */
function renderHistoricoCiudad(datos) {
    const canvas = document.getElementById('chart-historico-ciudad');
    if (!canvas) return;

    if (chartHistoricoCiudad) {
        chartHistoricoCiudad.destroy();
        chartHistoricoCiudad = null;
    }

    if (!datos || datos.length === 0) {
        chartHistoricoCiudad = new Chart(canvas, {
            type: 'line',
            data: { labels: ['Sin datos en el rango seleccionado'], datasets: [] },
            options: {
                plugins: {
                    legend: { display: false },
                    datalabels: { display: false }
                }
            }
        });
        return;
    }

    let labels, datasets;

    if (ciudadSeleccionada) {
        // ── Una sola ciudad ──────────────────────────────────────
        labels   = datos.map(d => formatHoraDepto(d.HORA_LECTURA));
        datasets = [{
            label: ciudadSeleccionada,
            data: datos.map(d => d.HL5 || 0),
            borderColor: '#e74c3c',
            backgroundColor: 'rgba(231, 76, 60, 0.08)',
            tension: 0.35,
            fill: true,
            pointRadius: 3,
            pointHoverRadius: 6,
            borderWidth: 2
        }];

    } else {
        // ── Todas las ciudades (multi-línea) ─────────────────────
        const horasUnicas = [...new Set(datos.map(d => d.HORA_LECTURA))].sort();
        const ciudades    = [...new Set(datos.map(d => d.CIUDAD))].sort();

        labels = horasUnicas.map(h => formatHoraDepto(h));

        // Calcular volumen total por ciudad para ordenar y elegir las top 15
        const volumenPorCiudad = {};
        datos.forEach(d => {
            volumenPorCiudad[d.CIUDAD] = (volumenPorCiudad[d.CIUDAD] || 0) + (d.HL5 || 0);
        });
        const ciudadesOrdenadas = ciudades
            .sort((a, b) => (volumenPorCiudad[b] || 0) - (volumenPorCiudad[a] || 0))
            .slice(0, 15); // Mostrar hasta 15 ciudades para no saturar

        // Mapa rápido "hora||ciudad" → HL5
        const mapa = {};
        datos.forEach(d => {
            mapa[`${d.HORA_LECTURA}||${d.CIUDAD}`] = d.HL5 || 0;
        });

        datasets = ciudadesOrdenadas.map((ciudad, i) => {
            const color = COLORES_DEPTO[i % COLORES_DEPTO.length];
            return {
                label: ciudad,
                data: horasUnicas.map(h => mapa[`${h}||${ciudad}`] ?? 0),
                borderColor: color,
                backgroundColor: 'transparent',
                tension: 0.3,
                fill: false,
                pointRadius: 2,
                pointHoverRadius: 5,
                borderWidth: 2
            };
        });
    }

    chartHistoricoCiudad = new Chart(canvas, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: 'nearest', intersect: true },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#555',
                        font: { size: 11 },
                        usePointStyle: true,
                        pointStyleWidth: 10,
                        padding: 14,
                        filter: (item) => {
                            // En modo "todas", limitar leyenda visible a 10
                            if (!ciudadSeleccionada && datasets.length > 10) {
                                return item.datasetIndex < 10;
                            }
                            return true;
                        }
                    }
                },
                datalabels: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderWidth: 1,
                    padding: 10,
                    displayColors: true,
                    callbacks: {
                        label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y} HL5`
                    }
                }
            },
            scales: {
                x: {
                    ticks: {
                        color: '#666',
                        maxTicksLimit: horasHistoricoCiudad === 12 ? 12 : 16,
                        font: { size: 10 },
                        maxRotation: 45,
                        minRotation: 45
                    },
                    grid: { color: 'rgba(0,0,0,0.05)' }
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: '#666',
                        font: { size: 11 },
                        precision: 0
                    },
                    grid: { color: 'rgba(0,0,0,0.05)' },
                    title: {
                        display: true,
                        text: 'HL5 Afectados',
                        color: '#888',
                        font: { size: 11 }
                    }
                }
            }
        }
    });
}