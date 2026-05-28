// ============================================
// SEGUIMIENTO HL5 - JAVASCRIPT
// ============================================

let mapaHL5;
let markersLayer;
let otSeleccionada = null;

// Variables para el sistema de filtros
let datosTablaGlobal = [];
const filtrosActivos = {};
let columnaFiltroActual = null;
const columnasDetalle = [
    'HORA_INICIO',
    'NODE',
    'CINUM',
    'CINAME',
    'COD_UBICA',
    'CIUDAD',
    'DEPARTAMENTO',
    'MAXIMO',
    'OT',
    'ESTADO_OT',
    'GRUPO_OT',
    'FECHA_AVANCE',
    'AVANCE',
    'FALLA_FO',
    'OT_FO'
];

// ============================================
// INICIALIZACIÓN
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Iniciando Seguimiento HL5...');
    inicializarMapa();
    inicializarFiltrosTabla();
    cargarDatos();
    
    // Actualizar cada 5 minutos
    setInterval(cargarDatos, 300000);
});

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
// CARGAR DATOS
// ============================================

async function cargarDatos() {
    try {
        console.log('📡 Cargando datos de HL5...');
        
        // Cargar datos de OTs
        const responseOTs = await fetch('/api/hl5/ots');
        const dataOTs = await responseOTs.json();
        
        // Cargar datos de métricas por grupo
        const responseMetricas = await fetch('/api/hl5/metricas');
        const dataMetricas = await responseMetricas.json();
        
        console.log('✅ Datos cargados:', { 
            ots: dataOTs.length, 
            metricas: dataMetricas 
        });
        
        // Actualizar la interfaz
        actualizarMetricas(dataMetricas);
        actualizarMapa(dataOTs);
        actualizarTabla(dataOTs);
        actualizarEstadisticasTiempo(dataOTs);
        actualizarOTsFOPrevia(dataOTs);
        actualizarTablaDetalle(dataOTs);
        
    } catch (error) {
        console.error('❌ Error cargando datos:', error);
        mostrarError('Error al cargar los datos. Por favor, recarga la página.');
    }
}

// ============================================
// ACTUALIZAR MÉTRICAS
// ============================================

function actualizarMetricas(metricas) {
    console.log('📊 Actualizando métricas...', metricas);
    
    // Total de OTs
    const totalOTs = (metricas.CAMPO || 0) + (metricas.UNIRED || 0) + (metricas.BACKOFFICE || 0) + 
                     (metricas.TX || 0) + (metricas.FO || 0) + (metricas.DxINET || 0) + (metricas.CG || 0);
    
    document.getElementById('total-ots').textContent = totalOTs;
    document.getElementById('campo-count').textContent = metricas.CAMPO || 0;
    document.getElementById('unired-count').textContent = metricas.UNIRED || 0;
    document.getElementById('backoffice-count').textContent = metricas.BACKOFFICE || 0;
    document.getElementById('tx-count').textContent = metricas.TX || 0;
    document.getElementById('fo-count').textContent = metricas.FO || 0;
    document.getElementById('dxinet-count').textContent = metricas.DxINET || 0;
    document.getElementById('cg-count').textContent = metricas.CG || 0;
}

// ============================================
// ACTUALIZAR MAPA
// ============================================

function actualizarMapa(ots) {
    console.log('🗺️ Actualizando mapa con', ots.length, 'marcadores');
    
    // Limpiar marcadores existentes
    markersLayer.clearLayers();
    
    // Crear icono rojo personalizado
    const iconoRojo = L.icon({
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
    });
    
    // Añadir marcadores al mapa
    ots.forEach(ot => {
        if (ot.LATITUD && ot.LONGITUD) {
            // Calcular tiempo afectado
            let tiempoAfectado = '';
            if (ot.HORA_INICIO) {
                const horaInicio = new Date(ot.HORA_INICIO);
                const ahora = new Date();
                const diferenciaMs = ahora - horaInicio;
                
                // Convertir a días, horas y minutos
                const dias = Math.floor(diferenciaMs / (1000 * 60 * 60 * 24));
                const horas = Math.floor((diferenciaMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                const minutos = Math.floor((diferenciaMs % (1000 * 60 * 60)) / (1000 * 60));
                
                if (dias > 0) {
                    tiempoAfectado = `${dias}d ${horas}h ${minutos}m`;
                } else if (horas > 0) {
                    tiempoAfectado = `${horas}h ${minutos}m`;
                } else {
                    tiempoAfectado = `${minutos}m`;
                }
            } else {
                tiempoAfectado = 'N/A';
            }
            
            // Formatear hora de inicio
            const horaInicioFormateada = formatearFechaHora(ot.HORA_INICIO);
            
            const marker = L.marker([ot.LATITUD, ot.LONGITUD], { icon: iconoRojo })
                .bindPopup(`
                    <div class="popup-content">
                        <strong>${ot.CINAME || ot.CINUM}</strong><br>
                        <p><strong>OT:</strong> ${ot.OT}</p>
                        <p><strong>CINUM:</strong> ${ot.CINUM || 'N/A'}</p>
                        <p><strong>Estado:</strong> ${ot.ESTADO_OT}</p>
                        <p><strong>Grupo:</strong> ${ot.GRUPO_OT}</p>
                        <p><strong>Ciudad:</strong> ${ot.CIUDAD}</p>
                        <p><strong>COD_UBICA:</strong> ${ot.COD_UBICA || 'N/A'}</p>
                        <p><strong>Hora Inicio:</strong> ${horaInicioFormateada}</p>
                        <p><strong>Tiempo Afectado:</strong> <span style="color: #dc3545; font-weight: bold;">${tiempoAfectado}</span></p>
                    </div>
                `);
            
            markersLayer.addLayer(marker);
        }
    });
    
    console.log('✅ Mapa actualizado');
}

// ============================================
// ACTUALIZAR TABLA DE RESPONSABLES
// ============================================

// ============================================
// ACTUALIZAR TABLA DE RESPONSABLES - CORREGIDO
// ============================================

function actualizarTabla(ots) {
    console.log('📋 Actualizando tabla con', ots.length, 'OTs');
    
    const tbody = document.querySelector('#tabla-responsables tbody');
    tbody.innerHTML = '';
    
    // Agrupar OTs por número de OT
    const otsAgrupadas = {};
    ots.forEach(ot => {
        const numOT = ot.OT;
        if (!otsAgrupadas[numOT]) {
            otsAgrupadas[numOT] = {
                OT: numOT,
                CAMPO: 0,
                DxINET: 0,
                UNIRED: 0,
                FO: 0,
                TX: 0,
                CG: 0,
                BACKOFFICE: 0,
                DIAS: ot.DIAS || 0
            };
        }
        
        // Incrementar el contador del grupo correspondiente
        const grupo = ot.GRUPO_OT;
        if (grupo) {
            if (grupo.includes('O_CAM')) otsAgrupadas[numOT].CAMPO = 1;
            else if (grupo === 'O_DXINT') otsAgrupadas[numOT].DxINET = 1;
            else if (grupo === 'O_UNIRED') otsAgrupadas[numOT].UNIRED = 1;
            else if (grupo === 'O_GESFO') otsAgrupadas[numOT].FO = 1;
            else if (grupo === 'O_GESTRA') otsAgrupadas[numOT].TX = 1;
            else if (grupo === 'O_GESRED') otsAgrupadas[numOT].CG = 1;
            else if (grupo === 'BACKOFFICE_N1') otsAgrupadas[numOT].BACKOFFICE = 1;
        }
    });
    
    // Ordenar por DIAS de menor a mayor
    const otsOrdenadas = Object.values(otsAgrupadas).sort((a, b) => {
        return a.DIAS - b.DIAS;  // 
    });
    
    console.log('📊 Primeras 5 OTs ordenadas:', otsOrdenadas.slice(0, 5).map(o => o.OT));
    
    // Crear filas de la tabla
    otsOrdenadas.forEach(ot => {
        const tr = document.createElement('tr');
        
        // Determinar clase de color según días
        let claseDias = 'dias-0';
        if (ot.DIAS > 8) claseDias = 'dias-8-plus';
        else if (ot.DIAS >= 4) claseDias = 'dias-4-7';
        else if (ot.DIAS >= 1) claseDias = 'dias-1-3';
        
        tr.innerHTML = `
            <td>${ot.OT}</td>
            <td class="${ot.CAMPO ? 'has-value' : ''}">${ot.CAMPO ? 'X' : ''}</td>
            <td class="${ot.DxINET ? 'has-value' : ''}">${ot.DxINET ? 'X' : ''}</td>
            <td class="${ot.UNIRED ? 'has-value' : ''}">${ot.UNIRED ? 'X' : ''}</td>
            <td class="${ot.FO ? 'has-value' : ''}">${ot.FO ? 'X' : ''}</td>
            <td class="${ot.TX ? 'has-value' : ''}">${ot.TX ? 'X' : ''}</td>
            <td class="${ot.CG ? 'has-value' : ''}">${ot.CG ? 'X' : ''}</td>
            <td class="${ot.BACKOFFICE ? 'has-value' : ''}">${ot.BACKOFFICE ? 'X' : ''}</td>
            <td class="days-cell ${claseDias}">${ot.DIAS}</td>
        `;
        
        tbody.appendChild(tr);
    });
    
    console.log('✅ Tabla actualizada con', otsOrdenadas.length, 'filas');
}
// ============================================
// ACTUALIZAR ESTADÍSTICAS DE TIEMPO
// ============================================

function actualizarEstadisticasTiempo(ots) {
    console.log('⏱️ Actualizando estadísticas de tiempo...');
    
    let count4h = 0;
    let count8h = 0;
    let count24h = 0;
    let count72h = 0;
    let count7d = 0;
    let count15d = 0;
    
    ots.forEach(ot => {
        const horas = parseFloat(ot.HORAS) || 0;
        
        if (horas < 4) count4h++;
        else if (horas >= 8 && horas < 24) count8h++;
        else if (horas >= 24 && horas < 72) count24h++;
        else if (horas >= 72 && horas < 168) count72h++;
        else if (horas >= 168 && horas < 360) count7d++;
        else if (horas >= 360) count15d++;
    });
    
    document.getElementById('count-4h').textContent = count4h;
    document.getElementById('count-8h').textContent = count8h;
    document.getElementById('count-24h').textContent = count24h;
    document.getElementById('count-72h').textContent = count72h;
    document.getElementById('count-7d').textContent = count7d;
    document.getElementById('count-15d').textContent = count15d;
    
    console.log('✅ Estadísticas de tiempo actualizadas');
}

// ============================================
// ACTUALIZAR OTs CON FO PREVIA
// ============================================

function actualizarOTsFOPrevia(ots) {
    console.log('📊 Actualizando OTs con FO previa...');
    
    const countFOPrevia = ots.filter(ot => ot.FALLA_FO === 'SI' || ot.OT_FO).length;
    document.getElementById('ot-fo-previa').textContent = countFOPrevia;
    
    console.log('✅ OTs con FO previa:', countFOPrevia);
}

// ============================================
// ACTUALIZAR TABLA DETALLE HL5 AFECTADOS
// ============================================

function actualizarTablaDetalle(ots) {
    console.log('📋 Actualizando tabla detalle con', ots.length, 'registros');
    
    // Guardar datos globalmente para los filtros
    datosTablaGlobal = ots;
    
    // Aplicar filtros y renderizar
    aplicarFiltrosYRenderizar();
}

// ============================================
// MODAL DE ACCIONES
// ============================================

function abrirModalAcciones(ot, cinum, ciname, grupo) {
    console.log('🔧 Abriendo modal de acciones para OT:', ot);
    
    otSeleccionada = {
        ot: ot,
        cinum: cinum,
        ciname: ciname,
        grupo: grupo
    };
    
    // Actualizar información del modal
    const modalInfo = document.getElementById('modalInfo');
    modalInfo.innerHTML = `
        <div class="modal-info-row">
            <span class="modal-info-label">OT:</span>
            <span class="modal-info-value">${ot}</span>
        </div>
        <div class="modal-info-row">
            <span class="modal-info-label">CINUM:</span>
            <span class="modal-info-value">${cinum}</span>
        </div>
        <div class="modal-info-row">
            <span class="modal-info-label">CINAME:</span>
            <span class="modal-info-value">${ciname}</span>
        </div>
        <div class="modal-info-row">
            <span class="modal-info-label">Grupo:</span>
            <span class="modal-info-value">${grupo}</span>
        </div>
    `;
    
    // Mostrar modal y menú de opciones
    document.getElementById('modalAcciones').classList.add('active');
    document.getElementById('menuOpciones').style.display = 'flex';
    document.getElementById('formAvance').style.display = 'none';
    document.getElementById('formCerrar').style.display = 'none';
    document.getElementById('formEscalar').style.display = 'none';
}

function cerrarModal() {
    console.log('❌ Cerrando modal');
    document.getElementById('modalAcciones').classList.remove('active');
    otSeleccionada = null;
}

function mostrarFormulario(tipo) {
    console.log('📝 Mostrando formulario:', tipo);
    
    // Ocultar menú de opciones
    document.getElementById('menuOpciones').style.display = 'none';
    
    // Mostrar formulario correspondiente
    if (tipo === 'avance') {
        document.getElementById('formAvance').style.display = 'block';
        document.getElementById('avanceComentario').value = '';
    } else if (tipo === 'cerrar') {
        document.getElementById('formCerrar').style.display = 'block';
        document.getElementById('cierreComentario').value = '';
        document.getElementById('cierreEstado').value = '';
    } else if (tipo === 'escalar') {
        document.getElementById('formEscalar').style.display = 'block';
        document.getElementById('escalarArea').value = '';
        document.getElementById('escalarMotivo').value = '';
    }
}

function volverMenu() {
    console.log('🔙 Volviendo al menú');
    document.getElementById('menuOpciones').style.display = 'flex';
    document.getElementById('formAvance').style.display = 'none';
    document.getElementById('formCerrar').style.display = 'none';
    document.getElementById('formEscalar').style.display = 'none';
}

async function enviarAvance(event) {
    event.preventDefault();
    
    const comentario = document.getElementById('avanceComentario').value;
    
    if (!otSeleccionada || !comentario) {
        alert('Por favor, completa todos los campos');
        return;
    }
    
    console.log('📤 Enviando avance para OT:', otSeleccionada.ot);
    
    try {
        const response = await fetch('/api/hl5/gestionar-ot', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ot: otSeleccionada.ot,
                tipo_accion: 'AVANCE',
                comentario: comentario
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('✅ Avance registrado exitosamente');
            cerrarModal();
            cargarDatos(); // Recargar datos
        } else {
            alert('❌ Error: ' + (data.message || data.error || 'No se pudo registrar el avance'));
        }
    } catch (error) {
        console.error('❌ Error enviando avance:', error);
        alert('❌ Error al enviar el avance');
    }
}

async function cerrarOT(event) {
    event.preventDefault();
    
    const comentario = document.getElementById('cierreComentario').value;
    const estado = document.getElementById('cierreEstado').value;
    
    if (!otSeleccionada || !comentario || !estado) {
        alert('Por favor, completa todos los campos');
        return;
    }
    
    console.log('🔒 Cerrando OT:', otSeleccionada.ot);
    
    try {
        const response = await fetch('/api/hl5/gestionar-ot', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ot: otSeleccionada.ot,
                tipo_accion: 'CERRAR',
                comentario: comentario,
                estado: estado
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('✅ OT cerrada exitosamente');
            cerrarModal();
            cargarDatos(); // Recargar datos
        } else {
            alert('❌ Error: ' + (data.message || data.error || 'No se pudo cerrar la OT'));
        }
    } catch (error) {
        console.error('❌ Error cerrando OT:', error);
        alert('❌ Error al cerrar la OT');
    }
}

async function escalarOT(event) {
    event.preventDefault();
    
    const area = document.getElementById('escalarArea').value;
    const motivo = document.getElementById('escalarMotivo').value;
    
    if (!otSeleccionada || !area || !motivo) {
        alert('Por favor, completa todos los campos');
        return;
    }
    
    console.log('⬆️ Escalando OT:', otSeleccionada.ot);
    
    try {
        const response = await fetch('/api/hl5/gestionar-ot', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ot: otSeleccionada.ot,
                tipo_accion: 'ESCALAR',
                area_destino: area,
                motivo: motivo
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('✅ OT escalada exitosamente');
            cerrarModal();
            cargarDatos(); // Recargar datos
        } else {
            alert('❌ Error: ' + (data.message || data.error || 'No se pudo escalar la OT'));
        }
    } catch (error) {
        console.error('❌ Error escalando OT:', error);
        alert('❌ Error al escalar la OT');
    }
}

// ============================================
// UTILIDADES
// ============================================

function mostrarError(mensaje) {
    console.error('❌', mensaje);
    alert(mensaje);
}

function formatearFecha(fecha) {
    if (!fecha) return 'N/A';
    const date = new Date(fecha);
    return date.toLocaleDateString('es-CO') + ' ' + date.toLocaleTimeString('es-CO');
}

function formatearFechaHora(fecha) {
    if (!fecha) return '';
    try {
        const date = new Date(fecha);
        if (isNaN(date.getTime())) return '';
        
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        
        return `${year}-${month}-${day} ${hours}:${minutes}`;
    } catch (e) {
        return '';
    }
}

function truncarTexto(texto, maxLength) {
    if (!texto) return '';
    if (texto.length <= maxLength) return texto;
    return texto.substring(0, maxLength) + '...';
}

console.log('✅ Script de Seguimiento HL5 cargado correctamente');
// ============================================
// SISTEMA DE FILTROS
// ============================================

function inicializarFiltrosTabla() {
    const modal = document.getElementById('filter-modal');
    const modalClose = document.querySelector('.filter-modal-close');
    const btnOk = document.getElementById('filter-btn-ok');
    const btnCancel = document.getElementById('filter-btn-cancel');
    const searchInput = document.getElementById('filter-search-input');
    const optionsContainer = document.getElementById('filter-options-container');
    const btnLimpiarFiltros = document.getElementById('btn-limpiar-filtros');

    if (!modal || !modalClose || !btnOk || !btnCancel || !searchInput || !optionsContainer) {
        console.warn('⚠️ Elementos del modal de filtro no encontrados');
        return;
    }

    console.log('✅ Inicializando filtros de tabla...');

    document.querySelectorAll('.filter-icon').forEach(icon => {
        icon.addEventListener('click', function(e) {
            e.stopPropagation();
            const columna = this.dataset.col;
            columnaFiltroActual = columna;
            console.log('🔍 Abriendo filtro para columna:', columna);
            abrirModalFiltro(columna);
        });
    });

    modalClose.addEventListener('click', cerrarModalFiltro);
    btnCancel.addEventListener('click', cerrarModalFiltro);

    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            cerrarModalFiltro();
        }
    });

    btnOk.addEventListener('click', aplicarFiltroModal);

    searchInput.addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase();
        const options = optionsContainer.querySelectorAll('.filter-option');
        
        options.forEach(option => {
            const label = option.querySelector('label').textContent.toLowerCase();
            option.style.display = label.includes(searchTerm) ? 'flex' : 'none';
        });
    });

    if (btnLimpiarFiltros) {
        btnLimpiarFiltros.addEventListener('click', limpiarTodosFiltros);
    }
}

function abrirModalFiltro(columna) {
    const modal = document.getElementById('filter-modal');
    const optionsContainer = document.getElementById('filter-options-container');
    const searchInput = document.getElementById('filter-search-input');
    
    if (!modal || !optionsContainer || !searchInput) {
        console.error('❌ Elementos del modal no encontrados');
        return;
    }

    searchInput.value = '';

    // Obtener valores únicos de la columna desde datosTablaGlobal
    const valoresUnicos = Array.from(
        new Set(
            datosTablaGlobal
                .map(item => String(item[columna] || ''))
                .filter(v => v !== '')
        )
    ).sort((a, b) => a.localeCompare(b, 'es', { sensitivity: 'base' }));
    
    console.log('📊 Valores únicos para', columna, ':', valoresUnicos.length);
    
    optionsContainer.innerHTML = '';
    valoresUnicos.forEach(valor => {
        const isChecked = filtrosActivos[columna] && filtrosActivos[columna].includes(valor);
        
        const optionDiv = document.createElement('div');
        optionDiv.className = 'filter-option';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `filter-${columna}-${valor}`;
        checkbox.value = valor;
        checkbox.checked = isChecked;
        
        const label = document.createElement('label');
        label.htmlFor = `filter-${columna}-${valor}`;
        label.textContent = valor;
        
        optionDiv.appendChild(checkbox);
        optionDiv.appendChild(label);
        
        optionDiv.addEventListener('click', function(e) {
            if (e.target !== checkbox) {
                checkbox.checked = !checkbox.checked;
            }
        });
        
        optionsContainer.appendChild(optionDiv);
    });
    
    modal.classList.add('show');
}

function cerrarModalFiltro() {
    const modal = document.getElementById('filter-modal');
    if (modal) modal.classList.remove('show');
    columnaFiltroActual = null;
}

function aplicarFiltroModal() {
    if (!columnaFiltroActual) return;
    
    const optionsContainer = document.getElementById('filter-options-container');
    const checkboxes = optionsContainer.querySelectorAll('input[type="checkbox"]:checked');
    
    const valoresSeleccionados = Array.from(checkboxes).map(cb => cb.value);
    
    console.log('✅ Aplicando filtro:', columnaFiltroActual, valoresSeleccionados);
    
    if (valoresSeleccionados.length > 0) {
        filtrosActivos[columnaFiltroActual] = valoresSeleccionados;
        
        const icon = document.querySelector(`.filter-icon[data-col="${columnaFiltroActual}"]`);
        if (icon) icon.classList.add('active');
    } else {
        delete filtrosActivos[columnaFiltroActual];
        const icon = document.querySelector(`.filter-icon[data-col="${columnaFiltroActual}"]`);
        if (icon) icon.classList.remove('active');
    }
    
    cerrarModalFiltro();
    aplicarFiltrosYRenderizar();
}

function aplicarFiltrosYRenderizar() {
    console.log('🔄 Aplicando filtros activos:', filtrosActivos);
    
    let datosFiltrados = [...datosTablaGlobal];
    
    // Aplicar cada filtro activo
    Object.keys(filtrosActivos).forEach(columna => {
        const valoresFiltro = filtrosActivos[columna];
        if (valoresFiltro && valoresFiltro.length > 0) {
            datosFiltrados = datosFiltrados.filter(row => {
                const valor = String(row[columna] || '');
                return valoresFiltro.includes(valor);
            });
        }
    });
    
    console.log('📊 Registros después de filtrar:', datosFiltrados.length);
    renderizarTablaDetalle(datosFiltrados);
}

function limpiarTodosFiltros() {
    console.log('🧹 Limpiando todos los filtros');
    Object.keys(filtrosActivos).forEach(key => delete filtrosActivos[key]);
    document.querySelectorAll('.filter-icon').forEach(icon => icon.classList.remove('active'));
    aplicarFiltrosYRenderizar();
}

function renderizarTablaDetalle(datos) {
    console.log('📋 Renderizando tabla detalle con', datos.length, 'registros');
    
    const tbody = document.querySelector('#tabla-detalle-hl5 tbody');
    if (!tbody) {
        console.error('❌ No se encontró el tbody de la tabla detalle');
        return;
    }
    
    tbody.innerHTML = '';
    
    // Ordenar por HORA_INICIO descendente (más recientes primero)
    const otsOrdenadas = [...datos].sort((a, b) => {
        const fechaA = new Date(a.HORA_INICIO || 0);
        const fechaB = new Date(b.HORA_INICIO || 0);
        return fechaB - fechaA;
    });
    
    // Crear filas de la tabla
    otsOrdenadas.forEach(ot => {
        const tr = document.createElement('tr');
        
        // Verificar si tiene FO previa
        const tieneFOPrevia = (ot.FALLA_FO === 'SI' || ot.OT_FO);
        if (tieneFOPrevia) {
            tr.classList.add('fila-fo-previa');
        }
        
        tr.innerHTML = `
            <td>${formatearFechaHora(ot.HORA_INICIO)}</td>
            <td>${ot.NODE || ''}</td>
            <td>${ot.CINUM || ''}</td>
            <td>${ot.CINAME || ''}</td>
            <td>${ot.COD_UBICA || ''}</td>
            <td>${ot.CIUDAD || ''}</td>
            <td>${ot.DEPARTAMENTO || ''}</td>
            <td>${ot.MAXIMO || ''}</td>
            <td>${ot.OT || ''}</td>
            <td>${ot.ESTADO_OT || ''}</td>
            <td>${ot.GRUPO_OT || ''}</td>
            <td>${formatearFechaHora(ot.FECHA_AVANCE)}</td>
            <td class="avance-cell" title="${ot.AVANCE || ''}">${ot.AVANCE || ''}</td>
            <td>${ot.FALLA_FO || 'NO'}</td>
            <td>${ot.OT_FO || ''}</td>
            <td>
                <button class="btn-acciones" onclick="abrirModalAcciones('${ot.OT || ''}', '${ot.CINUM || ''}', '${ot.CINAME || ''}', '${ot.GRUPO_OT || ''}')">
                    <ion-icon name="settings-outline"></ion-icon>
                </button>
            </td>
        `;
        
        tbody.appendChild(tr);
    });
    
    console.log('✅ Tabla detalle renderizada con', otsOrdenadas.length, 'filas');
}