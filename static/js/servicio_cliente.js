// ============================================
// VARIABLES GLOBALES
// ============================================
let mapaEventos;
let markersFallas = [];
let markersMantenimientos = [];
let datosFallas = [];
let datosMantenimientos = [];
let tipoEventoSeleccionado = 'ambos';

// 🆕 NUEVA VARIABLE PARA TOTALES DE USUARIOS
let totalesUsuarios = {
    por_tecnologia: {},
    por_departamento: {},
    por_municipio: {},
    total_general: 0
};

// Capitales de departamentos de Colombia
const CAPITALES_COLOMBIA = [
    'BOGOTÁ', 'BOGOTA', 'BOGOTÁ D.C.', 'BOGOTA D.C.',
    'MEDELLÍN', 'MEDELLIN',
    'CALI',
    'BARRANQUILLA',
    'CARTAGENA', 'CARTAGENA DE INDIAS',
    'CÚCUTA', 'CUCUTA',
    'BUCARAMANGA',
    'PEREIRA',
    'SANTA MARTA',
    'IBAGUÉ', 'IBAGUE',
    'PASTO', 'SAN JUAN DE PASTO',
    'MANIZALES',
    'NEIVA',
    'VILLAVICENCIO',
    'ARMENIA',
    'VALLEDUPAR',
    'MONTERÍA', 'MONTERIA',
    'SINCELEJO',
    'POPAYÁN', 'POPAYAN',
    'TUNJA',
    'FLORENCIA',
    'QUIBDÓ', 'QUIBDO',
    'RIOHACHA',
    'YOPAL',
    'MOCOA',
    'SAN JOSÉ DEL GUAVIARE', 'SAN JOSE DEL GUAVIARE',
    'LETICIA',
    'INÍRIDA', 'INIRIDA',
    'PUERTO CARREÑO', 'PUERTO CARRENO',
    'MITÚ', 'MITU',
    'ARAUCA',
    'SAN ANDRES'
];

// Coordenadas centro de Colombia
const COLOMBIA_CENTER = [4.5709, -74.2973];
const ZOOM_INICIAL = 6;
const COLORES_ICONO_TECNOLOGIA = {
    '3G': '#d62828',
    '4G': '#2979ff',
    '5G': '#ffc107'
};
const selectIconStates = new Map();
const SEMAFORO_ESCALAS = [
    { limite: 4, clase: 'tiempo-verde', color: '#00b561' },
    { limite: 12, clase: 'tiempo-amarillo', color: '#ffc107' },
    { limite: 24, clase: 'tiempo-naranja', color: '#f57c00' },
    { limite: 72, clase: 'tiempo-cafe', color: '#bb7412 ' },
    { limite: Infinity, clase: 'tiempo-rojo', color: '#d62828' }
];

// ============================================
// INICIALIZACIÓN
// ============================================
document.addEventListener('DOMContentLoaded', async function() {
    console.log('🚀 Inicializando Servicio al Cliente...');
    console.log('🔍 Verificando disponibilidad de Leaflet:', typeof L !== 'undefined' ? '✅ Disponible' : '❌ No disponible');
    
    if (typeof L === 'undefined') {
        console.error('❌ ERROR CRÍTICO: Leaflet no está cargado. Verifica que el script esté en el HTML.');
        alert('Error: La librería de mapas no se cargó correctamente. Por favor recarga la página.');
        return;
    }
    
    try {
        inicializarSelectsTecnologia();
        inicializarMapas();
        
        // ✅ OPTIMIZACIÓN: Cargar fallas/mantenimientos PRIMERO (sin esperar totales)
        console.log('⚡ Cargando contenido principal sin esperar totales de usuarios...');
        await Promise.all([
            cargarFallas(),
            cargarMantenimientos()
        ]);
        
        // ✅ Cargar totales en segundo plano y actualizar porcentajes cuando estén listos
        cargarTotalesUsuariosYActualizar();         // ⬅️ SIN AWAIT - NO BLOQUEA
        
        // Configurar auto-refresh cada hora en punto
        configurarAutoRefresh();
    } catch (error) {
        console.error('❌ Error durante la inicialización:', error);
    }
});




// ============================================

// CARGAR TOTALES DE USUARIOS

// ============================================

// ============================================
// CARGAR TOTALES EN SEGUNDO PLANO Y ACTUALIZAR PORCENTAJES
// ============================================
async function cargarTotalesUsuariosYActualizar() {
    try {
        // Mostrar "Calculando..." en los porcentajes mientras se cargan los totales
        mostrarPorcentajesCalculando();
        
        // Cargar totales (esto puede tardar)
        await cargarTotalesUsuarios();
        
        // Una vez cargados, recalcular y actualizar los porcentajes
        actualizarTodosPorcentajes();
        
        console.log('✅ Porcentajes actualizados con totales de usuarios');
    } catch (error) {
        console.error('❌ Error al actualizar porcentajes:', error);
        mostrarPorcentajesError();
    }
}

async function cargarTotalesUsuarios() {
    try {
        console.log('[INFO] Cargando totales de usuarios (versión optimizada)...');
        
        // Mostrar indicador de carga
        mostrarIndicadorCargaTotales(true);
        
        const tiempoInicio = performance.now();
        const response = await fetch('/api/totales-usuarios');
        
        if (!response.ok) {
            throw new Error(`Error HTTP: ${response.status}`);
        }
        
        const data = await response.json();
        const tiempoTranscurrido = ((performance.now() - tiempoInicio) / 1000).toFixed(2);
        
        console.log(`[INFO] Totales recibidos en ${tiempoTranscurrido}s`);
        console.log(`[INFO] Caché usado: ${data.cache_usado ? 'SÍ ✅' : 'NO ❌'}`);
        console.log('[INFO] Totales de usuarios recibidos:', data);

        totalesUsuarios = data.totales || {
            por_tecnologia: {},
            por_departamento: {},
            por_municipio: {},
            total_general: 0
        };

        console.log(`[INFO] Totales cargados. Total general: ${totalesUsuarios.total_general.toLocaleString('es-CO')}`);
        
        // Ocultar indicador
        mostrarIndicadorCargaTotales(false);

        return totalesUsuarios;

    } catch (error) {
        console.error('[ERROR] Error cargando totales de usuarios:', error);
        mostrarIndicadorCargaTotales(false, true);
        
        totalesUsuarios = {
            por_tecnologia: {},
            por_departamento: {},
            por_municipio: {},
            total_general: 0
        };
        return totalesUsuarios;
    }
}

// ============================================
// MOSTRAR INDICADOR DE CARGA DE TOTALES
// ============================================
function mostrarIndicadorCargaTotales(mostrar, error = false) {
    const indicadorId = 'indicador-carga-totales';
    let indicador = document.getElementById(indicadorId);
    
    if (mostrar) {
        if (!indicador) {
            indicador = document.createElement('div');
            indicador.id = indicadorId;
            indicador.className = 'indicador-carga-totales';
            indicador.innerHTML = `
                <div class="spinner-container">
                    <ion-icon name="sync-outline" class="spinner-icon"></ion-icon>
                    <p>Cargando estadísticas de usuarios...</p>
                    <small>Esto puede tomar unos segundos la primera vez</small>
                </div>
            `;
            document.body.appendChild(indicador);
        }
        indicador.style.display = 'flex';
    } else {
        if (indicador) {
            if (error) {
                indicador.innerHTML = `
                    <div class="spinner-container error">
                        <ion-icon name="alert-circle-outline"></ion-icon>
                        <p>Error al cargar estadísticas</p>
                        <small>Intenta recargar la página</small>
                    </div>
                `;
                setTimeout(() => {
                    indicador.style.display = 'none';
                }, 3000);
            } else {
                indicador.style.display = 'none';
            }
        }
    }
}

// ============================================
// MOSTRAR "CALCULANDO..." EN PORCENTAJES
// ============================================
function mostrarPorcentajesCalculando() {
    const elementosFallas = document.getElementById('contador-porcentaje-fallas');
    const elementosMant = document.getElementById('contador-porcentaje-mant');
    
    if (elementosFallas) {
        elementosFallas.innerHTML = '<span class="calculando-porcentaje">Calculando</span>';
    }
    if (elementosMant) {
        elementosMant.innerHTML = '<span class="calculando-porcentaje">Calculando</span>';
    }
}

// ============================================
// MOSTRAR ERROR EN PORCENTAJES
// ============================================
function mostrarPorcentajesError() {
    const elementosFallas = document.getElementById('contador-porcentaje-fallas');
    const elementosMant = document.getElementById('contador-porcentaje-mant');
    
    if (elementosFallas) {
        elementosFallas.innerHTML = '<span style="font-size: 0.8em; color: #dc3545;">Error</span>';
    }
    if (elementosMant) {
        elementosMant.innerHTML = '<span style="font-size: 0.8em; color: #dc3545;">Error</span>';
    }
}

// ============================================
// ACTUALIZAR TODOS LOS PORCENTAJES
// ============================================
function actualizarTodosPorcentajes() {
    // Obtener filtros actuales
    const tecnologiaSelect = document.getElementById('filtro-tecnologia');
    const departamentoSelect = document.getElementById('filtro-departamento');
    const municipioSelect = document.getElementById('filtro-municipio');
    
    const filtros = {
        tecnologia: tecnologiaSelect ? tecnologiaSelect.value : 'todas',
        departamento: departamentoSelect ? departamentoSelect.value : 'todos',
        municipio: municipioSelect ? municipioSelect.value : 'todos'
    };
    
    // Calcular totales de usuarios de fallas y mantenimientos actuales
    const totalUsuariosFallas = datosFallas.reduce((sum, f) => sum + (f.usuarios_afectados || 0), 0);
    const totalUsuariosMant = datosMantenimientos.reduce((sum, m) => sum + (m.usuarios_afectados || m.usuarios || 0), 0);
    
    // Actualizar porcentaje de fallas
    const porcentajeFallas = calcularPorcentajeUsuarios(totalUsuariosFallas, filtros);
    setTextoIndicador('contador-porcentaje-fallas', formatearPorcentaje(porcentajeFallas));
    
    // Actualizar porcentaje de mantenimientos
    const porcentajeMant = calcularPorcentajeUsuarios(totalUsuariosMant, filtros);
    setTextoIndicador('contador-porcentaje-mant', formatearPorcentaje(porcentajeMant));
    
    console.log(`📊 Porcentajes actualizados - Fallas: ${formatearPorcentaje(porcentajeFallas)}, Mantenimientos: ${formatearPorcentaje(porcentajeMant)}`);
}

// ============================================
// CONFIGURAR AUTO-REFRESH CADA HORA EN PUNTO
// ============================================


function configurarAutoRefresh() {

    const ahora = new Date();

    const minutos = ahora.getMinutes();

    const segundos = ahora.getSeconds();

    

    // Calcular milisegundos hasta la próxima hora en punto

    const milisegundosHastaProximaHora = ((60 - minutos - 1) * 60 + (60 - segundos)) * 1000;

    

    // Calcular hora de próxima actualización

    const proximaHora = new Date(ahora.getTime() + milisegundosHastaProximaHora);

    const horaFormateada = proximaHora.toLocaleTimeString('es-CO', {

        hour: '2-digit',

        minute: '2-digit',

        hour12: false

    });

    

    // Mostrar en el indicador

    const elementoProximaActualizacion = document.getElementById('proxima-actualizacion');

    if (elementoProximaActualizacion) {

        elementoProximaActualizacion.textContent = horaFormateada;

    }

    

    console.log(`? Próxima actualización automática: ${horaFormateada} (en ${Math.floor(milisegundosHastaProximaHora / 1000 / 60)} minutos)`);

    

    // Primera actualización en la próxima hora en punto

    setTimeout(async () => {

        console.log('🔄 Auto-refresh: Actualizando datos (hora en punto)...');

        await Promise.all([

            cargarFallas(),

            cargarMantenimientos()

        ]);
        
        cargarTotalesUsuariosYActualizar();         // ⬅️ SIN AWAIT - NO BLOQUEA

        
        // Actualizar el indicador con la siguiente hora
        actualizarIndicadorProximaHora();

        

        // Después de la primera actualización, configurar intervalo cada hora (3600000 ms)

        setInterval(async () => {

            console.log('🔄 Auto-refresh: Actualizando datos (hora en punto)...');

            await Promise.all([

                cargarFallas(),

                cargarMantenimientos()

            ]);
            
            cargarTotalesUsuariosYActualizar();     // ⬅️ SIN AWAIT - NO BLOQUEA

            actualizarIndicadorProximaHora();

        }, 3600000);

        

    }, milisegundosHastaProximaHora);

}



// ============================================
// ACTUALIZAR INDICADOR DE PRÓXIMA HORA
// ============================================
function actualizarIndicadorProximaHora() {
    const ahora = new Date();
    const proximaHora = new Date(ahora);
    proximaHora.setHours(ahora.getHours() + 1, 0, 0, 0);
    
    const horaFormateada = proximaHora.toLocaleTimeString('es-CO', { 
        hour: '2-digit', 
        minute: '2-digit',
        hour12: false 
    });
    
    const elementoProximaActualizacion = document.getElementById('proxima-actualizacion');
    if (elementoProximaActualizacion) {
        elementoProximaActualizacion.textContent = horaFormateada;
    }
    
    console.log(`⏰ Próxima actualización programada: ${horaFormateada}`);
}

// ============================================
// INICIALIZAR MAPAS
// ============================================
function inicializarMapas() {
    console.log('??? Inicializando mapa unificado...');
    
    try {
        mapaEventos = L.map('mapa-eventos').setView(COLOMBIA_CENTER, ZOOM_INICIAL);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: 'OpenStreetMap contributors',
            maxZoom: 18
        }).addTo(mapaEventos);
        
        console.log('? Mapa de eventos inicializado');
    } catch (error) {
        console.error('? Error inicializando mapa principal:', error);
    }
}

function formatearFecha(fecha) {
    if (!fecha) return 'N/A';
    try {
        const date = new Date(fecha);
        if (isNaN(date.getTime())) {
            return fecha;
        }
        const dia = String(date.getDate()).padStart(2, '0');
        const mes = String(date.getMonth() + 1).padStart(2, '0');
        const anio = date.getFullYear();
        const hora = String(date.getHours()).padStart(2, '0');
        const minutos = String(date.getMinutes()).padStart(2, '0');
        return `${dia}/${mes}/${anio} ${hora}:${minutos}`;
    } catch (error) {
        console.error('Error formateando fecha:', error);
        return fecha;
    }
}

function formatearFechaCompleta(fecha) {
    if (!fecha) return 'N/A';
    try {
        const date = new Date(fecha);
        if (isNaN(date.getTime())) {
            return fecha;
        }
        const dia = String(date.getDate()).padStart(2, '0');
        const mes = String(date.getMonth() + 1).padStart(2, '0');
        const anio = date.getFullYear();
        const hora = String(date.getHours()).padStart(2, '0');
        const minutos = String(date.getMinutes()).padStart(2, '0');
        const segundos = String(date.getSeconds()).padStart(2, '0');
        return `${dia}/${mes}/${anio} ${hora}:${minutos}:${segundos}`;
    } catch (error) {
        console.error('Error formateando fecha completa:', error);
        return fecha;
    }
}

function formatearNumero(numero) {
    if (numero === null || numero === undefined) return '0';
    try {
        return Number(numero).toLocaleString('es-CO');
    } catch (error) {
        console.error('Error formateando numero:', error);
        return String(numero);
    }
}

function formatearPorcentaje(valor) {
    if (valor === null || valor === undefined || Number.isNaN(valor)) {
        return '0.00%';
    }
    const porcentaje = Math.min(Math.max(valor, 0), 100);
    return `${porcentaje.toFixed(2)}%`;
}

function buscarTotalPorClave(mapa, clave) {
    if (!mapa || !clave) return null;
    const claveNormalizada = normalizarClaveFiltro(clave);
    for (const [key, value] of Object.entries(mapa)) {
        if (normalizarClaveFiltro(key) === claveNormalizada) {
            return value;
        }
    }
    return null;
}

function obtenerTotalReferenciaUsuarios(filtros = {}) {
    if (!totalesUsuarios || !totalesUsuarios.total_general) {
        return 0;
    }
    
    const {
        tecnologia = 'todas',
        departamento = 'todos',
        municipio = 'todos'
    } = filtros;
    
    if (municipio && municipio !== 'todos' && departamento && departamento !== 'todos') {
        const claveMunicipio = `${departamento}|${municipio}`;
        const totalMunicipio = buscarTotalPorClave(totalesUsuarios.por_municipio, claveMunicipio);
        if (totalMunicipio !== null && totalMunicipio !== undefined) {
            return totalMunicipio;
        }
    }
    
    if (departamento && departamento !== 'todos') {
        const totalDepartamento = buscarTotalPorClave(totalesUsuarios.por_departamento, departamento);
        if (totalDepartamento !== null && totalDepartamento !== undefined) {
            return totalDepartamento;
        }
    }
    
    if (tecnologia && tecnologia !== 'todas') {
        const totalTecnologia = buscarTotalPorClave(totalesUsuarios.por_tecnologia, tecnologia);
        if (totalTecnologia !== null && totalTecnologia !== undefined) {
            return totalTecnologia;
        }
    }
    
    return totalesUsuarios.total_general || 0;
}

function calcularPorcentajeUsuarios(totalUsuarios, filtros = {}) {
    const totalReferencia = obtenerTotalReferenciaUsuarios(filtros);
    if (!totalReferencia || totalReferencia <= 0) {
        return 0;
    }
    const usuarios = Number(totalUsuarios) || 0;
    return (usuarios / totalReferencia) * 100;
}

function mostrarCargando(tbodyId, colspan) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;

    tbody.innerHTML = `
        <tr>
            <td colspan="${colspan}" class="cargando">
                <ion-icon name="sync-outline" style="font-size: 24px; animation: spin 1s linear infinite;"></ion-icon>
                <br>Cargando datos...
            </td>
        </tr>
    `;
}

function mostrarError(tbodyId, mensaje, colspan) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;

    tbody.innerHTML = `
        <tr>
            <td colspan="${colspan}" style="text-align: center; padding: 40px; color: #dc3545;">
                <ion-icon name="alert-circle-outline" style="font-size: 48px;"></ion-icon>
                <br><strong>${mensaje}</strong>
                <br><small>Intenta nuevamente en unos minutos</small>
            </td>
        </tr>
    `;
}


// ============================================
// CARGAR FALLAS ACTIVAS
// ============================================
async function cargarFallas() {
    try {
        console.log('?? Cargando fallas...');
        mostrarCargando('tbody-fallas', 9);
        
        const response = await fetch('/api/fallas-activas');
        
        if (!response.ok) {
            throw new Error(`Error HTTP: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('?? Datos de fallas recibidos:', data);
        
        datosFallas = data.fallas || [];
        console.log(`? ${datosFallas.length} fallas cargadas`);
        
        actualizarIndicadoresFallas(datosFallas, data.total_usuarios_afectados || 0);
        actualizarFechaCarga('fecha-ultima-carga-fallas', data.fecha_ultima_carga);
        
        filtrarEventos();
        console.log('? Fallas cargadas correctamente');
        
    } catch (error) {
        console.error('? Error cargando fallas:', error);
        mostrarError('tbody-fallas', 'Error al cargar las fallas activas', 9);
        actualizarIndicadoresFallas([], 0);
        actualizarFechaCarga('fecha-ultima-carga-fallas', 'Error');
    }
}

// ============================================
// CARGAR MANTENIMIENTOS
// ============================================
async function cargarMantenimientos() {
    try {
        console.log('📄 Cargando mantenimientos...');
        mostrarCargando('tbody-mantenimientos', 10); // ← Cambiado a 10
        
        const response = await fetch('/api/mantenimientos-activos');
        
        if (!response.ok) {
            throw new Error(`Error HTTP: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('📦 Datos de mantenimientos recibidos:', data);
        
        datosMantenimientos = data.mantenimientos || [];
        console.log(`✅ ${datosMantenimientos.length} mantenimientos cargados`);
        
        actualizarIndicadoresMantenimientos(datosMantenimientos);
        actualizarFechaCarga('fecha-ultima-carga-mant', data.fecha_ultima_carga);
        
        filtrarEventos();
        console.log('✅ Mantenimientos cargados correctamente');
        
    } catch (error) {
        console.error('❌ Error cargando mantenimientos:', error);
        mostrarError('tbody-mantenimientos', 'Error al cargar los mantenimientos', 10); // ← Cambiado a 10
        actualizarIndicadoresMantenimientos([]);
        actualizarFechaCarga('fecha-ultima-carga-mant', 'Error');
    }
}

// ============================================
// MAPA Y POPUPS UNIFICADOS
// ============================================
function limpiarMarcadores(lista) {
    if (!mapaEventos) {
        return [];
    }
    lista.forEach(marker => mapaEventos.removeLayer(marker));
    return [];
}

function obtenerHorasMantenimiento(mantenimiento) {
    if (mantenimiento.tiempo_afectacion_hrs != null) {
        return mantenimiento.tiempo_afectacion_hrs;
    }
    if (!mantenimiento.fecha_inicio) {
        return 0;
    }
    const inicio = new Date(mantenimiento.fecha_inicio);
    if (isNaN(inicio.getTime())) {
        return 0;
    }
    const ahora = new Date();
    const horas = (ahora.getTime() - inicio.getTime()) / (1000 * 60 * 60);
    return Math.max(horas, 0);
}

function construirPopupFalla(falla, tiempoAfectacion, claseSemaforo, iconoSemaforo) {
    return `
        <div class="popup-content">
            <div class="popup-header">
                <ion-icon name="alert-circle" style="color: #dc3545; font-size: 24px;"></ion-icon>
                <h4 style="margin: 0 0 0 10px; color: #dc3545;">Falla Activa</h4>
            </div>
            <div class="popup-body">
                <div class="popup-row">
                    <span class="popup-label">TICKET:</span>
                    <span class="popup-value">${falla.ticket}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">ESTACION BASE:</span>
                    <span class="popup-value">${falla.estacion_base || 'N/A'}</span>
                </div>
                ${falla.description ? `
                <div class="popup-row">
                    <span class="popup-label">NOMBRE SITIO:</span>
                    <span class="popup-value">${falla.description}</span>
                </div>
                ` : ''}
                <div class="popup-row">
                    <span class="popup-label">MUNICIPIO:</span>
                    <span class="popup-value">${falla.municipio || 'N/A'}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">DEPARTAMENTO:</span>
                    <span class="popup-value">${falla.departamento || 'N/A'}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">LATITUD:</span>
                    <span class="popup-value">${falla.latitud ? falla.latitud.toFixed(4) : 'N/A'}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">LONGITUD:</span>
                    <span class="popup-value">${falla.longitud ? falla.longitud.toFixed(4) : 'N/A'}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">TECNOLOGIA:</span>
                    <span class="popup-value">${falla.tecnologia || 'N/A'}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">USUARIOS AFECT.:</span>
                    <span class="popup-value" style="color: #6f42c1; font-weight: 700;">${formatearNumero(falla.usuarios_afectados || 0)}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">TIEMPO AFECT.:</span>
                    <span class="popup-value">
                        <span class="tiempo-afectacion ${claseSemaforo}" style="padding: 4px 8px; font-size: 11px;">
                            ${iconoSemaforo} ${tiempoAfectacion.toFixed(1)}h
                        </span>
                    </span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">FECHA INICIO:</span>
                    <span class="popup-value">${formatearFecha(falla.fecha_inicio)}</span>
                </div>
                ${falla.estado ? `
                <div class="popup-row">
                    <span class="popup-label">ESTADO:</span>
                    <span class="popup-value">${falla.estado}</span>
                </div>
                ` : ''}
                ${falla.location ? `
                <div class="popup-row">
                    <span class="popup-label">UBICACION:</span>
                    <span class="popup-value">${falla.location}</span>
                </div>
                ` : ''}
            </div>
        </div>
    `;
}

function construirPopupMantenimiento(mant, horasActivas, claseSemaforo, iconoSemaforo) {
    return `
        <div class="popup-content">
            <div class="popup-header">
                <ion-icon name="construct" style="color: #00a0c6; font-size: 24px;"></ion-icon>
                <h4 style="margin: 0 0 0 10px; color: #007a9e;">Mantenimiento Programado</h4>
            </div>
            <div class="popup-body">
                <div class="popup-row">
                    <span class="popup-label">BTP:</span>
                    <span class="popup-value">${mant.ticket}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">ESTACION BASE:</span>
                    <span class="popup-value">${mant.estacion_base || 'N/A'}</span>
                </div>
                ${mant.nombre_sitio ? `
                <div class="popup-row">
                    <span class="popup-label">NOMBRE SITIO:</span>
                    <span class="popup-value">${mant.nombre_sitio}</span>
                </div>
                ` : ''}
                <div class="popup-row">
                    <span class="popup-label">MUNICIPIO:</span>
                    <span class="popup-value">${mant.municipio || 'N/A'}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">DEPARTAMENTO:</span>
                    <span class="popup-value">${mant.departamento || 'N/A'}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">LATITUD:</span>
                    <span class="popup-value">${mant.latitud ? mant.latitud.toFixed(4) : 'N/A'}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">LONGITUD:</span>
                    <span class="popup-value">${mant.longitud ? mant.longitud.toFixed(4) : 'N/A'}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">TECNOLOGIA:</span>
                    <span class="popup-value">${mant.tecnologia || 'N/A'}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">USUARIOS AFECT.:</span>
                    <span class="popup-value" style="color: #6f42c1; font-weight: 700;">${formatearNumero(mant.usuarios_afectados || 0)}</span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">TIEMPO ACTIVO:</span>
                    <span class="popup-value">
                        <span class="tiempo-afectacion ${claseSemaforo}" style="padding: 4px 8px; font-size: 11px;">
                            ${iconoSemaforo} ${horasActivas.toFixed(1)}h
                        </span>
                    </span>
                </div>
                <div class="popup-row">
                    <span class="popup-label">FECHA INICIO:</span>
                    <span class="popup-value">${formatearFecha(mant.fecha_inicio)}</span>
                </div>
                ${mant.fecha_fin_programado ? `
                <div class="popup-row">
                    <span class="popup-label">FECHA FIN PROG.:</span>
                    <span class="popup-value">${formatearFecha(mant.fecha_fin_programado)}</span>
                </div>
                ` : ''}
                ${mant.grupo_ejecutor ? `
                <div class="popup-row">
                    <span class="popup-label">GRUPO EJECUTOR:</span>
                    <span class="popup-value">${mant.grupo_ejecutor}</span>
                </div>
                ` : ''}
                ${mant.description_ot ? `
                <div class="popup-row">
                    <span class="popup-label">DESCRIPCION:</span>
                    <span class="popup-value">${mant.description_ot}</span>
                </div>
                ` : ''}
                ${mant.estado ? `
                <div class="popup-row">
                    <span class="popup-label">ESTADO:</span>
                    <span class="popup-value">${mant.estado}</span>
                </div>
                ` : ''}
            </div>
        </div>
    `;
}

function actualizarMapaEventos(fallas, mantenimientos) {
    if (!mapaEventos) {
        return;
    }
    
    markersFallas = limpiarMarcadores(markersFallas);
    markersMantenimientos = limpiarMarcadores(markersMantenimientos);
    
    const todosLosMarcadores = [];
    
    fallas.forEach(falla => {
        if (!falla.latitud || !falla.longitud) {
            console.warn('?? Falla sin coordenadas:', falla.ticket);
            return;
        }
        const tiempoAfectacion = falla.tiempo_afectacion_hrs || 0;
        const marker = L.marker([falla.latitud, falla.longitud], {
            icon: crearIconoFalla(falla.tecnologia, tiempoAfectacion)
        }).addTo(mapaEventos);
        
        const claseSemaforo = obtenerClaseSemaforo(tiempoAfectacion);
        const iconoSemaforo = obtenerIconoSemaforo(tiempoAfectacion);
        marker.bindPopup(construirPopupFalla(falla, tiempoAfectacion, claseSemaforo, iconoSemaforo), {
            maxWidth: 350,
            className: 'custom-popup-falla'
        });

        markersFallas.push(marker);
        todosLosMarcadores.push(marker);
    });
    
    mantenimientos.forEach(mant => {
        if (!mant.latitud || !mant.longitud) {
            console.warn('?? Mantenimiento sin coordenadas:', mant.ticket);
            return;
        }
        const horasActivas = obtenerHorasMantenimiento(mant);
        const marker = L.marker([mant.latitud, mant.longitud], {
            icon: crearIconoMantenimiento(mant.tecnologia, horasActivas)
        }).addTo(mapaEventos);
        
        const claseSemaforo = obtenerClaseSemaforo(horasActivas);
        const iconoSemaforo = obtenerIconoSemaforo(horasActivas);
        marker.bindPopup(construirPopupMantenimiento(mant, horasActivas, claseSemaforo, iconoSemaforo), {
            maxWidth: 350,
            className: 'custom-popup-mantenimiento'
        });

        markersMantenimientos.push(marker);
        todosLosMarcadores.push(marker);
    });
    
    if (todosLosMarcadores.length > 0) {
        const group = L.featureGroup(todosLosMarcadores);
        mapaEventos.fitBounds(group.getBounds().pad(0.12));
    } else {
        mapaEventos.setView(COLOMBIA_CENTER, ZOOM_INICIAL);
    }
}

// ============================================
// ACTUALIZAR TABLA DE FALLAS
// ============================================
function actualizarTablaFallas(fallas) {
    const tbody = document.getElementById('tbody-fallas');
    tbody.innerHTML = '';
    
    if (fallas.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" style="text-align: center; padding: 40px; color: #6c757d;">
                    <ion-icon name="checkmark-circle-outline" style="font-size: 48px; color: #28a745;"></ion-icon>
                    <br>No hay fallas activas en este momento
                </td>
            </tr>
        `;
        // Recalcular altura después de agregar mensaje
        setTimeout(recalcularAlturasColapsables, 50);
        return;
    }
    
    fallas.forEach(falla => {
        const tiempoAfectacion = falla.tiempo_afectacion_hrs || 0;
        const claseSemaforo = obtenerClaseSemaforo(tiempoAfectacion);
        const iconoSemaforo = obtenerIconoSemaforo(tiempoAfectacion);
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${falla.ticket}</td>
            <td>${falla.estacion_base || 'N/A'}</td>
            <td>${falla.description || 'N/A'}</td>
            <td>${formatearFecha(falla.fecha_inicio)}</td>
            <td>${falla.municipio}</td>
            <td>${falla.departamento || 'N/A'}</td>
            <td>${falla.tecnologia}</td>
            <td>${formatearNumero(falla.usuarios_afectados || 0)}</td>
            <td>
                <span class="tiempo-afectacion ${claseSemaforo}">
                    ${iconoSemaforo} ${tiempoAfectacion.toFixed(1)}h
                </span>
            </td>
        `;
        
        // Hacer clic en la fila para centrar en el mapa
        if (falla.latitud && falla.longitud) {
            row.style.cursor = 'pointer';
            row.addEventListener('click', () => {
                centrarEnMarcador('falla', falla.latitud, falla.longitud);
            });
        }
        
        tbody.appendChild(row);
    });
    // ✅ AGREGAR ESTO AL FINAL
    setTimeout(recalcularAlturasColapsables, 50);
}

// ============================================
// ACTUALIZAR TABLA DE MANTENIMIENTOS
// ============================================
function actualizarTablaMantenimientos(mantenimientos) {
    const tbody = document.getElementById('tbody-mantenimientos');
    tbody.innerHTML = '';
    
    if (mantenimientos.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="10" style="text-align: center; padding: 40px; color: #6c757d;">
                    <ion-icon name="checkmark-circle-outline" style="font-size: 48px; color: #28a745;"></ion-icon>
                    <br>No hay mantenimientos programados en este momento
                </td>
            </tr>
        `;
        // Recalcular altura después de agregar mensaje
        setTimeout(recalcularAlturasColapsables, 50);
        return;
    }
    
    mantenimientos.forEach(mant => {
        const horasActivas = obtenerHorasMantenimiento(mant);
        const claseSemaforo = obtenerClaseSemaforo(horasActivas);
        const iconoSemaforo = obtenerIconoSemaforo(horasActivas);
        const usuarios = mant.usuarios_afectados || 0;
        const nombreSitio = mant.nombre_sitio || 'N/A';
        const estacionBase = mant.estacion_base || 'N/A';
        const btp = mant.ticket || 'N/A';
        const fechaFinProgramado = mant.fecha_fin_programado ? formatearFecha(mant.fecha_fin_programado) : 'N/A';
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${btp}</td>
            <td>${estacionBase}</td>
            <td>${nombreSitio}</td>
            <td>${formatearFecha(mant.fecha_inicio)}</td>
            <td>${mant.municipio || 'N/A'}</td>
            <td>${mant.departamento || 'N/A'}</td>
            <td>${mant.tecnologia || 'N/A'}</td>
            <td>${formatearNumero(usuarios)}</td>
            <td>
                <span class="tiempo-afectacion ${claseSemaforo}">
                    ${iconoSemaforo} ${horasActivas.toFixed(1)}h
                </span>
            </td>
            <td>${fechaFinProgramado}</td>
        `;
        
        if (mant.latitud && mant.longitud) {
            row.style.cursor = 'pointer';
            row.addEventListener('click', () => {
                centrarEnMarcador('mantenimiento', mant.latitud, mant.longitud);
            });
        }
        
        tbody.appendChild(row);
    });
    // ✅ AGREGAR ESTO AL FINAL
    setTimeout(recalcularAlturasColapsables, 50);
}


// ============================================
// INDICADORES Y FILTROS UNIFICADOS
// ============================================
function obtenerConteoTecnologia(lista) {
    const conteo = { '3G': 0, '4G': 0, '5G': 0 };
    lista.forEach(item => {
        if (conteo.hasOwnProperty(item.tecnologia)) {
            conteo[item.tecnologia] += 1;
        }
    });
    return conteo;
}

function obtenerConfigSemaforo(horas) {
    const valorNumerico = Number(horas);
    const valor = Number.isFinite(valorNumerico) ? valorNumerico : 0;
    return SEMAFORO_ESCALAS.find(item => valor < item.limite) || SEMAFORO_ESCALAS[SEMAFORO_ESCALAS.length - 1];
}

function obtenerColorSemaforo(horas) {
    return obtenerConfigSemaforo(horas).color;
}

function obtenerClaseSemaforo(horas) {
    return obtenerConfigSemaforo(horas).clase;
}

function obtenerIconoSemaforo(horas) {
    const config = obtenerConfigSemaforo(horas);
    return `<span class="semaforo-icon" style="color: ${config.color};">&#9679;</span>`;
}

function obtenerConteoSemaforo(lista, obtenerHoras) {
    const conteo = { verde: 0, amarillo: 0, naranja: 0, cafe: 0, rojo: 0 };
    lista.forEach(item => {
        const horas = obtenerHoras(item);
        if (horas < 4) conteo.verde += 1;
        else if (horas < 12) conteo.amarillo += 1;
        else if (horas < 24) conteo.naranja += 1;
        else if (horas < 72) conteo.cafe += 1;
        else conteo.rojo += 1;
    });
    return conteo;
}

function setTextoIndicador(id, valor) {
    const elemento = document.getElementById(id);
    if (!elemento) {
        console.warn(`Elemento con id "${id}" no encontrado al actualizar indicadores.`);
        return;
    }
    elemento.textContent = valor;
}

function actualizarIndicadoresFallas(fallas, totalUsuarios, filtros = {}) {
    setTextoIndicador('contador-fallas', fallas.length);
    setTextoIndicador('contador-usuarios', formatearNumero(totalUsuarios || 0));
    const porcentaje = calcularPorcentajeUsuarios(totalUsuarios || 0, filtros);
    setTextoIndicador('contador-porcentaje-fallas', formatearPorcentaje(porcentaje));
    
    const conteoTecnologia = obtenerConteoTecnologia(fallas);
    setTextoIndicador('contador-3g', conteoTecnologia['3G'] || 0);
    setTextoIndicador('contador-4g', conteoTecnologia['4G'] || 0);
    setTextoIndicador('contador-5g', conteoTecnologia['5G'] || 0);
    
    const conteoSemaforo = obtenerConteoSemaforo(fallas, falla => falla.tiempo_afectacion_hrs || 0);
    setTextoIndicador('contador-verde', conteoSemaforo.verde);
    setTextoIndicador('contador-amarillo', conteoSemaforo.amarillo);
    setTextoIndicador('contador-naranja', conteoSemaforo.naranja);
    setTextoIndicador('contador-cafe', conteoSemaforo.cafe);
    setTextoIndicador('contador-rojo', conteoSemaforo.rojo);
}

function actualizarIndicadoresMantenimientos(mantenimientos, filtros = {}) {
    setTextoIndicador('contador-mant-total', mantenimientos.length);
    const totalUsuarios = mantenimientos.reduce((total, mant) => total + (mant.usuarios_afectados || mant.usuarios || 0), 0);
    setTextoIndicador('contador-mant-usuarios', formatearNumero(totalUsuarios));
    const porcentaje = calcularPorcentajeUsuarios(totalUsuarios || 0, filtros);
    setTextoIndicador('contador-porcentaje-mant', formatearPorcentaje(porcentaje));
    
    const conteoTecnologia = obtenerConteoTecnologia(mantenimientos);
    setTextoIndicador('contador-mant-3g', conteoTecnologia['3G'] || 0);
    setTextoIndicador('contador-mant-4g', conteoTecnologia['4G'] || 0);
    setTextoIndicador('contador-mant-5g', conteoTecnologia['5G'] || 0);
    
    const conteoSemaforo = obtenerConteoSemaforo(mantenimientos, obtenerHorasMantenimiento);
    setTextoIndicador('contador-mant-verde', conteoSemaforo.verde);
    setTextoIndicador('contador-mant-amarillo', conteoSemaforo.amarillo);
    setTextoIndicador('contador-mant-naranja', conteoSemaforo.naranja);
    setTextoIndicador('contador-mant-cafe', conteoSemaforo.cafe);
    setTextoIndicador('contador-mant-rojo', conteoSemaforo.rojo);
}

function actualizarFechaCarga(elementId, fecha) {
    const elemento = document.getElementById(elementId);
    if (!elemento) return;
    
    if (!fecha) {
        elemento.textContent = 'No disponible';
        return;
    }
    
    try {
        elemento.textContent = formatearFechaCompleta(fecha);
    } catch (error) {
        console.error('Error formateando fecha:', error);
        elemento.textContent = fecha;
    }
}

function obtenerTextoOpcionTodos(select, fallback) {
    if (!select) return fallback;
    if (!select.dataset.textoTodos) {
        const opcionTodos = select.querySelector('option[value="todos"]');
        if (opcionTodos) {
            select.dataset.textoTodos = opcionTodos.textContent.trim();
        }
    }
    return select.dataset.textoTodos || fallback;
}

function normalizarClaveFiltro(valor) {
    return (valor || '').toString().trim().toUpperCase();
}

function actualizarFiltroDepartamentos(selectId, dataset) {
    const select = document.getElementById(selectId);
    if (!select) return;
    
    const valorAnterior = select.value || 'todos';
    const textoTodos = obtenerTextoOpcionTodos(select, 'Todos los departamentos');
    
    const mapaDepartamentos = new Map();
    dataset.forEach(item => {
        const original = (item.departamento || '').toString().trim();
        if (!original || original.toUpperCase() === 'N/A') {
            return;
        }
        const clave = normalizarClaveFiltro(original);
        if (!mapaDepartamentos.has(clave)) {
            mapaDepartamentos.set(clave, original);
        }
    });
    
    const opcionesOrdenadas = Array.from(mapaDepartamentos.values())
        .sort((a, b) => a.localeCompare(b, 'es', { sensitivity: 'base' }));
    
    select.innerHTML = '';
    
    const opcionTodos = document.createElement('option');
    opcionTodos.value = 'todos';
    opcionTodos.textContent = textoTodos;
    select.appendChild(opcionTodos);
    
    opcionesOrdenadas.forEach(dep => {
        const option = document.createElement('option');
        option.value = dep;
        option.textContent = dep;
        select.appendChild(option);
    });
    
    if (valorAnterior !== 'todos' && mapaDepartamentos.has(normalizarClaveFiltro(valorAnterior))) {
        select.value = valorAnterior;
    } else {
        select.value = 'todos';
    }
}

function actualizarFiltroMunicipios(selectId, dataset, departamentoSeleccionado) {
    const select = document.getElementById(selectId);
    if (!select) return;
    
    const valorAnterior = select.value || 'todos';
    const textoTodos = obtenerTextoOpcionTodos(select, 'Todos los municipios');
    const departamentoNormalizado = normalizarClaveFiltro(departamentoSeleccionado);
    
    const mapaMunicipios = new Map();
    dataset.forEach(item => {
        const departamentoItem = normalizarClaveFiltro(item.departamento);
        if (departamentoSeleccionado !== 'todos' && departamentoItem !== departamentoNormalizado) {
            return;
        }
        
        const original = (item.municipio || '').toString().trim();
        if (!original || original.toUpperCase() === 'N/A') {
            return;
        }
        const clave = normalizarClaveFiltro(original);
        if (!mapaMunicipios.has(clave)) {
            mapaMunicipios.set(clave, original);
        }
    });
    
    const opcionesOrdenadas = Array.from(mapaMunicipios.values())
        .sort((a, b) => a.localeCompare(b, 'es', { sensitivity: 'base' }));
    
    select.innerHTML = '';
    
    const opcionTodos = document.createElement('option');
    opcionTodos.value = 'todos';
    opcionTodos.textContent = textoTodos;
    select.appendChild(opcionTodos);
    
    opcionesOrdenadas.forEach(mun => {
        const option = document.createElement('option');
        option.value = mun;
        option.textContent = mun;
        select.appendChild(option);
    });
    
    if (valorAnterior !== 'todos' && mapaMunicipios.has(normalizarClaveFiltro(valorAnterior))) {
        select.value = valorAnterior;
    } else {
        select.value = 'todos';
    }
}

function obtenerDatosParaFiltros(tipo) {
    if (tipo === 'fallas') return datosFallas;
    if (tipo === 'mantenimientos') return datosMantenimientos;
    return [...datosFallas, ...datosMantenimientos];
}

function cumpleFiltroSemaforo(valor, filtro) {
    switch (filtro) {
        case 'verde': return valor < 4;
        case 'amarillo': return valor >= 4 && valor < 12;
        case 'naranja': return valor >= 12 && valor < 24;
        case 'cafe': return valor >= 24 && valor < 72;
        case 'rojo': return valor >= 72;
        default: return true;
    }
}

function filtrarEventos() {
    try {
        const tipo = document.getElementById('filtro-tipo-evento').value || 'ambos';
        const tecnologia = document.getElementById('filtro-tecnologia').value || 'todas';
        const datasetFiltros = obtenerDatosParaFiltros(tipo);
        
        actualizarFiltroDepartamentos('filtro-departamento', datasetFiltros);
        const departamento = document.getElementById('filtro-departamento').value;
        actualizarFiltroMunicipios('filtro-municipio', datasetFiltros, departamento);
        const municipio = document.getElementById('filtro-municipio').value;
        const semaforo = document.getElementById('filtro-semaforo').value || 'todos';
        
        tipoEventoSeleccionado = tipo;
        
        let fallasFiltradas = datosFallas.slice();
        let mantenimientosFiltrados = datosMantenimientos.slice();
        
        if (tecnologia !== 'todas') {
            fallasFiltradas = fallasFiltradas.filter(f => f.tecnologia === tecnologia);
            mantenimientosFiltrados = mantenimientosFiltrados.filter(m => m.tecnologia === tecnologia);
        }
        
        if (departamento !== 'todos') {
            fallasFiltradas = fallasFiltradas.filter(f => normalizarClaveFiltro(f.departamento) === normalizarClaveFiltro(departamento));
            mantenimientosFiltrados = mantenimientosFiltrados.filter(m => normalizarClaveFiltro(m.departamento) === normalizarClaveFiltro(departamento));
        }
        
        if (municipio !== 'todos') {
            fallasFiltradas = fallasFiltradas.filter(f => normalizarClaveFiltro(f.municipio) === normalizarClaveFiltro(municipio));
            mantenimientosFiltrados = mantenimientosFiltrados.filter(m => normalizarClaveFiltro(m.municipio) === normalizarClaveFiltro(municipio));
        }
        
        if (semaforo !== 'todos') {
            fallasFiltradas = fallasFiltradas.filter(f => cumpleFiltroSemaforo(f.tiempo_afectacion_hrs || 0, semaforo));
            mantenimientosFiltrados = mantenimientosFiltrados.filter(m => cumpleFiltroSemaforo(obtenerHorasMantenimiento(m), semaforo));
        }
        
        if (tipo === 'fallas') {
            mantenimientosFiltrados = [];
        } else if (tipo === 'mantenimientos') {
            fallasFiltradas = [];
        }
        
        const fallasParaMapa = tipo === 'mantenimientos' ? [] : fallasFiltradas;
        const mantenimientosParaMapa = tipo === 'fallas' ? [] : mantenimientosFiltrados;
        actualizarMapaEventos(fallasParaMapa, mantenimientosParaMapa);
        
        actualizarTablaFallas(fallasFiltradas);
        actualizarTablaMantenimientos(mantenimientosFiltrados);
        
        const totalUsuariosFallas = fallasFiltradas.reduce((total, falla) => total + (falla.usuarios_afectados || 0), 0);
        const filtrosAplicados = { tecnologia, departamento, municipio };
        actualizarIndicadoresFallas(fallasFiltradas, totalUsuariosFallas, filtrosAplicados);
        actualizarIndicadoresMantenimientos(mantenimientosFiltrados, filtrosAplicados);
        
        console.log('?? Filtrado aplicado', {
            tipo,
            tecnologia,
            departamento,
            municipio,
            semaforo,
            fallas: fallasFiltradas.length,
            mantenimientos: mantenimientosFiltrados.length
        });
    } catch (error) {
        console.error('Error aplicando filtros:', error);
    }
}

function resetearFiltrosEventos() {
    const tipoSelect = document.getElementById('filtro-tipo-evento');
    const tecnologiaSelect = document.getElementById('filtro-tecnologia');
    const departamentoSelect = document.getElementById('filtro-departamento');
    const municipioSelect = document.getElementById('filtro-municipio');
    const semaforoSelect = document.getElementById('filtro-semaforo');
    
    if (tipoSelect) tipoSelect.value = 'ambos';
    if (tecnologiaSelect) {
        tecnologiaSelect.value = 'todas';
        const iconKey = tecnologiaSelect.dataset.iconKey || tecnologiaSelect.id;
        actualizarSelectTecnologiaVisual(iconKey);
    }
    if (departamentoSelect) departamentoSelect.value = 'todos';
    if (municipioSelect) municipioSelect.value = 'todos';
    if (semaforoSelect) semaforoSelect.value = 'todos';
    
    filtrarEventos();
}
function centrarEnMarcador(tipo, lat, lon) {
    if (!mapaEventos || lat == null || lon == null) {
        return;
    }

    mapaEventos.setView([lat, lon], 12);

    const markers = tipo === 'mantenimiento' ? markersMantenimientos : markersFallas;
    markers.forEach(marker => {
        const markerPos = marker.getLatLng();
        if (Math.abs(markerPos.lat - lat) < 0.0001 && Math.abs(markerPos.lng - lon) < 0.0001) {
            marker.openPopup();
        }
    });

    const mapaElement = document.getElementById('mapa-eventos');
    if (mapaElement) {
        mapaElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}



function obtenerFormaTecnologia(tecnologia) {
    const formas = {
        '3G': 'triangulo',
        '4G': 'circulo',
        '5G': 'cuadrado'
    };
    return formas[tecnologia] || 'cuadrado';
}

function construirSvgIcono(forma, color, size = 32, variante = 'alerta') {
    let figura;
    switch (forma) {
        case 'triangulo':
            figura = `<path d="M20 5 L36 34 H4 Z" fill="${color}" />`;
            break;
        case 'cuadrado':
            figura = `<rect x="6" y="6" width="28" height="28" rx="6" fill="${color}" />`;
            break;
        default:
            figura = `<circle cx="20" cy="20" r="18" fill="${color}" />`;
            break;
    }

    let contenido;
    if (variante === 'mantenimiento') {
        const fontSize = Math.round(size * 0.48);
        contenido = `<text x="20" y="24" text-anchor="middle" dominant-baseline="middle" font-size="${fontSize}" font-family="Segoe UI, sans-serif" fill="#ffffff">🛠</text>`;
    } else {
        contenido = `<rect x="18" y="11" width="4" height="14" rx="2" fill="#ffffff"/><circle cx="20" cy="29" r="3" fill="#ffffff"/>`;
    }

    return `
        <svg width="${size}" height="${size}" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
            ${figura}
            ${contenido}
        </svg>
    `;
}

function crearIconoFalla(tecnologia, tiempoAfectacion) {
    const color = obtenerColorSemaforo(tiempoAfectacion || 0);
    const forma = obtenerFormaTecnologia(tecnologia);
    const svgIcon = construirSvgIcono(forma, color, 32, 'alerta');

    return L.divIcon({
        className: 'custom-icon',
        html: svgIcon,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
        popupAnchor: [0, -16]
    });
}

function crearIconoMantenimiento(tecnologia, horasActivas) {
    const color = obtenerColorSemaforo(horasActivas || 0);
    const forma = obtenerFormaTecnologia(tecnologia);
    const svgIcon = construirSvgIcono(forma, color, 32, 'mantenimiento');

    return L.divIcon({
        className: 'custom-icon',
        html: svgIcon,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
        popupAnchor: [0, -16]
    });
}

function generarHtmlOpcionTecnologia(value, label) {
    const color = COLORES_ICONO_TECNOLOGIA[value];
    if (!color) {
        return `<span class="select-icon-label">${label}</span>`;
    }

    const forma = obtenerFormaTecnologia(value);
    const svg = construirSvgIcono(forma, color, 22, 'alerta');
    const textoLimpio = label.replace(/^[^0-9A-Za-z]+/, '').trim() || label;

    return `<span class="select-icon-thumb">${svg}</span><span class="select-icon-label">${textoLimpio}</span>`;
}

function inicializarSelectsTecnologia() {
    const selects = document.querySelectorAll('select.select-icon-tecnologia');

    selects.forEach(select => {
        if (!select || select.dataset.iconified === 'true') return;
        select.dataset.iconified = 'true';

        const wrapper = document.createElement('div');
        wrapper.className = 'select-icon-wrapper';

        const parent = select.parentNode;
        parent.insertBefore(wrapper, select);
        wrapper.appendChild(select);
        select.classList.add('select-icon-original');
        select.tabIndex = -1;
        select.setAttribute('aria-hidden', 'true');

        const display = document.createElement('button');
        display.type = 'button';
        display.className = 'select-icon-display';
        display.setAttribute('aria-haspopup', 'listbox');
        display.setAttribute('aria-expanded', 'false');

        const displayContent = document.createElement('span');
        displayContent.className = 'select-icon-display-content';

        const arrow = document.createElement('span');
        arrow.className = 'select-icon-arrow';
        arrow.innerHTML = '&#9662;';

        display.appendChild(displayContent);
        display.appendChild(arrow);
        wrapper.appendChild(display);

        const optionsList = document.createElement('ul');
        optionsList.className = 'select-icon-options';
        optionsList.setAttribute('role', 'listbox');
        wrapper.appendChild(optionsList);

        const optionItems = Array.from(select.options).map(option => ({
            value: option.value,
            label: option.text,
            html: generarHtmlOpcionTecnologia(option.value, option.text)
        }));
        const selectKey = (select.id && select.id.trim()) ? select.id : `select-icon-${selectIconStates.size + 1}`;
        select.dataset.iconKey = selectKey;

        function closeDropdown() {
            wrapper.classList.remove('open');
            display.setAttribute('aria-expanded', 'false');
        }

        function openDropdown() {
            document.querySelectorAll('.select-icon-wrapper.open').forEach(openWrapper => {
                if (openWrapper !== wrapper) {
                    openWrapper.classList.remove('open');
                    const button = openWrapper.querySelector('.select-icon-display');
                    if (button) {
                        button.setAttribute('aria-expanded', 'false');
                    }
                }
            });
            wrapper.classList.add('open');
            display.setAttribute('aria-expanded', 'true');
        }

        function renderOptions() {
            optionsList.innerHTML = '';
            optionItems.forEach(item => {
                const li = document.createElement('li');
                li.className = 'select-icon-option';
                li.innerHTML = item.html;
                li.dataset.value = item.value;
                li.setAttribute('role', 'option');
                if (item.value === select.value) {
                    li.classList.add('selected');
                    li.setAttribute('aria-selected', 'true');
                }

                li.addEventListener('click', () => {
                    const hasChanged = select.value !== item.value;
                    select.value = item.value;
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                    if (!hasChanged) {
                        actualizarSelectTecnologiaVisual(selectKey);
                    }
                    closeDropdown();
                });

                optionsList.appendChild(li);
            });
        }

        function updateDisplay(value) {
            const current = optionItems.find(item => item.value === value) || optionItems[0];
            displayContent.innerHTML = current ? current.html : '';
            optionsList.querySelectorAll('.select-icon-option').forEach(li => {
                const isSelected = li.dataset.value === value;
                li.classList.toggle('selected', isSelected);
                if (isSelected) {
                    li.setAttribute('aria-selected', 'true');
                } else {
                    li.removeAttribute('aria-selected');
                }
            });
        }

        renderOptions();
        updateDisplay(select.value);

        display.addEventListener('click', () => {
            if (wrapper.classList.contains('open')) {
                closeDropdown();
            } else {
                openDropdown();
            }
        });

        display.addEventListener('keydown', (event) => {
            const keys = ['ArrowDown', 'ArrowUp', 'Enter', ' ', 'Escape'];
            if (!keys.includes(event.key)) return;

            const currentIndex = optionItems.findIndex(item => item.value === select.value);

            if (event.key === 'ArrowDown') {
                event.preventDefault();
                const nextIndex = (currentIndex + 1) % optionItems.length;
                select.value = optionItems[nextIndex].value;
                select.dispatchEvent(new Event('change', { bubbles: true }));
            } else if (event.key === 'ArrowUp') {
                event.preventDefault();
                const prevIndex = (currentIndex - 1 + optionItems.length) % optionItems.length;
                select.value = optionItems[prevIndex].value;
                select.dispatchEvent(new Event('change', { bubbles: true }));
            } else if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                if (wrapper.classList.contains('open')) {
                    closeDropdown();
                } else {
                    openDropdown();
                }
            } else if (event.key === 'Escape') {
                event.preventDefault();
                closeDropdown();
            }
        });

        document.addEventListener('click', (event) => {
            if (!wrapper.contains(event.target)) {
                closeDropdown();
            }
        });

        select.addEventListener('change', () => {
            updateDisplay(select.value);
        });

        selectIconStates.set(selectKey, {
            select,
            refresh: () => updateDisplay(select.value)
        });
    });
}

function actualizarSelectTecnologiaVisual(selectKey) {
    const state = selectIconStates.get(selectKey);
    if (state && typeof state.refresh === 'function') {
        state.refresh();
    }
}



// ============================================
// ESTILOS CSS PARA ANIMACIÓN
// ============================================
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
    
    @keyframes dots {
        0%, 20% { content: '.'; }
        40% { content: '..'; }
        60%, 100% { content: '...'; }
    }
    
    .calculando-porcentaje {
        font-size: 0.8em !important;
        color: #6c757d !important;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }
    
    .calculando-porcentaje::after {
        content: '...';
        animation: dots 1.5s infinite;
        display: inline-block;
        width: 1.5em;
        text-align: left;
    }
    
    .popup-content {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    .popup-header {
        display: flex;
        align-items: center;
        border-bottom: 2px solid #e9ecef;
        padding-bottom: 10px;
        margin-bottom: 10px;
    }
    
    .popup-body {
        max-height: 400px;
        overflow-y: auto;
    }
    
    .popup-row {
        display: flex;
        justify-content: space-between;
        padding: 6px 0;
        border-bottom: 1px solid #f8f9fa;
    }
    
    .popup-row:last-child {
        border-bottom: none;
    }
    
    .popup-label {
        font-weight: 600;
        color: #495057;
        font-size: 12px;
        flex: 0 0 45%;
    }
    
    .popup-value {
        color: #212529;
        font-size: 12px;
        text-align: right;
        flex: 0 0 55%;
        word-break: break-word;
    }
    
    .tiempo-afectacion {
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 11px;
        display: inline-block;
    }
    
    .semaforo-verde {
        background-color: #d4edda;
        color:#00a152;
        border: 1px solid #c3e6cb;
    }
    
    .semaforo-amarillo {
        background-color: #fff3cd;
        color:#ffc107;
        border: 1px solid #ffeaa7;
    }
    
    .semaforo-naranja {
        background-color: #ffe5d0;
        color:#ef6c00;
        border: 1px solid #fdd9b5;
    }
    
    .semaforo-cafe {
        background-color: #f5deb3;
        color:#a0640f;
        border: 1px solid #d2b48c;
    }
    
    .semaforo-rojo {
        background-color: #f8d7da;
        color:#c41e1e;
        border: 1px solid #f5c6cb;
    }
    
    .custom-icon {
        background: transparent !important;
        border: none !important;
    }
    
    tr {
        transition: background-color 0.2s ease;
    }
    
    tr:hover {
        background-color: #f8f9fa !important;
    }
`;
document.head.appendChild(style);

console.log('✅ Archivo servicio_cliente.js cargado completamente');

// ============================================
// FUNCIÓN PARA COLAPSAR/EXPANDIR SECCIONES
// ============================================
function toggleCollapsible(id) {
    const content = document.getElementById(id);
    const card = content.closest('.collapsible-card');
    
    // Toggle active class
    card.classList.toggle('active');
    
    // Expand or collapse
    if (content.classList.contains('collapsed')) {
        // EXPANDIR
        content.classList.remove('collapsed');
        
        // Calcular altura después de un pequeño delay para que el contenido se renderice
        setTimeout(() => {
            const height = content.scrollHeight;
            content.style.maxHeight = height + 'px';
            
            // Después de la transición, remover maxHeight para que sea flexible
            setTimeout(() => {
                if (!content.classList.contains('collapsed')) {
                    content.style.maxHeight = 'none';
                }
            }, 400);
        }, 10);
    } else {
        // COLAPSAR
        // Primero establecer la altura actual
        content.style.maxHeight = content.scrollHeight + 'px';
        
        // Forzar reflow
        content.offsetHeight;
        
        // Luego colapsar
        setTimeout(() => {
            content.style.maxHeight = '0px';
            content.classList.add('collapsed');
        }, 10);
    }
}

// ============================================
// ACTUALIZAR KPIs DEL HEADER
// ============================================
function actualizarKPIsHeader() {
    const totalFallas = datosFallas.length;
    const totalUsuarios = datosFallas.reduce((sum, f) => sum + (f.usuarios_afectados || 0), 0);
    const totalMant = datosMantenimientos.length;
    const criticos = datosFallas.filter(f => (f.tiempo_afectacion_hrs || 0) >= 72).length;
    
    document.getElementById('kpi-fallas').textContent = totalFallas;
    document.getElementById('kpi-usuarios').textContent = formatearNumero(totalUsuarios);
    document.getElementById('kpi-mantenimientos').textContent = totalMant;
    document.getElementById('kpi-criticos').textContent = criticos;
}

// ============================================
// ACTUALIZAR BADGES DE CONTEO
// ============================================
function actualizarBadgesConteo() {
    document.getElementById('badge-fallas-count').textContent = datosFallas.length;
    document.getElementById('badge-mant-count').textContent = datosMantenimientos.length;
    document.getElementById('badge-tabla-fallas').textContent = datosFallas.length;
    document.getElementById('badge-tabla-mant').textContent = datosMantenimientos.length;
}

// ============================================
// ACTUALIZAR PRÓXIMA ACTUALIZACIÓN EN HEADER
// ============================================
function actualizarProximaActualizacionHeader() {
    const ahora = new Date();
    const proximaHora = new Date(ahora);
    proximaHora.setHours(ahora.getHours() + 1, 0, 0, 0);
    
    const horaFormateada = proximaHora.toLocaleTimeString('es-CO', { 
        hour: '2-digit', 
        minute: '2-digit',
        hour12: false 
    });
    
    const elementoProximaActualizacion = document.getElementById('proxima-actualizacion');
    if (elementoProximaActualizacion) {
        elementoProximaActualizacion.textContent = horaFormateada;
    }
}

// ============================================
// EXPANDIR SECCIONES AL CARGAR DATOS
// ============================================
function expandirSeccionesIniciales() {
    // Expandir métricas de fallas por defecto
    setTimeout(() => {
        const metricasFallas = document.getElementById('metricas-fallas');
        if (metricasFallas) {
            metricasFallas.style.maxHeight = metricasFallas.scrollHeight + 'px';
            metricasFallas.closest('.collapsible-card').classList.add('active');
        }
        
        // Expandir métricas de mantenimientos
        const metricasMant = document.getElementById('metricas-mant');
        if (metricasMant) {
            metricasMant.style.maxHeight = metricasMant.scrollHeight + 'px';
            metricasMant.closest('.collapsible-card').classList.add('active');
        }
    }, 500);
}

// ============================================
// MODIFICAR FUNCIONES EXISTENTES
// ============================================

// Modificar cargarFallas para actualizar todo
const cargarFallasOriginal = cargarFallas;
cargarFallas = async function() {
    await cargarFallasOriginal();
    actualizarKPIsHeader();
    actualizarBadgesConteo();
    actualizarProximaActualizacionHeader();
    expandirSeccionesIniciales();
};

// Modificar cargarMantenimientos
const cargarMantenimientosOriginal = cargarMantenimientos;
cargarMantenimientos = async function() {
    await cargarMantenimientosOriginal();
    actualizarKPIsHeader();
    actualizarBadgesConteo();
};

// Modificar filtrarEventos
const filtrarEventosOriginal2 = filtrarEventos;
filtrarEventos = function() {
    filtrarEventosOriginal2();
    actualizarKPIsHeader();
    actualizarBadgesConteo();
};

// Inicializar en DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
    actualizarProximaActualizacionHeader();
});

// ============================================
// RECALCULAR ALTURA DE COLAPSABLES ABIERTOS
// ============================================
function recalcularAlturasColapsables() {
    // Recalcular altura de todas las secciones expandidas
    document.querySelectorAll('.collapsible-content:not(.collapsed)').forEach(content => {
        if (content.style.maxHeight !== 'none') {
            content.style.maxHeight = content.scrollHeight + 'px';
        }
    });
}
