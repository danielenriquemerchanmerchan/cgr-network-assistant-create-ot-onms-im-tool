// ============================================
// gestion_usuarios.js — Versión actualizada
// Nuevas funciones: último acceso, conectados,
// gráfica por hora, edición extendida
// ============================================

// ─── Estado global ────────────────────────────────────────────
let ordenActual = { columna: null, direccion: 'asc' };
let filtroSoloConectados = false;

// ============================================
// ORDENAMIENTO
// ============================================

function ordenarTabla(columna) {
    const tabla = document.getElementById('tablaUsuarios');
    if (!tabla) return;
    const tbody = tabla.querySelector('tbody');
    const filas = Array.from(tbody.querySelectorAll('.fila-usuario'));

    if (ordenActual.columna === columna) {
        ordenActual.direccion = ordenActual.direccion === 'asc' ? 'desc' : 'asc';
    } else {
        ordenActual.columna = columna;
        ordenActual.direccion = 'asc';
    }

    actualizarIconosOrdenamiento(columna, ordenActual.direccion);

    filas.sort((a, b) => {
        let vA, vB;
        switch (columna) {
            case 'usuario': vA = a.dataset.usuario || ''; vB = b.dataset.usuario || ''; break;
            case 'nombre':  vA = a.dataset.nombre  || ''; vB = b.dataset.nombre  || ''; break;
            case 'correo':  vA = a.dataset.correo  || ''; vB = b.dataset.correo  || ''; break;
            case 'area':    vA = a.dataset.area    || ''; vB = b.dataset.area    || ''; break;
            case 'perfil':  vA = a.dataset.perfil  || ''; vB = b.dataset.perfil  || ''; break;
            case 'estado':  vA = a.dataset.estado  || ''; vB = b.dataset.estado  || ''; break;
            case 'sesion':  vA = parseInt(a.dataset.sesion) || 0; vB = parseInt(b.dataset.sesion) || 0; break;
            case 'fecha':   vA = parsearFecha(a.dataset.fecha); vB = parsearFecha(b.dataset.fecha); break;
            case 'acceso':  vA = a.dataset.accesoIso || ''; vB = b.dataset.accesoIso || ''; break;
            default: return 0;
        }
        let cmp = 0;
        if (columna === 'fecha' || columna === 'sesion') {
            cmp = vA - vB;
        } else if (columna === 'acceso') {
            // Nunca (vacío) va al final
            if (!vA && !vB) cmp = 0;
            else if (!vA) cmp = 1;
            else if (!vB) cmp = -1;
            else cmp = vA.localeCompare(vB);
        } else {
            cmp = vA.toString().localeCompare(vB.toString(), 'es', { sensitivity: 'base' });
        }
        return ordenActual.direccion === 'asc' ? cmp : -cmp;
    });

    filas.forEach(f => tbody.appendChild(f));
    aplicarFiltros();
}

function actualizarIconosOrdenamiento(columnaActiva, direccion) {
    document.querySelectorAll('.tabla-usuarios thead th[data-column]').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
        const icon = th.querySelector('.sort-icon');
        if (icon) icon.setAttribute('name', 'swap-vertical-outline');
    });
    if (columnaActiva) {
        const thActivo = document.querySelector(`th[data-column="${columnaActiva}"]`);
        if (thActivo) {
            thActivo.classList.add(direccion === 'asc' ? 'sort-asc' : 'sort-desc');
            const icon = thActivo.querySelector('.sort-icon');
            if (icon) icon.setAttribute('name', direccion === 'asc' ? 'arrow-up-outline' : 'arrow-down-outline');
        }
    }
}

function parsearFecha(str) {
    if (!str) return new Date(0);
    const p = str.split('/');
    if (p.length !== 3) return new Date(0);
    return new Date(p[2], p[1] - 1, p[0]);
}

// ============================================
// FILTRADO
// ============================================

function aplicarFiltros() {
    const filas = document.querySelectorAll('.fila-usuario');
    let visible = 0;

    const filtros = {
        busqueda:    (document.getElementById('buscarUsuario')?.value    || '').toLowerCase(),
        estadoGlob:  document.getElementById('filtroEstado')?.value      || 'todos',
        perfilGlob:  document.getElementById('filtroPerfil')?.value      || 'todos',
        usuario:     (document.getElementById('filter-usuario')?.value   || '').toLowerCase(),
        nombre:      (document.getElementById('filter-nombre')?.value    || '').toLowerCase(),
        correo:      (document.getElementById('filter-correo')?.value    || '').toLowerCase(),
        area:        (document.getElementById('filter-area')?.value      || '').toLowerCase(),
        perfilCol:   document.getElementById('filter-perfil-col')?.value || '',
        estadoCol:   document.getElementById('filter-estado-col')?.value || '',
        sesionCol:   document.getElementById('filter-sesion-col')?.value || '',
        acceso:      (document.getElementById('filter-acceso')?.value    || '').toLowerCase(),
        fecha:       (document.getElementById('filter-fecha')?.value     || '').toLowerCase(),
    };

    actualizarEstilosFiltros(filtros);

    filas.forEach(fila => {
        let mostrar = true;

        // ── Filtros básicos ──────────────────────────────────────────────
        if (filtros.busqueda && !fila.textContent.toLowerCase().includes(filtros.busqueda)) mostrar = false;
        if (filtros.estadoGlob !== 'todos' && fila.dataset.estado !== filtros.estadoGlob)   mostrar = false;
        if (filtros.perfilGlob !== 'todos' && fila.dataset.perfil !== filtros.perfilGlob)   mostrar = false;
        if (filtros.usuario && !(fila.dataset.usuario  || '').includes(filtros.usuario))    mostrar = false;
        if (filtros.nombre  && !(fila.dataset.nombre   || '').includes(filtros.nombre))     mostrar = false;
        if (filtros.correo  && !(fila.dataset.correo   || '').includes(filtros.correo))     mostrar = false;
        if (filtros.area    && !(fila.dataset.area     || '').includes(filtros.area))       mostrar = false;
        if (filtros.perfilCol && fila.dataset.perfil !== filtros.perfilCol)                 mostrar = false;
        if (filtros.estadoCol && fila.dataset.estado !== filtros.estadoCol)                 mostrar = false;
        if (filtros.sesionCol !== '' && fila.dataset.sesion !== filtros.sesionCol)           mostrar = false;
        if (filtros.fecha   && !(fila.dataset.fecha    || '').toLowerCase().includes(filtros.fecha))  mostrar = false;

        // ── Filtro Último Acceso ─────────────────────────────────────────
        if (filtros.acceso) {
            // busca en el texto renderizado de la celda
            const celdaAcceso = fila.querySelector('.ultimo-acceso-cell');
            const textoAcceso = celdaAcceso ? celdaAcceso.textContent.toLowerCase() : '';
            if (!textoAcceso.includes(filtros.acceso)) mostrar = false;
        }

        // ── Filtro Solo Conectados ───────────────────────────────────────
        if (filtroSoloConectados && fila.dataset.conectado !== 'true') mostrar = false;

        fila.style.display = mostrar ? '' : 'none';
        if (mostrar) visible++;
    });

    actualizarContador(visible, filas.length);
    actualizarMensajeSinResultados(visible);
}

function actualizarEstilosFiltros(f) {
    const ids = [
        ['filter-usuario',    f.usuario],
        ['filter-nombre',     f.nombre],
        ['filter-correo',     f.correo],
        ['filter-area',       f.area],
        ['filter-perfil-col', f.perfilCol],
        ['filter-estado-col', f.estadoCol],
        ['filter-sesion-col', f.sesionCol],
        ['filter-acceso',     f.acceso],
        ['filter-fecha',      f.fecha],
    ];
    ids.forEach(([id, val]) => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('has-value', !!val);
    });
}

function actualizarContador(vis, total) {
    const cv = document.getElementById('contador-visibles');
    const ct = document.getElementById('contador-total');
    if (cv) cv.textContent = vis;
    if (ct) ct.textContent = total;
}

function actualizarMensajeSinResultados(cnt) {
    const tbody = document.querySelector('.tabla-usuarios tbody');
    if (!tbody) return;
    let msg = document.getElementById('mensaje-sin-resultados');
    if (cnt === 0) {
        if (!msg) {
            const tr = document.createElement('tr');
            tr.id = 'mensaje-sin-resultados';
            tr.innerHTML = '<td colspan="10" style="text-align:center;padding:30px;color:#999;">'
                + '<ion-icon name="search-outline" style="font-size:48px;display:block;margin:0 auto 10px;"></ion-icon>'
                + 'No se encontraron usuarios con los filtros aplicados</td>';
            tbody.appendChild(tr);
        }
    } else {
        msg?.remove();
    }
}

function limpiarTodosFiltros() {
    const ids = ['buscarUsuario','filtroEstado','filtroPerfil',
                 'filter-usuario','filter-nombre','filter-correo','filter-area',
                 'filter-perfil-col','filter-estado-col','filter-sesion-col',
                 'filter-acceso','filter-fecha'];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        if (el.tagName === 'SELECT') {
            el.value = el.id === 'filtroEstado' || el.id === 'filtroPerfil' ? 'todos' : '';
        } else {
            el.value = '';
        }
    });

    // Limpiar filtro conectados
    filtroSoloConectados = false;
    document.getElementById('btnFiltroConectados')?.classList.remove('activo');

    ordenActual = { columna: null, direccion: 'asc' };
    actualizarIconosOrdenamiento(null, null);
    aplicarFiltros();
}

// ============================================
// FILTRO: SOLO CONECTADOS
// ============================================

function toggleFiltroConectados() {
    filtroSoloConectados = !filtroSoloConectados;
    const btn = document.getElementById('btnFiltroConectados');
    if (btn) btn.classList.toggle('activo', filtroSoloConectados);
    aplicarFiltros();
}

// ============================================
// ÚLTIMO ACCESO: TIEMPO RELATIVO
// ============================================

function tiempoRelativo(isoStr) {
    if (!isoStr) return null;
    const ahora = new Date();
    const fecha = new Date(isoStr);
    if (isNaN(fecha)) return null;

    const diffMs   = ahora - fecha;
    const diffMin  = Math.floor(diffMs / 60000);
    const diffHrs  = Math.floor(diffMs / 3600000);
    const diffDias = Math.floor(diffMs / 86400000);

    let texto, clase;
    if (diffMin < 60) {
        texto = diffMin <= 1 ? 'hace 1 minuto' : `hace ${diffMin} min`;
        clase = 'tiempo-reciente';
    } else if (diffHrs < 24) {
        texto = diffHrs === 1 ? 'hace 1 hora' : `hace ${diffHrs} horas`;
        clase = 'tiempo-hoy';
    } else if (diffDias < 7) {
        texto = diffDias === 1 ? 'ayer' : `hace ${diffDias} días`;
        clase = 'tiempo-semana';
    } else {
        // Mostrar fecha formateada
        texto = fecha.toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' });
        clase = 'tiempo-antiguo';
    }
    return { texto, clase };
}

function renderizarUltimosAccesos() {
    document.querySelectorAll('.ultimo-acceso-cell').forEach(celda => {
        const iso = celda.dataset.iso;
        if (!iso) return;  // "Nunca" ya está en el HTML
        const rel = tiempoRelativo(iso);
        if (!rel) return;
        celda.innerHTML = `<span class="${rel.clase}" title="${celda.textContent.trim()}">${rel.texto}</span>`;
    });
}

// ============================================
// MODALES
// ============================================

/** Puente para leer los data-* del botón editar */
function mostrarModalEditarDesdeBtn(btn) {
    mostrarModalEditar(
        btn.dataset.usuario,
        btn.dataset.nombre,
        btn.dataset.apellido,
        btn.dataset.correo,
        btn.dataset.area,
        btn.dataset.perfil,
        btn.dataset.estado,
        parseInt(btn.dataset.sesion) || 0
    );
}

function mostrarModalEditar(usuario, nombre, apellido, correo, area, perfil, estado, sesionPermanente) {
    document.getElementById('edit_usuario_red').value       = usuario;
    document.getElementById('edit_display_usuario').textContent = usuario;
    document.getElementById('edit_nombre').value            = nombre;
    document.getElementById('edit_apellido').value          = apellido;
    document.getElementById('edit_correo').value            = correo;
    document.getElementById('edit_area').value              = area;
    document.getElementById('edit_perfil').value            = perfil;
    document.getElementById('edit_estado').value            = estado;

    const toggle = document.getElementById('edit_sesion_permanente');
    if (toggle) toggle.checked = (sesionPermanente === 1 || sesionPermanente === '1' || sesionPermanente === true);

    document.getElementById('modalEditar').style.display = 'block';
}

function mostrarModalPassword(usuario, nombreCompleto) {
    document.getElementById('pass_usuario_red').value          = usuario;
    document.getElementById('pass_display_nombre').textContent = `${nombreCompleto} (${usuario})`;
    document.getElementById('nueva_password').value            = '';
    document.getElementById('confirmar_password').value        = '';
    document.getElementById('password-error').textContent      = '';
    document.getElementById('modalPassword').style.display     = 'block';
}

function mostrarModalAgregar() {
    document.getElementById('formAgregar').reset();
    const toggle = document.getElementById('add_sesion_permanente');
    if (toggle) toggle.checked = false;
    document.getElementById('modalAgregar').style.display = 'block';
}

function cerrarModal(id) {
    document.getElementById(id).style.display = 'none';
}

function confirmarEliminar(usuario, nombre) {
    if (confirm(`⚠️ ¿Eliminar al usuario?\n\nUsuario: ${usuario}\nNombre: ${nombre}\n\nEsta acción NO se puede deshacer.`)) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/eliminar_usuario';
        const inp  = document.createElement('input');
        inp.type   = 'hidden';
        inp.name   = 'usuario_red';
        inp.value  = usuario;
        form.appendChild(inp);
        document.body.appendChild(form);
        mostrarOverlayProcesando('Eliminando usuario...');
        form.submit();
    }
}

function mostrarOverlayProcesando(msg) {
    const overlay = document.createElement('div');
    overlay.id = 'overlay-procesando';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.7);display:flex;justify-content:center;align-items:center;z-index:9999;';
    overlay.innerHTML = `
        <div style="background:white;padding:30px;border-radius:10px;text-align:center;">
            <div style="border:4px solid #f3f3f3;border-top:4px solid #0166ff;border-radius:50%;width:40px;height:40px;animation:spin 1s linear infinite;margin:0 auto 15px;"></div>
            <p style="margin:0;font-size:16px;color:#333;">${msg}</p>
        </div>`;
    const style = document.createElement('style');
    style.textContent = '@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}';
    document.head.appendChild(style);
    document.body.appendChild(overlay);
}

// ============================================
// GRÁFICA: USO POR HORA
// ============================================

function inicializarChart() {
    const canvas = document.getElementById('chartUsoHoras');
    if (!canvas) return;
    if (typeof HISTOGRAMA_HORAS === 'undefined') return;

    const etiquetas  = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2,'0')}:00`);
    const maxVal     = Math.max(...HISTOGRAMA_HORAS, 1);
    const colores    = HISTOGRAMA_HORAS.map(v =>
        v === maxVal   ? '#0052cc' :
        v >= maxVal*.7 ? '#0166ff' :
        v >= maxVal*.4 ? '#4d94ff' : '#b3d1ff'
    );

    new Chart(canvas, {
        type: 'bar',
        data: {
            labels:   etiquetas,
            datasets: [{
                label:           'Logins',
                data:            HISTOGRAMA_HORAS,
                backgroundColor: colores,
                borderRadius:    4,
                borderSkipped:   false,
            }]
        },
        options: {
            responsive:          true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: ctx => `Hora ${ctx[0].label}`,
                        label: ctx => ` ${ctx.parsed.y} login${ctx.parsed.y !== 1 ? 's' : ''}`,
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 11 }, maxRotation: 0 }
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1,
                        font: { size: 11 },
                        callback: v => Number.isInteger(v) ? v : null,
                    },
                    grid: { color: '#f0f0f0' }
                }
            }
        }
    });
}

// ============================================
// VALIDACIONES DE FORMULARIOS
// ============================================

function setupFormValidations() {
    // ── Formulario Editar ────────────────────────────────────────
    const formEditar = document.getElementById('formEditar');
    if (formEditar) {
        formEditar.addEventListener('submit', function(e) {
            const nombre   = document.getElementById('edit_nombre').value.trim();
            const apellido = document.getElementById('edit_apellido').value.trim();
            const correo   = document.getElementById('edit_correo').value.trim();
            const area     = document.getElementById('edit_area').value.trim();
            const perfil   = document.getElementById('edit_perfil').value;
            const estado   = document.getElementById('edit_estado').value;

            if (!nombre || !apellido || !correo || !area || !perfil || !estado) {
                e.preventDefault();
                alert('⚠️ Complete todos los campos obligatorios.');
                return false;
            }
            const emailRx = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRx.test(correo)) {
                e.preventDefault();
                alert('⚠️ El correo electrónico no es válido.');
                return false;
            }
            const sesion = document.getElementById('edit_sesion_permanente')?.checked;
            if (sesion && !confirm('⚠️ ATENCIÓN: Sesión SIN TIMEOUT\n\nLa sesión NUNCA expirará. ¿Continuar?')) {
                e.preventDefault(); return false;
            }
            if (!confirm('¿Guardar los cambios de este usuario?')) {
                e.preventDefault(); return false;
            }
            mostrarOverlayProcesando('Guardando...');
        });
    }

    // ── Formulario Password ──────────────────────────────────────
    const formPassword = document.getElementById('formPassword');
    if (formPassword) {
        const npwd = document.getElementById('nueva_password');
        const cpwd = document.getElementById('confirmar_password');
        const err  = document.getElementById('password-error');

        cpwd.addEventListener('input', () => {
            if (npwd.value === cpwd.value) { err.textContent = ''; cpwd.style.borderColor = ''; }
            else { err.textContent = '❌ Las contraseñas no coinciden'; cpwd.style.borderColor = 'red'; }
        });

        formPassword.addEventListener('submit', function(e) {
            if (npwd.value !== cpwd.value) {
                e.preventDefault(); err.textContent = '❌ Las contraseñas no coinciden'; return false;
            }
            if (!/^(?=.*\d)(?=.*[a-z])(?=.*[A-Z]).{8,}$/.test(npwd.value)) {
                e.preventDefault(); alert('⚠️ La contraseña debe tener:\n- 8 caracteres mínimo\n- Mayúsculas\n- Minúsculas\n- Números'); return false;
            }
            if (!confirm('¿Cambiar contraseña?')) { e.preventDefault(); return false; }
            mostrarOverlayProcesando('Cambiando contraseña...');
        });
    }

    // ── Formulario Agregar ───────────────────────────────────────
    const formAgregar = document.getElementById('formAgregar');
    if (formAgregar) {
        formAgregar.addEventListener('submit', function(e) {
            const campos = {
                'nombre':      document.getElementById('add_nombre').value.trim(),
                'apellido':    document.getElementById('add_apellido').value.trim(),
                'usuario':     document.getElementById('add_usuario_red').value.trim(),
                'correo':      document.getElementById('add_correo').value.trim(),
                'área':        document.getElementById('add_area').value.trim(),
                'perfil':      document.getElementById('add_perfil').value,
                'contraseña':  document.getElementById('add_password').value,
            };
            for (const [campo, val] of Object.entries(campos)) {
                if (!val) { e.preventDefault(); alert(`⚠️ Complete el campo: ${campo}`); return false; }
            }
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(campos.correo)) {
                e.preventDefault(); alert('⚠️ Correo electrónico inválido'); return false;
            }
            if (!/^(?=.*\d)(?=.*[a-z])(?=.*[A-Z]).{8,}$/.test(campos.contraseña)) {
                e.preventDefault(); alert('⚠️ La contraseña debe tener:\n- 8 caracteres mínimo\n- Mayúsculas\n- Minúsculas\n- Números'); return false;
            }
            const sesion = document.getElementById('add_sesion_permanente')?.checked;
            if (sesion && !confirm('⚠️ Sesión SIN TIMEOUT para nuevo usuario. ¿Continuar?')) {
                e.preventDefault(); return false;
            }
            if (!confirm('¿Crear este usuario?')) { e.preventDefault(); return false; }
            mostrarOverlayProcesando('Creando usuario...');
        });
    }
}

// ============================================
// INICIALIZACIÓN
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    // Inicializar contador y filtros
    aplicarFiltros();

    // Tiempo relativo en columna Último Acceso
    renderizarUltimosAccesos();
    // Actualizar cada minuto
    setInterval(renderizarUltimosAccesos, 60000);

    // Gráfica
    inicializarChart();

    // Búsqueda en tiempo real
    document.getElementById('buscarUsuario')?.addEventListener('input', aplicarFiltros);

    // Validaciones
    setupFormValidations();

    // Cerrar modales con ESC o clic fuera
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            ['modalEditar','modalPassword','modalAgregar'].forEach(cerrarModal);
        }
    });
    window.onclick = function(e) {
        ['modalEditar','modalPassword','modalAgregar'].forEach(id => {
            if (e.target === document.getElementById(id)) cerrarModal(id);
        });
    };

    // Auto-cerrar alertas flash
    document.querySelectorAll('.alert').forEach(a => {
        setTimeout(() => {
            a.style.transition = 'opacity .5s';
            a.style.opacity = '0';
            setTimeout(() => a.remove(), 500);
        }, 5000);
    });

    console.log('✓ gestion_usuarios.js cargado');
});