/**
 * ============================================
 * APERTURAS ANILLOS HL5 - JavaScript CORREGIDO
 * ============================================
 * Versión con manejo de errores mejorado
 */

// Variables globales
let datosGlobales = [];
let filtroActual = 'TODOS';
let datosFiltroPrincipal = [];
let datosTablaActual = [];
let mapaUnificado;
let layerCabeceras, layerAnillos, layerHL5Afectados;
let capasCabeceras = true;
let capasAnillos = true;
let capasHL5Afectados = true;
let aperturaSeleccionada = null;
const columnasDetalle = [
    'HORA_INICIO',
    'TIPO_APERTURA',
    'ANILLO',
    'NODO_A',
    'IP_A',
    'NODO_A_STATUS',
    'NODO_B',
    'IP_B',
    'NODO_B_STATUS',
    'HORAS',
    'AFECTA',
    'OT',
    'GRUPO_OT',
    'AVANCE'
];
const filtrosActivos = {};
let columnaFiltroActual = null;
let valoresFiltroActual = [];
const normalizarValor = (v) => (v === null || v === undefined ? 'N/A' : String(v));

/**
 * Inicializar mapa unificado de Leaflet
 */
function inicializarMapas() {
    try {
        console.log('🗺️ Inicializando mapa...');
        
        // Verificar si el elemento del mapa existe
        const mapaElement = document.getElementById('mapaUnificado');
        if (!mapaElement) {
            console.error('❌ Elemento #mapaUnificado no encontrado');
            return false;
        }
        
        // Crear mapa unificado
        mapaUnificado = L.map('mapaUnificado').setView([4.5709, -74.2973], 6);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(mapaUnificado);

        // Crear layer groups para cabeceras, anillos y HL5 afectados
        layerCabeceras = L.layerGroup().addTo(mapaUnificado);
        layerAnillos = L.layerGroup().addTo(mapaUnificado);
        layerHL5Afectados = L.layerGroup().addTo(mapaUnificado);
        
        console.log('✅ Mapa inicializado correctamente');
        return true;
    } catch (error) {
        console.error('❌ Error inicializando mapa:', error);
        return false;
    }
}

/**
 * Toggle visibilidad de capas
 */
function toggleCapa(tipo) {
    if (tipo === 'cabeceras') {
        capasCabeceras = !capasCabeceras;
        const btn = document.getElementById('toggleCabeceras');
        
        if (capasCabeceras) {
            mapaUnificado.addLayer(layerCabeceras);
            btn.classList.add('active');
        } else {
            mapaUnificado.removeLayer(layerCabeceras);
            btn.classList.remove('active');
        }
    } else if (tipo === 'anillos') {
        capasAnillos = !capasAnillos;
        const btn = document.getElementById('toggleAnillos');
        
        if (capasAnillos) {
            mapaUnificado.addLayer(layerAnillos);
            btn.classList.add('active');
        } else {
            mapaUnificado.removeLayer(layerAnillos);
            btn.classList.remove('active');
        }
    } else if (tipo === 'hl5_afectados') {
        capasHL5Afectados = !capasHL5Afectados;
        const btn = document.getElementById('toggleHL5Afectados');
        
        if (capasHL5Afectados) {
            mapaUnificado.addLayer(layerHL5Afectados);
            btn.classList.add('active');
        } else {
            mapaUnificado.removeLayer(layerHL5Afectados);
            btn.classList.remove('active');
        }
    }
}

/**
 * Cargar datos desde las APIs - VERSION CORREGIDA
 */
async function cargarDatos() {
    console.log('🔄 Iniciando carga de datos...');
    
    try {
        // Cargar aperturas de anillos y cabeceras
        console.log('📡 Fetching /api/hl5/aperturas-anillos...');
        const response = await fetch('/api/hl5/aperturas-anillos');
        const data = await response.json();
        
        console.log('📦 Datos recibidos:', data);
        
        if (data.success) {
            console.log(`✅ ${data.total} aperturas recibidas`);
            datosGlobales = data.aperturas;
            
            // Actualizar métricas con manejo de errores
            try {
                console.log('📊 Actualizando métricas...');
                actualizarMetricas(datosGlobales);
                console.log('✅ Métricas actualizadas');
            } catch (error) {
                console.error('❌ Error actualizando métricas:', error);
                // Continuar aunque fallen las métricas
            }
            
            // Pintar mapa con manejo de errores
            try {
                console.log('🗺️ Pintando mapa...');
                pintarMapaUnificado(datosGlobales);
                console.log('✅ Mapa pintado');
            } catch (error) {
                console.error('❌ Error pintando mapa:', error);
                // Continuar aunque falle el mapa
            }
            
            // Preparar datos para la tabla
            datosFiltroPrincipal = [...datosGlobales];
            datosTablaActual = [...datosFiltroPrincipal];
            
            // Renderizar tabla
            console.log('📋 Renderizando tabla...');
            renderizarTablaFiltrada();
            console.log('✅ Tabla renderizada');
            
        } else {
            console.error('❌ Error en respuesta:', data.error);
            mostrarError('No se pudieron cargar las aperturas: ' + data.error);
        }

        // Cargar HL5 afectados con brazos - independiente de la tabla
        try {
            console.log('🔄 Cargando HL5 afectados...');
            await cargarHL5Afectados();
        } catch (error) {
            console.error('❌ Error cargando HL5 afectados:', error);
        }

        // Cargar panel de anillos afectados
        try {
            console.log('🔴 Cargando panel anillos...');
            await cargarPanelAnillos();
        } catch (error) {
            console.error('❌ Error cargando panel anillos:', error);
        }
        
    } catch (error) {
        console.error('❌ Error general cargando datos:', error);
        mostrarError('Error al cargar los datos: ' + error.message);
    }
}

/**
 * Cargar HL5 afectados con sus brazos alarmados
 */
async function cargarHL5Afectados() {
    try {
        console.log('📡 Fetching /api/hl5/afectados-con-brazos...');
        const response = await fetch('/api/hl5/afectados-con-brazos');
        const data = await response.json();
        
        console.log('📦 HL5 afectados recibidos:', data);
        
        if (data.success) {
            console.log(`✅ ${data.total} HL5 afectados recibidos`);
            pintarHL5Afectados(data.hl5_afectados);
            
            const contador = document.getElementById('contadorHL5Afectados');
            if (contador) {
                contador.textContent = `${data.total} equipos`;
            }
        } else {
            console.error('❌ Error cargando HL5 afectados:', data.error);
        }
    } catch (error) {
        console.error('❌ Error en cargarHL5Afectados:', error);
    }
}

/**
 * Pintar HL5 afectados en el mapa como triangulos
 */
function pintarHL5Afectados(hl5Afectados) {
    if (!layerHL5Afectados) {
        console.warn('⚠️ Layer HL5 afectados no inicializado');
        return;
    }
    
    // Limpiar layer
    layerHL5Afectados.clearLayers();

    hl5Afectados.forEach(hl5 => {
        const latAlarmado = hl5.latitud;
        const lonAlarmado = hl5.longitud;

        if (!latAlarmado || !lonAlarmado) {
            console.warn(`⚠️ HL5 ${hl5.cinum} sin coordenadas, saltando...`);
            return;
        }

        // Color según tiempo de afectación
        let colorAlarmado = '#dc3545'; // Rojo intenso por defecto
        if (hl5.horas < 4) {
            colorAlarmado = '#ff6b6b'; // Rojo claro
        } else if (hl5.horas >= 24) {
            colorAlarmado = '#8b0000'; // Rojo muy oscuro
        }

        // Marcador TRIANGULAR del nodo alarmado
        const iconoAlarmado = L.divIcon({
            className: 'custom-marker-triangle-hl5-afectado',
            html: `<div style="
                width: 0;
                height: 0;
                border-left: 10px solid transparent;
                border-right: 10px solid transparent;
                border-bottom: 18px solid ${colorAlarmado};
                filter: drop-shadow(0 0 6px rgba(220, 53, 69, 0.8));
                position: relative;
            ">
                <div style="
                    position: absolute;
                    width: 0;
                    height: 0;
                    border-left: 8px solid transparent;
                    border-right: 8px solid transparent;
                    border-bottom: 14px solid white;
                    top: 2px;
                    left: -8px;
                "></div>
                <div style="
                    position: absolute;
                    width: 0;
                    height: 0;
                    border-left: 7px solid transparent;
                    border-right: 7px solid transparent;
                    border-bottom: 12px solid ${colorAlarmado};
                    top: 3px;
                    left: -7px;
                "></div>
            </div>`,
            iconSize: [20, 18],
            iconAnchor: [10, 18]
        });

        L.marker([latAlarmado, lonAlarmado], {icon: iconoAlarmado})
            .bindPopup(crearPopupHL5Afectado(hl5), {
                maxWidth: 400,
                minWidth: 300,
                maxHeight: 500
            })
            .addTo(layerHL5Afectados);
    });
}

/**
 * Crear popup para nodo HL5 alarmado
 */
function crearPopupHL5Afectado(hl5) {
    const numBrazos = hl5.brazos ? hl5.brazos.length : 0;
    const tieneBrazos = numBrazos > 0;
    
    const cinumCiname = `${hl5.cinum || 'N/A'} - ${hl5.ciname || 'N/A'}`;
    
    // HTML de los brazos
    let brazosHTML = '';
    if (tieneBrazos) {
        brazosHTML = hl5.brazos.map((brazo, idx) => {
            // Determinar si el brazo tiene afectación (alguno de los dos nodos está DOWN)
            const brazoAfectado = brazo.origen_status === 'DOWN' || brazo.destino_status === 'DOWN';
            const claseBrazo = brazoAfectado ? 'popup-brazo brazo-down' : 'popup-brazo';
            
            // Crear HTML para el origen con OT si está DOWN
            let origenHTML = `
                <div class="popup-brazo-nodo">
                    <span class="popup-label">Origen:</span>
                    <span class="popup-value">${brazo.origen || 'N/A'}</span>
                    <span class="popup-label">Descripción:</span>
                    <span class="popup-value">${brazo.origen_description || 'N/A'}</span>
                    <span class="popup-label">Sitio:</span>
                    <span class="popup-value">${brazo.origen_sitio || 'N/A'}</span>
                    <span class="popup-label">IP:Puerto:</span>
                    <span class="popup-value">${brazo.ip_origen || 'N/A'}:${brazo.puerto_origen || 'N/A'}</span>
                    <span class="popup-label">Estado:</span>
                    <span class="popup-badge popup-badge-${brazo.origen_status?.toLowerCase() || 'unknown'}">${brazo.origen_status || 'N/A'}</span>`;
            
            // Si está DOWN, agregar la OT
            if (brazo.origen_status === 'DOWN' && brazo.origen_ot) {
                origenHTML += `
                    <span class="popup-label">OT:</span>
                    <span class="popup-value" style="color: #dc3545; font-weight: 600;">${brazo.origen_ot}</span>`;
            }
            
            origenHTML += `</div>`;
            
            // Crear HTML para el destino con OT si está DOWN
            let destinoHTML = `
                <div class="popup-brazo-nodo">
                    <span class="popup-label">Destino:</span>
                    <span class="popup-value">${brazo.destino || 'N/A'}</span>
                    <span class="popup-label">Descripción:</span>
                    <span class="popup-value">${brazo.destino_description || 'N/A'}</span>
                    <span class="popup-label">Sitio:</span>
                    <span class="popup-value">${brazo.destino_sitio || 'N/A'}</span>
                    <span class="popup-label">IP:Puerto:</span>
                    <span class="popup-value">${brazo.ip_destino || 'N/A'}:${brazo.puerto_destino || 'N/A'}</span>
                    <span class="popup-label">Estado:</span>
                    <span class="popup-badge popup-badge-${brazo.destino_status?.toLowerCase() || 'unknown'}">${brazo.destino_status || 'N/A'}</span>`;
            
            // Si está DOWN, agregar la OT
            if (brazo.destino_status === 'DOWN' && brazo.destino_ot) {
                destinoHTML += `
                    <span class="popup-label">OT:</span>
                    <span class="popup-value" style="color: #dc3545; font-weight: 600;">${brazo.destino_ot}</span>`;
            }
            
            destinoHTML += `</div>`;
            
            return `
                <div class="${claseBrazo}">
                    <div class="popup-brazo-header">
                        <strong>🔗 Brazo ${idx + 1}</strong>
                        ${brazoAfectado ? ' <span style="color: #ffeb3b;">⚠️ AFECTADO</span>' : ''}
                    </div>
                    <div class="popup-brazo-body">
                        ${origenHTML}
                        <div class="popup-brazo-arrow">↓</div>
                        ${destinoHTML}
                    </div>
                </div>
            `;
        }).join('');
    } else {
        brazosHTML = '<p style="text-align: center; color: #7f8c8d; padding: 20px;">No se encontraron brazos para este HL5</p>';
    }
    
    return `
        <div class="popup-hl5-afectado">
            <div class="popup-header">
                <h3>🚨 HL5 Alarmado</h3>
            </div>
            <div class="popup-info">
                <div class="popup-info-row">
                    <span class="popup-label">HL5:</span>
                    <span class="popup-value">${cinumCiname}</span>
                </div>
                <div class="popup-info-row">
                    <span class="popup-label">Ubicación:</span>
                    <span class="popup-value">${hl5.cod_ubica || 'N/A'}</span>
                </div>
                <div class="popup-info-row">
                    <span class="popup-label">IP:</span>
                    <span class="popup-value">${hl5.ip || 'N/A'}</span>
                </div>
                <div class="popup-info-row">
                    <span class="popup-label">Ciudad:</span>
                    <span class="popup-value">${hl5.ciudad || 'N/A'} - ${hl5.departamento || 'N/A'}</span>
                </div>
                <div class="popup-info-row">
                    <span class="popup-label">OT:</span>
                    <span class="popup-value">${hl5.ot || 'N/A'}</span>
                </div>
                <div class="popup-info-row">
                    <span class="popup-label">Grupo:</span>
                    <span class="popup-value">${hl5.grupo_ot || 'N/A'}</span>
                </div>
                <div class="popup-info-row">
                    <span class="popup-label">Estado:</span>
                    <span class="popup-badge popup-badge-down">${hl5.estado_ot || 'N/A'}</span>
                </div>
                <div class="popup-info-row">
                    <span class="popup-label">Tiempo:</span>
                    <span class="popup-value">${hl5.horas ? hl5.horas.toFixed(1) + 'h' : 'N/A'} (${hl5.dias ? hl5.dias.toFixed(1) + 'd' : 'N/A'})</span>
                </div>
            </div>
            <div class="popup-brazos-container">
                <h4>Enlaces (${numBrazos})</h4>
                <div class="popup-brazos-scroll">
                    ${brazosHTML}
                </div>
            </div>
            <div class="popup-avance-container">
                <h4>📝 Último Avance</h4>
                <div class="popup-avance-content">
                    ${hl5.avance ? `<p>${hl5.avance}</p>` : '<p class="popup-avance-empty">Sin avances registrados</p>'}
                </div>
            </div>
        </div>
    `;
}

/**
 * Actualizar métricas del dashboard
 */
function actualizarMetricas(datos) {
    try {
        console.log('📊 Actualizando métricas con', datos.length, 'registros');
        
        const cabeceras = datos.filter(d => d.TIPO_APERTURA === 'CABECERA');
        const anillos = datos.filter(d => d.TIPO_APERTURA === 'ANILLO');

        // Totales
        const elemTotalCabeceras = document.getElementById('totalCabeceras');
        const elemTotalAnillos = document.getElementById('totalAnillos');
        
        if (elemTotalCabeceras) elemTotalCabeceras.textContent = cabeceras.length;
        if (elemTotalAnillos) elemTotalAnillos.textContent = anillos.length;

        // Cabeceras con afectación
        const cabAfectacion = cabeceras.filter(d => d.AFECTA === 'SI').length;
        const elemCabecerasAfectacion = document.getElementById('cabecerasAfectacion');
        if (elemCabecerasAfectacion) elemCabecerasAfectacion.textContent = cabAfectacion;

        // Anillos con afectación
        const aniAfectacion = anillos.filter(d => d.AFECTA === 'SI').length;
        const elemAnillosAfectacion = document.getElementById('anillosAfectacion');
        if (elemAnillosAfectacion) elemAnillosAfectacion.textContent = aniAfectacion;

        // Distribución por tiempo - Cabeceras
        const cab4h = cabeceras.filter(d => d.HORAS < 4).length;
        const cab8h = cabeceras.filter(d => d.HORAS >= 8 && d.HORAS < 24).length;
        const cab24h = cabeceras.filter(d => d.HORAS >= 24 && d.HORAS < 48).length;
        const cab2d = cabeceras.filter(d => d.HORAS >= 48).length;

        actualizarSemiCirculo('cab4h', 'cab4hVal', cab4h, cabeceras.length);
        actualizarSemiCirculo('cab8h', 'cab8hVal', cab8h, cabeceras.length);
        actualizarSemiCirculo('cab24h', 'cab24hVal', cab24h, cabeceras.length);
        actualizarSemiCirculo('cab2d', 'cab2dVal', cab2d, cabeceras.length);

        // Distribución por tiempo - Anillos
        const ani4h = anillos.filter(d => d.HORAS < 4).length;
        const ani8h = anillos.filter(d => d.HORAS >= 8 && d.HORAS < 24).length;
        const ani24h = anillos.filter(d => d.HORAS >= 24 && d.HORAS < 48).length;
        const ani2d = anillos.filter(d => d.HORAS >= 48).length;

        actualizarSemiCirculo('ani4h', 'ani4hVal', ani4h, anillos.length);
        actualizarSemiCirculo('ani8h', 'ani8hVal', ani8h, anillos.length);
        actualizarSemiCirculo('ani24h', 'ani24hVal', ani24h, anillos.length);
        actualizarSemiCirculo('ani2d', 'ani2dVal', ani2d, anillos.length);
        
    } catch (error) {
        console.error('❌ Error en actualizarMetricas:', error);
        throw error;
    }
}

/**
 * Actualizar semicírculo individual
 */
function actualizarSemiCirculo(fillId, valId, valor, total) {
    try {
        const porcentaje = total > 0 ? (valor / total * 100) : 0;
        const elemFill = document.getElementById(fillId);
        const elemVal = document.getElementById(valId);
        
        if (elemFill) elemFill.style.height = porcentaje + '%';
        if (elemVal) elemVal.textContent = valor;
    } catch (error) {
        console.warn(`⚠️ Error actualizando semicírculo ${fillId}:`, error);
    }
}

/**
 * Pintar mapa unificado con cabeceras y anillos
 */
function pintarMapaUnificado(datos) {
    try {
        console.log('🗺️ Pintando mapa con', datos.length, 'registros');
        
        if (!layerCabeceras || !layerAnillos) {
            console.warn('⚠️ Layers no inicializados, saltando renderizado del mapa');
            return;
        }
        
        const cabeceras = datos.filter(d => d.TIPO_APERTURA === 'CABECERA');
        const anillos = datos.filter(d => d.TIPO_APERTURA === 'ANILLO');

        // Limpiar layers
        layerCabeceras.clearLayers();
        layerAnillos.clearLayers();

        // Pintar cabeceras (rombos morados)
        pintarCabeceras(cabeceras);
        
        // Pintar anillos (círculos)
        pintarAnillos(anillos);

        // Actualizar contadores
        const elemContadorCabeceras = document.getElementById('contadorCabeceras');
        const elemContadorAnillos = document.getElementById('contadorAnillos');
        
        if (elemContadorCabeceras) elemContadorCabeceras.textContent = `${cabeceras.length} sitios`;
        if (elemContadorAnillos) elemContadorAnillos.textContent = `${anillos.length} sitios`;
        
    } catch (error) {
        console.error('❌ Error en pintarMapaUnificado:', error);
        throw error;
    }
}

/**
 * Pintar cabeceras como rombos morados (rojo si está DOWN)
 */
function pintarCabeceras(cabeceras) {
    cabeceras.forEach(apertura => {
        try {
            const latA = parseFloat(apertura.LATITUD_A);
            const lonA = parseFloat(apertura.LONGITUD_A);
            const latB = parseFloat(apertura.LATITUD_B);
            const lonB = parseFloat(apertura.LONGITUD_B);

            if (!isNaN(latA) && !isNaN(lonA) && !isNaN(latB) && !isNaN(lonB)) {
                const statusA = apertura.NODO_A_STATUS;
                const statusB = apertura.NODO_B_STATUS;
                
                // Color: rojo si está DOWN, morado si está UP
                const colorA = statusA === 'DOWN' ? '#dc3545' : '#9D4edd';
                const colorB = statusB === 'DOWN' ? '#dc3545' : '#5f21d3'; 
                const colorLinea = (statusA === 'DOWN' || statusB === 'DOWN') ? '#dc3545' : '#9D4edd';

                // Marcador Nodo A (rombo)
                const iconoA = L.divIcon({
                    className: 'custom-marker-diamond',
                    html: `<div style="
                        width: 14px; 
                        height: 14px; 
                        background: ${colorA}; 
                        transform: rotate(45deg);
                        border: 1px solid white;
                    "></div>`,
                    iconSize: [14, 14],
                    iconAnchor: [7, 7]
                });

                L.marker([latA, lonA], {icon: iconoA})
                    .bindPopup(crearPopup(apertura, 'A'))
                    .addTo(layerCabeceras);

                // Marcador Nodo B (rombo)
                const iconoB = L.divIcon({
                    className: 'custom-marker-diamond',
                    html: `<div style="
                        width: 14px; 
                        height: 14px; 
                        background: ${colorB}; 
                        transform: rotate(45deg);
                        border: 1px solid white;
                    "></div>`,
                    iconSize: [14, 14],
                    iconAnchor: [7, 7]
                });

                L.marker([latB, lonB], {icon: iconoB})
                    .bindPopup(crearPopup(apertura, 'B'))
                    .addTo(layerCabeceras);

                // Línea conectando A y B
                L.polyline(
                    [[latA, lonA], [latB, lonB]],
                    {
                        color: colorLinea,
                        weight: 3,
                        opacity: 0.7,
                        dashArray: '5, 5'
                    }
                ).bindPopup(crearPopupLinea(apertura))
                .addTo(layerCabeceras);
            }
        } catch (error) {
            console.warn('⚠️ Error pintando cabecera:', error);
        }
    });
}

/**
 * Pintar anillos con colores según estado
 */
function pintarAnillos(anillos) {
    anillos.forEach(apertura => {
        try {
            const latA = parseFloat(apertura.LATITUD_A);
            const lonA = parseFloat(apertura.LONGITUD_A);
            const latB = parseFloat(apertura.LATITUD_B);
            const lonB = parseFloat(apertura.LONGITUD_B);

            if (!isNaN(latA) && !isNaN(lonA) && !isNaN(latB) && !isNaN(lonB)) {
                const statusA = apertura.NODO_A_STATUS;
                const statusB = apertura.NODO_B_STATUS;
                
                // Colores para anillos
                const colorA = statusA === 'DOWN' ? '#dc3545' : '#007bff';
                const colorB = statusB === 'DOWN' ? '#dc3545' : '#0056b3';
                const colorLinea = (statusA === 'DOWN' || statusB === 'DOWN') ? '#dc3545' : '#007bff';

                // Marcador Nodo A (círculo)
                const iconoA = L.divIcon({
                    className: 'custom-marker-circle',
                    html: `<div style="
                        width: 12px; 
                        height: 12px; 
                        background: ${colorA}; 
                        border-radius: 50%;
                        border: 1px solid white;
                    "></div>`,
                    iconSize: [12, 12],
                    iconAnchor: [6, 6]
                });

                L.marker([latA, lonA], {icon: iconoA})
                    .bindPopup(crearPopup(apertura, 'A'))
                    .addTo(layerAnillos);

                // Marcador Nodo B (círculo)
                const iconoB = L.divIcon({
                    className: 'custom-marker-circle',
                    html: `<div style="
                        width: 12px; 
                        height: 12px; 
                        background: ${colorB}; 
                        border-radius: 50%;
                        border: 1px solid white;
                    "></div>`,
                    iconSize: [12, 12],
                    iconAnchor: [6, 6]
                });

                L.marker([latB, lonB], {icon: iconoB})
                    .bindPopup(crearPopup(apertura, 'B'))
                    .addTo(layerAnillos);

                // Línea conectando A y B
                L.polyline(
                    [[latA, lonA], [latB, lonB]],
                    {
                        color: colorLinea,
                        weight: 2,
                        opacity: 0.6
                    }
                ).bindPopup(crearPopupLinea(apertura))
                .addTo(layerAnillos);
            }
        } catch (error) {
            console.warn('⚠️ Error pintando anillo:', error);
        }
    });
}

/**
 * Crear popup para nodos A o B
 */
function crearPopup(apertura, nodo) {
    const esNodoA = nodo === 'A';
    const nombre = esNodoA ? apertura.NODO_A : apertura.NODO_B;
    const ip = esNodoA ? apertura.IP_A : apertura.IP_B;
    const status = esNodoA ? apertura.NODO_A_STATUS : apertura.NODO_B_STATUS;
    const sitLocation = esNodoA ? apertura.SIT_LOCATION_A : apertura.SIT_LOCATION_B;
    const fabricante = esNodoA ? apertura.FABRICANTE_A : apertura.FABRICANTE_B;
    const departamento = esNodoA ? apertura.DEPARTAMENTO_A : apertura.DEPARTAMENTO_B;
    const municipio = esNodoA ? apertura.MUNICIPIO_A : apertura.MUNICIPIO_B;

    const badgeClass = status === 'UP' ? 'up' : 'down';

    return `
        <div class="popup-content">
            <h3 class="popup-title">Nodo ${nodo}</h3>
            <p><strong>Nombre:</strong> ${nombre || 'N/A'}</p>
            <p><strong>IP:</strong> ${ip || 'N/A'}</p>
            <p><strong>Estado:</strong> <span class="badge ${badgeClass}">${status || 'N/A'}</span></p>
            <p><strong>Ubicación:</strong> ${sitLocation || 'N/A'}</p>
            <p><strong>Fabricante:</strong> ${fabricante || 'N/A'}</p>
            <p><strong>Ciudad:</strong> ${municipio || 'N/A'}, ${departamento || 'N/A'}</p>
            <hr>
            <p><strong>OT:</strong> ${apertura.OT || 'N/A'}</p>
            <p><strong>Grupo:</strong> ${apertura.GRUPO_OT || 'N/A'}</p>
            <p><strong>Tiempo:</strong> ${apertura.HORAS ? apertura.HORAS.toFixed(1) + 'h' : 'N/A'}</p>
        </div>
    `;
}

/**
 * Crear popup para líneas de conexión
 */
function crearPopupLinea(apertura) {
    const badgeClass = apertura.AFECTA === 'SI' ? 'down' : 'up';
    return `
        <div class="popup-content">
            <h3 class="popup-title">${apertura.TIPO_APERTURA || 'N/A'}</h3>
            <p><strong>Conexión:</strong> ${apertura.NODO_A || 'N/A'} ↔ ${apertura.NODO_B || 'N/A'}</p>
            <p><strong>Afectación:</strong> <span class="badge ${badgeClass}">${apertura.AFECTA || 'N/A'}</span></p>
            <p><strong>Hora Inicio:</strong> ${apertura.HORA_INICIO || 'N/A'}</p>
            <p><strong>Tiempo:</strong> ${apertura.HORAS ? apertura.HORAS.toFixed(1) + 'h' : 'N/A'}</p>
            <p><strong>OT:</strong> ${apertura.OT || 'N/A'}</p>
            <p><strong>Estado OT:</strong> ${apertura.ESTADO_OT || 'N/A'}</p>
        </div>
    `;
}

/**
 * Renderizar tabla filtrada - VERSION MEJORADA
 */
function renderizarTablaFiltrada() {
    try {
        console.log('📋 Renderizando tabla con', datosTablaActual.length, 'registros');
        
        const tbody = document.getElementById('tablaBody');
        
        if (!tbody) {
            console.error('❌ No se encontró el elemento tbody con id "tablaBody"');
            return;
        }
        
        if (datosTablaActual.length === 0) {
            tbody.innerHTML = '<tr><td colspan="15" style="text-align: center; padding: 40px; color: #7f8c8d;">No hay registros para mostrar</td></tr>';
            const totalRegistros = document.getElementById('totalRegistros');
            if (totalRegistros) {
                totalRegistros.textContent = '0 registros';
            }
            console.log('⚠️ No hay datos para mostrar en la tabla');
            return;
        }

        let html = '';
        datosTablaActual.forEach((d, index) => {
            html += `
                <tr>
                    <td>${d.HORA_INICIO || 'N/A'}</td>
                    <td><span class="badge ${d.TIPO_APERTURA === 'CABECERA' ? 'cabecera' : 'anillo'}">${d.TIPO_APERTURA || 'N/A'}</span></td>
                    <td>${d.ANILLO || 'N/A'}</td>
                    <td>${d.NODO_A || 'N/A'}</td>
                    <td>${d.IP_A || 'N/A'}</td>
                    <td><span class="badge ${d.NODO_A_STATUS === 'UP' ? 'up' : 'down'}">${d.NODO_A_STATUS || 'N/A'}</span></td>
                    <td>${d.NODO_B || 'N/A'}</td>
                    <td>${d.IP_B || 'N/A'}</td>
                    <td><span class="badge ${d.NODO_B_STATUS === 'UP' ? 'up' : 'down'}">${d.NODO_B_STATUS || 'N/A'}</span></td>
                    <td>${d.HORAS ? d.HORAS.toFixed(1) + 'h' : 'N/A'}</td>
                    <td><span class="badge ${d.AFECTA === 'SI' ? 'down' : 'up'}">${d.AFECTA || 'N/A'}</span></td>
                    <td>${d.OT || 'N/A'}</td>
                    <td>${d.GRUPO_OT || 'N/A'}</td>
                    <td>${d.AVANCE || 'N/A'}</td>
                    <td>
                        <button class="btn-acciones" onclick="abrirModalAcciones(${index})" title="Gestionar OT">
                            <ion-icon name="create-outline"></ion-icon>
                        </button>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
        
        const totalRegistros = document.getElementById('totalRegistros');
        if (totalRegistros) {
            totalRegistros.textContent = `${datosTablaActual.length} registros`;
        }
        
        console.log('✅ Tabla renderizada exitosamente');
        
    } catch (error) {
        console.error('❌ Error en renderizarTablaFiltrada:', error);
        throw error;
    }
}

// Placeholder para funciones de filtro de tabla que ya tenías
function inicializarFiltrosTabla() {
    const filterModal = document.getElementById('filter-modal');
    const filterOptionsContainer = document.getElementById('filter-options-container');
    const filterSearchInput = document.getElementById('filter-search-input');
    const btnSelectAll = document.getElementById('filter-select-all');
    const btnClear = document.getElementById('filter-clear');
    if (!filterModal || !filterOptionsContainer || !filterSearchInput) {
        console.warn('⚠️ No se encontraron elementos del modal de filtro');
        return;
    }

    // Abrir modal al hacer clic en el ícono de filtro
    document.querySelectorAll('.filter-icon').forEach(icon => {
        icon.addEventListener('click', () => {
            columnaFiltroActual = icon.dataset.col;
            const baseDatos = datosFiltroPrincipal.length ? datosFiltroPrincipal : datosGlobales;
            valoresFiltroActual = Array.from(
                new Set(baseDatos.map(d => normalizarValor(d[columnaFiltroActual])))
            ).sort();

            // Renderizar opciones
            renderOpcionesFiltro(filtrosActivos[columnaFiltroActual] || valoresFiltroActual);

            // Reset búsqueda
            filterSearchInput.value = '';

            // Mostrar modal
            filterModal.classList.add('show');
        });
    });

    // Filtro por texto dentro del modal
    filterSearchInput.addEventListener('input', () => {
        const texto = filterSearchInput.value.toLowerCase();
        const filtrados = valoresFiltroActual.filter(v => String(v).toLowerCase().includes(texto));
        renderOpcionesFiltro(filtrosActivos[columnaFiltroActual] || filtrados, filtrados);
    });

    // Botones Ok / Cancel
    document.getElementById('filter-btn-ok').addEventListener('click', () => {
        if (!columnaFiltroActual) return;
        const seleccionados = Array.from(filterOptionsContainer.querySelectorAll('input[type="checkbox"]:checked'))
            .map(chk => chk.value);

        if (seleccionados.length === 0 || seleccionados.length === valoresFiltroActual.length) {
            delete filtrosActivos[columnaFiltroActual];
        } else {
            filtrosActivos[columnaFiltroActual] = seleccionados;
        }

        aplicarFiltrosTabla();
        cerrarModalFiltros();
    });

    document.getElementById('filter-btn-cancel').addEventListener('click', cerrarModalFiltros);
    const closeIcon = document.querySelector('.filter-modal-close');
    if (closeIcon) closeIcon.addEventListener('click', cerrarModalFiltros);
    filterModal.addEventListener('click', (e) => {
        if (e.target === filterModal) cerrarModalFiltros();
    });

    // Seleccionar todo / Limpiar selección
    if (btnSelectAll) {
        btnSelectAll.addEventListener('click', () => {
            filterOptionsContainer.querySelectorAll('input[type="checkbox"]').forEach(chk => {
                chk.checked = true;
            });
        });
    }
    if (btnClear) {
        btnClear.addEventListener('click', () => {
            filterOptionsContainer.querySelectorAll('input[type="checkbox"]').forEach(chk => {
                chk.checked = false;
            });
        });
    }

    function renderOpcionesFiltro(seleccionados, lista = valoresFiltroActual) {
        const setSeleccion = new Set(seleccionados || []);
        filterOptionsContainer.innerHTML = lista.map(valor => {
            const checked = setSeleccion.size === 0 || setSeleccion.has(valor) ? 'checked' : '';
            return `
                <label class="filter-option">
                    <input type="checkbox" value="${valor}" ${checked}>
                    <span>${valor}</span>
                </label>
            `;
        }).join('');
    }

    function cerrarModalFiltros() {
        filterModal.classList.remove('show');
        columnaFiltroActual = null;
        valoresFiltroActual = [];
        filterOptionsContainer.innerHTML = '';
        filterSearchInput.value = '';
    }
}

function aplicarFiltrosTabla() {
    let datosFiltrados = [...datosFiltroPrincipal];

    Object.entries(filtrosActivos).forEach(([col, valores]) => {
        const setValores = new Set(valores.map(normalizarValor));
        datosFiltrados = datosFiltrados.filter(d => setValores.has(normalizarValor(d[col])));
    });

    datosTablaActual = datosFiltrados;
    renderizarTablaFiltrada();
}


function mostrarError(mensaje) {
    console.error('❌', mensaje);
    const tbody = document.getElementById('tablaBody');
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="15" style="text-align: center; padding: 40px; color: #e74c3c;">${mensaje || 'Error al cargar los datos'}</td></tr>`;
    }
}

function abrirModalAcciones(index) {
    aperturaSeleccionada = datosTablaActual[index];
    const modal = document.getElementById('modalAcciones');
    if (modal) {
        modal.classList.add('show');
        modal.style.display = 'flex';
        
        // Llenar información del modal
        const modalInfo = document.getElementById('modalInfo');
        if (modalInfo) {
            modalInfo.innerHTML = `
            <div class="modal-info-row">
                <span class="modal-info-label">OT:</span>
                <span class="modal-info-value">${aperturaSeleccionada.OT || 'N/A'}</span>
            </div>
            <div class="modal-info-row">
                <span class="modal-info-label">Tipo:</span>
                <span class="modal-info-value">${aperturaSeleccionada.TIPO_APERTURA || 'N/A'}</span>
            </div>
            <div class="modal-info-row">
                <span class="modal-info-label">Nodo A:</span>
                <span class="modal-info-value">${aperturaSeleccionada.NODO_A || 'N/A'} (${aperturaSeleccionada.NODO_A_STATUS || 'N/A'})</span>
            </div>
            <div class="modal-info-row">
                <span class="modal-info-label">Nodo B:</span>
                <span class="modal-info-value">${aperturaSeleccionada.NODO_B || 'N/A'} (${aperturaSeleccionada.NODO_B_STATUS || 'N/A'})</span>
            </div>
            <div class="modal-info-row">
                <span class="modal-info-label">Horas:</span>
                <span class="modal-info-value">${aperturaSeleccionada.HORAS ? aperturaSeleccionada.HORAS.toFixed(1) + 'h' : 'N/A'}</span>
            </div>
            <div class="modal-info-row">
                <span class="modal-info-label">Afecta:</span>
                <span class="modal-info-value">${aperturaSeleccionada.AFECTA || 'N/A'}</span>
            </div>
            <div class="modal-info-row">
                <span class="modal-info-label">Grupo:</span>
                <span class="modal-info-value">${aperturaSeleccionada.GRUPO_OT || 'N/A'}</span>
            </div>
        `;
        }
    }

    // Mostrar menú de opciones por defecto
    document.getElementById('menuOpciones').style.display = 'flex';
    document.getElementById('formAvance').style.display = 'none';
    document.getElementById('formCerrar').style.display = 'none';
    document.getElementById('formEscalar').style.display = 'none';
}

/**
 * Filtro principal por tipo / afectación
 */
function filtrarTabla(tipo, ev) {
    if (ev) ev.preventDefault();
    filtroActual = tipo;
    // Reset filtros de columnas
    for (const key in filtrosActivos) delete filtrosActivos[key];

    if (tipo === 'TODOS') {
        datosFiltroPrincipal = [...datosGlobales];
    } else if (tipo === 'CABECERA') {
        datosFiltroPrincipal = datosGlobales.filter(d => d.TIPO_APERTURA === 'CABECERA');
    } else if (tipo === 'ANILLO') {
        datosFiltroPrincipal = datosGlobales.filter(d => d.TIPO_APERTURA === 'ANILLO');
    } else if (tipo === 'SI') { // Con afectación
        datosFiltroPrincipal = datosGlobales.filter(d => d.AFECTA === 'SI');
    } else if (tipo === 'NO') { // Sin afectación
        datosFiltroPrincipal = datosGlobales.filter(d => d.AFECTA === 'NO');
    } else {
        datosFiltroPrincipal = [...datosGlobales];
    }

    datosTablaActual = [...datosFiltroPrincipal];
    aplicarFiltrosTabla();

    // Actualizar estado visual de botones
    document.querySelectorAll('.filtro-btn').forEach(btn => btn.classList.remove('active'));
    if (ev && ev.target) {
        ev.target.classList.add('active');
    }
}

/**
 * Limpiar todos los filtros (botón)
 */
function limpiarFiltros() {
    // borrar filtros de columnas
    for (const key in filtrosActivos) delete filtrosActivos[key];
    // reset filtro principal
    filtroActual = 'TODOS';
    datosFiltroPrincipal = [...datosGlobales];
    datosTablaActual = [...datosGlobales];
    aplicarFiltrosTabla();

    // botones principales
    document.querySelectorAll('.filtro-btn').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.trim().toUpperCase() === 'TODOS');
    });
}

function cerrarModal() {
    const modal = document.getElementById('modalAcciones');
    if (modal) {
        modal.classList.remove('show');
        modal.style.display = 'none';
    }
    aperturaSeleccionada = null;
    
    // Resetear formularios
    const limpiar = ['avanceComentario','cierreComentario','cierreEstado','escalarArea','escalarMotivo'];
    limpiar.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });

    // Volver al menú principal
    volverMenu();
}

function mostrarFormulario(tipo) {
    // Ocultar menú de opciones
    document.getElementById('menuOpciones').style.display = 'none';
    
    // Mostrar formulario correspondiente
    document.getElementById('formAvance').style.display = tipo === 'avance' ? 'block' : 'none';
    document.getElementById('formCerrar').style.display = tipo === 'cerrar' ? 'block' : 'none';
    document.getElementById('formEscalar').style.display = tipo === 'escalar' ? 'block' : 'none';
}

function volverMenu() {
    document.getElementById('menuOpciones').style.display = 'flex';
    document.getElementById('formAvance').style.display = 'none';
    document.getElementById('formCerrar').style.display = 'none';
    document.getElementById('formEscalar').style.display = 'none';
}

async function enviarAvance(event) {
    event.preventDefault();
    
    if (!aperturaSeleccionada) {
        alert('No hay OT seleccionada');
        return;
    }
    
    const comentario = document.getElementById('avanceComentario').value;
    
    try {
        const response = await fetch('/api/maximo/avance', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ot: aperturaSeleccionada.OT,
                comentario: comentario
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('Avance registrado exitosamente');
            cerrarModal();
            cargarDatos(); // Recargar datos
        } else {
            alert('Error al registrar avance: ' + (data.error || 'Error desconocido'));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al registrar avance');
    }
}

async function cerrarOT(event) {
    event.preventDefault();
    
    if (!aperturaSeleccionada) {
        alert('No hay OT seleccionada');
        return;
    }
    
    const comentario = document.getElementById('cierreComentario').value;
    const estado = document.getElementById('cierreEstado').value;
    
    if (!confirm(`¿Estás seguro de cerrar la OT ${aperturaSeleccionada.OT} con estado ${estado}?`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/maximo/cerrar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ot: aperturaSeleccionada.OT,
                comentario: comentario,
                estado: estado
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('OT cerrada exitosamente');
            cerrarModal();
            cargarDatos(); // Recargar datos
        } else {
            alert('Error al cerrar OT: ' + (data.error || 'Error desconocido'));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al cerrar OT');
    }
}

async function escalarOT(event) {
    event.preventDefault();
    
    if (!aperturaSeleccionada) {
        alert('No hay OT seleccionada');
        return;
    }
    
    const area = document.getElementById('escalarArea').value;
    const motivo = document.getElementById('escalarMotivo').value;
    
    if (!confirm(`¿Estás seguro de escalar la OT ${aperturaSeleccionada.OT} al área ${area}?`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/maximo/escalar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ot: aperturaSeleccionada.OT,
                area: area,
                motivo: motivo
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('OT escalada exitosamente');
            cerrarModal();
            cargarDatos(); // Recargar datos
        } else {
            alert('Error al escalar OT: ' + (data.error || 'Error desconocido'));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al escalar OT');
    }
}

// ============================================
// PANEL ANILLOS AFECTADOS
// ============================================

let datosAnillosPanel = [];
let filtroPanelActual = 'TODOS';

/**
 * Cargar y renderizar el panel de anillos afectados
 */
async function cargarPanelAnillos() {
    try {
        const response = await fetch('/api/hl5/anillos-panel');
        const data = await response.json();
        if (data.success) {
            // Ordenar por máximo de horas afectadas DESC (más tiempo afectado primero)
            data.anillos_afectados.sort((a, b) => {
                const maxHorasA = Math.max(
                    ...(a.aperturas || []).map(ap => ap.horas || 0),
                    ...(a.hl5 || []).map(h => h.horas || 0),
                    0
                );
                const maxHorasB = Math.max(
                    ...(b.aperturas || []).map(ap => ap.horas || 0),
                    ...(b.hl5 || []).map(h => h.horas || 0),
                    0
                );
                return maxHorasB - maxHorasA;
            });
            datosAnillosPanel = data.anillos_afectados;
            aplicarFiltroPanelAnillos();
        } else {
            console.error('Error cargando panel anillos:', data.error);
        }
    } catch (e) {
        console.error('Error en cargarPanelAnillos:', e);
    }
}

/**
 * Filtrar panel por tipo
 */
function filtrarPanel(tipo, btn) {
    filtroPanelActual = tipo;
    document.querySelectorAll('.panel-filtro-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    aplicarFiltroPanelAnillos();
}

function aplicarFiltroPanelAnillos() {
    let filtrados = datosAnillosPanel;
    if (filtroPanelActual !== 'TODOS') {
        filtrados = datosAnillosPanel.filter(a =>
            (a.tipos_afectacion || []).includes(filtroPanelActual)
        );
    }
    renderizarPanelAnillos(filtrados);
}

/**
 * Renderizar la lista de tarjetas de anillos en el panel
 */
function renderizarPanelAnillos(anillos) {
    const body = document.getElementById('panelAnillosBody');
    const count = document.getElementById('panelAnillosCount');
    if (!body) return;

    if (count) count.textContent = anillos.length;

    if (anillos.length === 0) {
        body.innerHTML = '<div style="padding:20px; text-align:center; color:#7f8c8d; font-size:13px;">Sin anillos afectados</div>';
        return;
    }

    body.innerHTML = anillos.map((a, idx) => {
        // Calcular horas máximas para mostrar
        const maxHoras = Math.max(
            ...(a.aperturas || []).map(ap => ap.horas || 0),
            ...(a.hl5 || []).map(h => h.horas || 0),
            0
        );
        const horasLabel = maxHoras > 0 ? `<span>⏱ ${maxHoras.toFixed(1)}h</span>` : '';

        const tipos = a.tipos_afectacion || [];
        const esMixto = tipos.length > 1;
        const badges = tipos.map(t => {
            const cls = t === 'CABECERA' ? 'cabecera' : t === 'ANILLO' ? 'anillo' : 'hl5';
            const label = t === 'CABECERA' ? 'Cabecera' : t === 'ANILLO' ? 'Anillo' : 'HL5';
            return `<span class="badge-tipo ${cls}">${label}</span>`;
        }).join('');

        const metaAperturas = a.total_aperturas > 0
            ? `<span>🔗 ${a.total_aperturas} brazo${a.total_aperturas > 1 ? 's' : ''}</span>` : '';
        const metaHL5 = a.total_hl5 > 0
            ? `<span>📡 ${a.total_hl5} HL5</span>` : '';
        const sinTopo = !a.tiene_topologia
            ? `<span style="color:#e67e22">⚠ Sin topología</span>` : '';

        // Encontrar el índice real en datosAnillosPanel para el modal
        const idxReal = datosAnillosPanel.indexOf(a);

        return `
        <div class="anillo-card ${esMixto ? 'mixto' : ''}" onclick="abrirModalGrafo(${idxReal})">
            <div class="anillo-card-nombre">${a.anillo}</div>
            <div class="anillo-card-badges">${badges}</div>
            <div class="anillo-card-meta">${horasLabel}${metaAperturas}${metaHL5}${sinTopo}</div>
        </div>`;
    }).join('');
}

/**
 * Abrir modal con el grafo del anillo
 */
function abrirModalGrafo(idx) {
    const anillo = datosAnillosPanel[idx];
    if (!anillo) return;

    const modal = document.getElementById('modalGrafoAnillo');
    const titulo = document.getElementById('modalGrafoTitulo');
    const badgesEl = document.getElementById('modalGrafoBadges');
    const statsEl = document.getElementById('modalGrafoStats');
    const svgWrapper = document.getElementById('modalGrafoSvg');
    const tablaEl = document.getElementById('modalGrafoTabla');

    titulo.textContent = anillo.anillo;

    // Badges de tipo
    badgesEl.innerHTML = (anillo.tipos_afectacion || []).map(t => {
        const cls = t === 'CABECERA' ? 'cabecera' : t === 'ANILLO' ? 'anillo' : 'hl5';
        const label = t === 'CABECERA' ? 'Cabecera' : t === 'ANILLO' ? 'Anillo' : 'HL5';
        return `<span class="badge-tipo ${cls}">${label}</span>`;
    }).join('');

    // Stats
    const enlacesAfectados = (anillo.topologia || []).filter(l => l.afectado).length;
    const totalEnlaces = (anillo.topologia || []).length;
    statsEl.innerHTML = `
        <div class="grafo-stat-card">
            <div class="grafo-stat-value">${totalEnlaces}</div>
            <div class="grafo-stat-label">Total enlaces</div>
        </div>
        <div class="grafo-stat-card">
            <div class="grafo-stat-value" style="color:#dc3545">${enlacesAfectados}</div>
            <div class="grafo-stat-label">Afectados</div>
        </div>
        <div class="grafo-stat-card">
            <div class="grafo-stat-value" style="color:#9b59b6">${anillo.total_aperturas}</div>
            <div class="grafo-stat-label">Brazos</div>
        </div>
        <div class="grafo-stat-card">
            <div class="grafo-stat-value" style="color:#e74c3c">${anillo.total_hl5}</div>
            <div class="grafo-stat-label">HL5</div>
        </div>`;

    // Dibujar grafo SVG
    if (anillo.topologia && anillo.topologia.length > 0) {
        dibujarGrafoAnillo(anillo.topologia, svgWrapper);
    } else {
        svgWrapper.innerHTML = '<div style="padding:40px; text-align:center; color:#aaa;">⚠️ Sin topología disponible</div>';
    }

    // Tabla de enlaces afectados
    const afectados = (anillo.topologia || []).filter(l => l.afectado);
    if (afectados.length > 0) {
        tablaEl.innerHTML = `
        <div class="modal-grafo-tabla-titulo">🔴 Detalle de enlaces afectados (${afectados.length})</div>
        <table>
            <thead>
                <tr>
                    <th>Origen</th>
                    <th>Destino</th>
                    <th>Tipo</th>
                    <th>OT</th>
                    <th>Horas</th>
                </tr>
            </thead>
            <tbody>
                ${afectados.map(l => `
                <tr class="fila-afectada">
                    <td>${l.device_origen || 'N/A'}</td>
                    <td>${l.device_destino || 'N/A'}</td>
                    <td><span class="badge-tipo ${(l.tipo_afectacion||'').toLowerCase() === 'cabecera' ? 'cabecera' : (l.tipo_afectacion||'').toLowerCase() === 'hl5' ? 'hl5' : 'anillo'}">${l.tipo_afectacion || 'N/A'}</span></td>
                    <td>${l.ot_afectacion || 'N/A'}</td>
                    <td>${l.horas_afectacion ? l.horas_afectacion.toFixed(1) + 'h' : 'N/A'}</td>
                </tr>`).join('')}
            </tbody>
        </table>`;
    } else {
        tablaEl.innerHTML = '';
    }

    modal.classList.add('show');
}

function cerrarModalGrafo() {
    const modal = document.getElementById('modalGrafoAnillo');
    if (modal) modal.classList.remove('show');
}

/**
 * Dibujar grafo SVG del anillo con layout circular
 */
function dibujarGrafoAnillo(topologia, container) {
    const ns = 'http://www.w3.org/2000/svg';

    // Extraer nodos únicos
    const nodesMap = new Map();
    const hl5Afectados = new Set();

    topologia.forEach(link => {
        const orig = link.device_origen || '';
        const dest = link.device_destino || '';
        if (orig && !nodesMap.has(orig)) nodesMap.set(orig, { id: orig, afectado: false });
        if (dest && !nodesMap.has(dest)) nodesMap.set(dest, { id: dest, afectado: false });
        if (link.nodo_hl5_afectado) hl5Afectados.add(link.nodo_hl5_afectado);
    });

    hl5Afectados.forEach(cinum => {
        if (nodesMap.has(cinum)) {
            nodesMap.get(cinum).afectado = true;
        }
    });

    const nodes = Array.from(nodesMap.values());
    const n = nodes.length;

    // Calcular tamaño del canvas según cantidad de nodos
    // Más nodos → canvas más grande para que los labels no se pisen
    const LABEL_MARGIN = 130; // espacio reservado alrededor para etiquetas
    const MIN_CIRC_R = 120;
    // Separación mínima entre nodos en el perímetro: ~160px para que los labels quepan
    const minPerimeter = n * 160;
    const ringR = Math.max(MIN_CIRC_R, minPerimeter / (2 * Math.PI));
    const W = (ringR + LABEL_MARGIN) * 2;
    const H = (ringR + LABEL_MARGIN) * 2;
    const cx = W / 2, cy = H / 2;
    const nodeR = 10;

    // Posicionar nodos en círculo empezando desde arriba (-π/2)
    nodes.forEach((node, i) => {
        const angle = (2 * Math.PI * i / n) - Math.PI / 2;
        node.x = cx + ringR * Math.cos(angle);
        node.y = cy + ringR * Math.sin(angle);
        node.angle = angle;
    });

    // Crear SVG con viewBox dinámico
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('xmlns', ns);
    svg.style.maxHeight = '520px';

    // Defs: marcadores de flecha
    const defs = document.createElementNS(ns, 'defs');

    ['arrow-normal', 'arrow-afect'].forEach((id, isAfect) => {
        const mk = document.createElementNS(ns, 'marker');
        mk.setAttribute('id', id);
        mk.setAttribute('markerWidth', '8');
        mk.setAttribute('markerHeight', '8');
        mk.setAttribute('refX', '6');
        mk.setAttribute('refY', '3');
        mk.setAttribute('orient', 'auto');
        const poly = document.createElementNS(ns, 'polygon');
        poly.setAttribute('points', '0 0, 8 3, 0 6');
        poly.setAttribute('fill', isAfect ? '#dc3545' : '#adb5bd');
        mk.appendChild(poly);
        defs.appendChild(mk);
    });
    svg.appendChild(defs);

    // Dibujar enlaces (primero para que queden debajo de los nodos)
    topologia.forEach(link => {
        const src = nodesMap.get(link.device_origen || '');
        const tgt = nodesMap.get(link.device_destino || '');
        if (!src || !tgt) return;

        const color = link.afectado ? '#dc3545' : '#adb5bd';

        const line = document.createElementNS(ns, 'line');
        line.setAttribute('x1', src.x);
        line.setAttribute('y1', src.y);
        line.setAttribute('x2', tgt.x);
        line.setAttribute('y2', tgt.y);
        line.setAttribute('stroke', color);
        line.setAttribute('stroke-width', link.afectado ? 2.5 : 1.5);
        if (link.afectado) line.setAttribute('stroke-dasharray', '7,3');
        line.setAttribute('marker-end', link.afectado ? 'url(#arrow-afect)' : 'url(#arrow-normal)');

        const title = document.createElementNS(ns, 'title');
        title.textContent = link.afectado
            ? `${link.device_origen} → ${link.device_destino}
Tipo: ${link.tipo_afectacion}
OT: ${link.ot_afectacion || 'N/A'} | ${link.horas_afectacion ? link.horas_afectacion.toFixed(1) + 'h' : ''}`
            : `${link.device_origen} → ${link.device_destino}`;
        line.appendChild(title);
        svg.appendChild(line);
    });

    // Dibujar nodos y etiquetas completas
    nodes.forEach(node => {
        const g = document.createElementNS(ns, 'g');

        // Glow para HL5 afectados
        if (node.afectado) {
            const glow = document.createElementNS(ns, 'circle');
            glow.setAttribute('cx', node.x);
            glow.setAttribute('cy', node.y);
            glow.setAttribute('r', nodeR + 6);
            glow.setAttribute('fill', 'rgba(220,53,69,0.2)');
            g.appendChild(glow);
        }

        // Círculo del nodo
        const circle = document.createElementNS(ns, 'circle');
        circle.setAttribute('cx', node.x);
        circle.setAttribute('cy', node.y);
        circle.setAttribute('r', nodeR);
        circle.setAttribute('fill', node.afectado ? '#dc3545' : '#007bff');
        circle.setAttribute('stroke', 'white');
        circle.setAttribute('stroke-width', 2);
        g.appendChild(circle);

        // Posición de la etiqueta: hacia afuera del círculo
        const DIST = nodeR + 16;
        const lx = node.x + DIST * Math.cos(node.angle);
        const ly = node.y + DIST * Math.sin(node.angle);

        // Alineación horizontal según cuadrante
        const anchor = Math.cos(node.angle) < -0.15 ? 'end'
                      : Math.cos(node.angle) > 0.15 ? 'start'
                      : 'middle';

        // Offset vertical: si está arriba del centro sube, si está abajo baja
        const dyOffset = Math.sin(node.angle) < 0 ? -4 : 12;

        // Fondo blanco para la etiqueta (mejora legibilidad sobre líneas)
        const labelText = node.id;
        const charW = 7; // ancho aprox por carácter a font-size 11
        const textW = labelText.length * charW;
        const textH = 14;
        const padX = 4, padY = 2;

        const rectX = anchor === 'end'   ? lx - textW - padX
                    : anchor === 'start' ? lx - padX
                    : lx - textW / 2 - padX;

        const bg = document.createElementNS(ns, 'rect');
        bg.setAttribute('x', rectX);
        bg.setAttribute('y', ly + dyOffset - textH + padY);
        bg.setAttribute('width', textW + padX * 2);
        bg.setAttribute('height', textH + padY * 2);
        bg.setAttribute('fill', 'rgba(255,255,255,0.88)');
        bg.setAttribute('rx', '3');
        g.appendChild(bg);

        const label = document.createElementNS(ns, 'text');
        label.setAttribute('x', lx);
        label.setAttribute('y', ly + dyOffset);
        label.setAttribute('text-anchor', anchor);
        label.setAttribute('font-size', '11');
        label.setAttribute('font-family', 'monospace, Consolas, Courier New');
        label.setAttribute('fill', node.afectado ? '#c0392b' : '#1a252f');
        label.setAttribute('font-weight', node.afectado ? '700' : '500');
        label.textContent = labelText;  // Nombre COMPLETO sin truncar
        g.appendChild(label);

        svg.appendChild(g);
    });

    container.innerHTML = '';
    container.appendChild(svg);
}

// Cerrar modal grafo al hacer clic fuera
document.addEventListener('click', (e) => {
    const modal = document.getElementById('modalGrafoAnillo');
    if (e.target === modal) cerrarModalGrafo();
});

// Cerrar modal al hacer clic fuera de él
document.addEventListener('click', (event) => {
    const modal = document.getElementById('modalAcciones');
    if (event.target === modal) {
        cerrarModal();
    }
});

/**
 * Inicializar aplicación - VERSION CORREGIDA
 */
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Iniciando aplicación...');
    
    // Inicializar mapa
    const mapaInicializado = inicializarMapas();
    if (!mapaInicializado) {
        console.warn('⚠️ Mapa no inicializado, pero continuando...');
    }
    
    // Inicializar filtros
    try {
        inicializarFiltrosTabla();
    } catch (error) {
        console.error('❌ Error inicializando filtros:', error);
    }
    
    // Cargar datos
    cargarDatos();
    
    // Botón limpiar filtros
    const btnLimpiar = document.getElementById('btn-limpiar-filtros');
    if (btnLimpiar) {
        btnLimpiar.addEventListener('click', limpiarFiltros);
    }
    
    // Auto-refresh cada 5 minutos
    setInterval(cargarDatos, 5 * 60 * 1000);
    
    console.log('✅ Aplicación inicializada');
});