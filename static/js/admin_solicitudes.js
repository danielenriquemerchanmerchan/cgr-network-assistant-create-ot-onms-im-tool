// ============================================
// FUNCIONES PARA MODALES
// ============================================

function mostrarModalAprobar(id, nombre, apellido, correo) {
    document.getElementById('aprobar_id').value = id;
    document.getElementById('aprobar_nombre').textContent = nombre + ' ' + apellido;
    document.getElementById('aprobar_correo').textContent = correo;
    document.getElementById('modalAprobar').style.display = 'block';
    
    // Limpiar campos del formulario
    document.getElementById('perfil').value = '';
    document.getElementById('observaciones').value = '';
}

function mostrarModalRechazar(id, nombre, apellido) {
    document.getElementById('rechazar_id').value = id;
    document.getElementById('rechazar_nombre').textContent = nombre + ' ' + apellido;
    document.getElementById('modalRechazar').style.display = 'block';
    
    // Limpiar campo motivo
    document.getElementById('motivo_rechazo').value = '';
}

function cerrarModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// Cerrar modal al hacer clic fuera
window.onclick = function(event) {
    const modalAprobar = document.getElementById('modalAprobar');
    const modalRechazar = document.getElementById('modalRechazar');
    
    if (event.target == modalAprobar) {
        cerrarModal('modalAprobar');
    }
    if (event.target == modalRechazar) {
        cerrarModal('modalRechazar');
    }
}

// Cerrar modal con tecla ESC
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        cerrarModal('modalAprobar');
        cerrarModal('modalRechazar');
    }
});


// ============================================
// FUNCIÓN DE FILTRADO
// ============================================

function filtrarSolicitudes() {
    const filtro = document.getElementById('filtroEstado').value;
    const filas = document.querySelectorAll('.fila-solicitud');
    let contadorVisible = 0;
    
    filas.forEach(fila => {
        const estado = fila.getAttribute('data-estado');
        
        if (filtro === 'todos' || estado === filtro) {
            fila.style.display = '';
            contadorVisible++;
        } else {
            fila.style.display = 'none';
        }
    });
    
    // Actualizar mensaje si no hay resultados visibles
    actualizarMensajeSinResultados(contadorVisible);
}

function actualizarMensajeSinResultados(contador) {
    const tbody = document.querySelector('.tabla-solicitudes tbody');
    let mensajeExistente = document.getElementById('mensaje-sin-resultados');
    
    if (contador === 0) {
        if (!mensajeExistente) {
            const tr = document.createElement('tr');
            tr.id = 'mensaje-sin-resultados';
            tr.innerHTML = '<td colspan="10" style="text-align: center; padding: 30px; color: #999;">No hay solicitudes con el filtro seleccionado</td>';
            tbody.appendChild(tr);
        }
    } else {
        if (mensajeExistente) {
            mensajeExistente.remove();
        }
    }
}


// ============================================
// VER DETALLE (OPCIONAL)
// ============================================

function verDetalle(id) {
    // Esta función puede expandirse para mostrar más información
    // Por ahora solo muestra un alert
    alert('Funcionalidad de detalle para solicitud ID: ' + id + '\n\nPróximamente se agregará un modal con información completa.');
}


// ============================================
// VALIDACIONES DE FORMULARIOS
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    const formAprobar = document.getElementById('formAprobar');
    const formRechazar = document.getElementById('formRechazar');
    
    // Validación formulario de aprobación
    if (formAprobar) {
        formAprobar.addEventListener('submit', function(e) {
            const perfil = document.getElementById('perfil').value;
            
            if (!perfil) {
                e.preventDefault();
                alert('⚠️ Por favor, seleccione un perfil antes de aprobar.');
                document.getElementById('perfil').focus();
                return false;
            }
            
            // Confirmación final
            if (!confirm('¿Está seguro de aprobar esta solicitud?\n\nSe creará un nuevo usuario en el sistema.')) {
                e.preventDefault();
                return false;
            }
            
            // Mostrar mensaje de procesamiento
            mostrarMensajeProcesando('Procesando aprobación...');
        });
    }
    
    // Validación formulario de rechazo
    if (formRechazar) {
        formRechazar.addEventListener('submit', function(e) {
            const motivo = document.getElementById('motivo_rechazo').value.trim();
            
            if (!motivo) {
                e.preventDefault();
                alert('⚠️ Por favor, especifique el motivo del rechazo.');
                document.getElementById('motivo_rechazo').focus();
                return false;
            }
            
            if (motivo.length < 10) {
                e.preventDefault();
                alert('⚠️ El motivo del rechazo debe tener al menos 10 caracteres.');
                document.getElementById('motivo_rechazo').focus();
                return false;
            }
            
            // Confirmación final
            if (!confirm('¿Está seguro de rechazar esta solicitud?\n\nSe enviará un correo al solicitante con el motivo del rechazo.')) {
                e.preventDefault();
                return false;
            }
            
            // Mostrar mensaje de procesamiento
            mostrarMensajeProcesando('Procesando rechazo...');
        });
    }
    
    // Aplicar filtro inicial (mostrar solo pendientes por defecto)
    filtrarSolicitudes();
});


// ============================================
// FUNCIONES AUXILIARES
// ============================================

function mostrarMensajeProcesando(mensaje) {
    // Crear overlay de procesamiento
    const overlay = document.createElement('div');
    overlay.id = 'overlay-procesando';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(0,0,0,0.7);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 9999;
    `;
    
    overlay.innerHTML = `
        <div style="background: white; padding: 30px; border-radius: 10px; text-align: center;">
            <div class="spinner" style="border: 4px solid #f3f3f3; border-top: 4px solid #0166ff; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto 15px;"></div>
            <p style="margin: 0; font-size: 16px; color: #333;">${mensaje}</p>
        </div>
    `;
    
    // Agregar animación del spinner
    const style = document.createElement('style');
    style.textContent = `
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    `;
    document.head.appendChild(style);
    
    document.body.appendChild(overlay);
}

// Función para resaltar filas (opcional)
function resaltarFila(idSolicitud) {
    const filas = document.querySelectorAll('.fila-solicitud');
    filas.forEach(fila => {
        const id = fila.querySelector('td:first-child').textContent;
        if (id == idSolicitud) {
            fila.style.backgroundColor = '#fffacd';
            setTimeout(() => {
                fila.style.backgroundColor = '';
            }, 2000);
        }
    });
}

// Auto-cerrar mensajes flash después de 5 segundos
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            alert.style.transition = 'opacity 0.5s';
            setTimeout(() => {
                alert.remove();
            }, 500);
        }, 5000);
    });
});


// ============================================
// BÚSQUEDA EN TIEMPO REAL (OPCIONAL)
// ============================================

function agregarBusqueda() {
    const tabla = document.querySelector('.tabla-solicitudes');
    if (!tabla) return;
    
    // Crear input de búsqueda
    const busquedaDiv = document.createElement('div');
    busquedaDiv.style.cssText = 'margin-bottom: 15px;';
    busquedaDiv.innerHTML = `
        <input type="text" id="busqueda-solicitudes" 
               placeholder="🔍 Buscar por nombre, correo, área..." 
               style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 14px;">
    `;
    
    tabla.parentElement.insertBefore(busquedaDiv, tabla);
    
    // Agregar evento de búsqueda
    document.getElementById('busqueda-solicitudes').addEventListener('input', function(e) {
        const busqueda = e.target.value.toLowerCase();
        const filas = document.querySelectorAll('.fila-solicitud');
        
        filas.forEach(fila => {
            const texto = fila.textContent.toLowerCase();
            if (texto.includes(busqueda)) {
                fila.style.display = '';
            } else {
                fila.style.display = 'none';
            }
        });
    });
}

// Descomentar si quieres activar la búsqueda
// agregarBusqueda();


// ============================================
// ESTADÍSTICAS EN TIEMPO REAL (OPCIONAL)
// ============================================

function actualizarEstadisticas() {
    const filas = document.querySelectorAll('.fila-solicitud');
    let pendientes = 0, aprobadas = 0, rechazadas = 0;
    
    filas.forEach(fila => {
        const estado = fila.getAttribute('data-estado');
        if (estado === 'PENDIENTE') pendientes++;
        else if (estado === 'APROBADO') aprobadas++;
        else if (estado === 'RECHAZADO') rechazadas++;
    });
    
    console.log(`Estadísticas: Pendientes: ${pendientes}, Aprobadas: ${aprobadas}, Rechazadas: ${rechazadas}`);
}

// Llamar al cargar la página
document.addEventListener('DOMContentLoaded', actualizarEstadisticas);