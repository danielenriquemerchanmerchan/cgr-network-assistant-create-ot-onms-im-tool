/* ============================================
   n1.js  -  Monitoreo N1 | SmartSOC
   ============================================ */

   'use strict';

   /* ---------- Estado global ---------- */
   const STATE = {
       bandeja: {
           datos: [],
           datosFiltrados: [],
           filtros: {}
       },
       retencion: {
           datos: [],
           datosFiltrados: [],
           filtros: {}
       },
       ot: null,
       incidente: null
   };
   
   /* ---------- Filtro de columna activo ---------- */
   let filtroActivo = { tabla: null, col: null };
   
   /* ---------- Auto-refresh ---------- */
   const AUTO_REFRESH_MS = 10 * 60 * 1000;
   let autoRefreshTimer = null;
   let countdownTimer   = null;
   let segundosRestantes = AUTO_REFRESH_MS / 1000;
   
   function iniciarAutoRefresh() {
       detenerAutoRefresh();
       segundosRestantes = AUTO_REFRESH_MS / 1000;
       actualizarCountdown();
       countdownTimer = setInterval(() => {
           segundosRestantes--;
           actualizarCountdown();
       }, 1000);
       autoRefreshTimer = setTimeout(() => {
           cargarTodo();
           iniciarAutoRefresh();
       }, AUTO_REFRESH_MS);
   }
   
   function detenerAutoRefresh() {
       if (autoRefreshTimer) clearTimeout(autoRefreshTimer);
       if (countdownTimer)   clearInterval(countdownTimer);
   }
   
   function actualizarCountdown() {
       const el = document.getElementById('countdownLabel');
       if (!el) return;
       const min = Math.floor(segundosRestantes / 60);
       const sec = segundosRestantes % 60;
       el.textContent = `Próxima actualización en ${min}:${String(sec).padStart(2, '0')}`;
   }
   
   /* ========================================
      INIT
      ======================================== */
   document.addEventListener('DOMContentLoaded', () => {
       cargarTodo();
       initFilterModal();
       iniciarAutoRefresh();
   });
   
   function cargarTodo() {
       const ahora = new Date();
       document.getElementById('ultimaActualizacion').textContent =
           'Última actualización: ' + ahora.toLocaleTimeString('es-CO');
       cargarBandeja();
       cargarRetencion();
       cargarStatsRetencion();
       iniciarAutoRefresh();
   }
   
   /* ========================================
      SECCIÓN 1 – BANDEJA BACKOFFICE
      ======================================== */
   
   function categorizarIdblock(idblock) {
       if (!idblock) return 'OTHERS';
       const val = idblock.toUpperCase();
       if (val.includes('FUSION'))   return 'HL5';
       if (val.includes('GRAFANA'))  return 'IPTV';
       if (val.includes('MASIVO'))   return 'Performance Fusión';
       if (val.includes('SOC_FIJA')) return 'Anillos y Cabeceras';
       return 'OTHERS';
   }
   
   function cargarBandeja() {
       mostrarLoading('bodyBandeja', 10);
       document.getElementById('totalBandeja').textContent = 'Cargando...';
   
       fetch('/api/n1/bandeja_backoffice')
           .then(r => r.json())
           .then(data => {
               if (data.success) {
                   const datos = (data.datos || []).map(row => ({
                       ...row,
                       CATEGORIA:  categorizarIdblock(row.IDBLOCK),
                       ANTIGUEDAD: calcularAntiguedadBadge(row.FECHA_INICIO || '').dataValue
                   }));
                   STATE.bandeja.datos = datos;
                   STATE.bandeja.datosFiltrados = [...datos];
                   renderTablaBandeja(STATE.bandeja.datosFiltrados);
               } else {
                   mostrarError('bodyBandeja', 10, data.error || 'Error al cargar datos');
                   resetContadores();
               }
           })
           .catch(err => {
               console.error('Error bandeja:', err);
               mostrarError('bodyBandeja', 10, 'Error de conexión');
               resetContadores();
           });
   }
   
   function resetContadores() {
       ['cntHl5','cntIptv','cntPerformance','cntAnillos','cntOthers',
        'cntVencidas','cntEnTiempo'].forEach(id => {
           const el = document.getElementById(id);
           if (el) el.textContent = '0';
       });
   }
   
   function actualizarContadores(datos) {
       const conteo = {
           'HL5': 0, 'IPTV': 0,
           'Performance Fusión': 0, 'Anillos y Cabeceras': 0, 'OTHERS': 0
       };
       let vencidas = 0, enTiempo = 0;
   
       datos.forEach(row => {
           const cat = row.CATEGORIA || 'OTHERS';
           if (conteo.hasOwnProperty(cat)) conteo[cat]++;
           else conteo['OTHERS']++;
   
           if (calcularAntiguedadBadge(row.FECHA_INICIO || '').vencida) vencidas++;
           else enTiempo++;
       });
   
       document.getElementById('cntHl5').textContent         = conteo['HL5'];
       document.getElementById('cntIptv').textContent        = conteo['IPTV'];
       document.getElementById('cntPerformance').textContent = conteo['Performance Fusión'];
       document.getElementById('cntAnillos').textContent     = conteo['Anillos y Cabeceras'];
       document.getElementById('cntOthers').textContent      = conteo['OTHERS'];
   
       const elV = document.getElementById('cntVencidas');
       const elT = document.getElementById('cntEnTiempo');
       if (elV) elV.textContent = vencidas;
       if (elT) elT.textContent = enTiempo;
   }
   
   const CATEGORIA_STYLE = {
       'HL5':                 { cls: 'cat-hl5',         icono: 'radio-outline' },
       'IPTV':                { cls: 'cat-iptv',         icono: 'tv-outline' },
       'Performance Fusión':  { cls: 'cat-performance',  icono: 'analytics-outline' },
       'Anillos y Cabeceras': { cls: 'cat-anillos',      icono: 'git-branch-outline' },
       'OTHERS':              { cls: 'cat-others',       icono: 'help-circle-outline' }
   };
   
   function renderCategoriaBadge(categoria) {
       const style = CATEGORIA_STYLE[categoria] || CATEGORIA_STYLE['OTHERS'];
       return `<span class="categoria-badge ${style.cls}">
                   <ion-icon name="${style.icono}"></ion-icon>
                   ${categoria}
               </span>`;
   }
   
   function renderTablaBandeja(datos) {
       const tbody = document.getElementById('bodyBandeja');
       const total = datos.length;
   
       document.getElementById('totalBandeja').textContent = total + ' registro' + (total !== 1 ? 's' : '');
       document.getElementById('badgeBandeja').textContent = total;
       actualizarContadores(datos);
   
       if (total === 0) {
           tbody.innerHTML = '<tr class="empty-row"><td colspan="10">Sin registros activos</td></tr>';
           return;
       }
   
       tbody.innerHTML = datos.map(row => {
           const estadoInc  = renderEstadoBadge(row.ESTADO);
           const estadoOt   = renderEstadoBadge(row.ESTADO_OT);
           const catBadge   = renderCategoriaBadge(row.CATEGORIA);
           const ant        = calcularAntiguedadBadge(row.FECHA_INICIO || '');
           const otCell     = row.OT
               ? `<span class="ot-numero">${row.OT}</span>`
               : `<span class="sin-ot">Sin OT</span>`;
           const btnAcciones = row.OT
               ? `<button class="btn-acciones btn-acciones-bandeja" onclick="abrirModal('${row.OT}','${row.INCIDENTE}','bandeja',${JSON.stringify(row).replace(/"/g,'&quot;')})">
                      <ion-icon name="create-outline"></ion-icon> Gestionar
                  </button>`
               : `<button class="btn-acciones" disabled title="Sin OT asignada">Sin OT</button>`;
   
           return `<tr${ant.vencida ? ' class="row-vencida"' : ''}>
               <td><strong>${row.INCIDENTE || '—'}</strong></td>
               <td class="resumen-cell" title="${(row.RESUMEN || '').replace(/"/g,'&quot;')}">${row.RESUMEN || '—'}</td>
               <td>${row.FECHA_INICIO || '—'}</td>
               <td>${estadoInc}</td>
               <td>${otCell}</td>
               <td>${estadoOt}</td>
               <td>${row.GRUPO_OT || '—'}</td>
               <td>${catBadge}</td>
               <td data-value="${ant.dataValue}">${ant.html}</td>
               <td>${btnAcciones}</td>
           </tr>`;
       }).join('');
   }
   
   /* ========================================
      SECCIÓN 2 – RETENCIÓN HL5
      ======================================== */
   function cargarRetencion() {
       mostrarLoading('bodyRetencion', 10);
       document.getElementById('totalRetencion').textContent = 'Cargando...';
   
       fetch('/api/n1/retencion_hl5')
           .then(r => r.json())
           .then(data => {
               if (data.success) {
                   STATE.retencion.datos = data.datos || [];
                   STATE.retencion.datosFiltrados = [...STATE.retencion.datos];
                   renderTablaRetencion(STATE.retencion.datosFiltrados);
               } else {
                   mostrarError('bodyRetencion', 10, data.error || 'Error al cargar datos');
               }
           })
           .catch(err => {
               console.error('Error retencion:', err);
               mostrarError('bodyRetencion', 10, 'Error de conexión');
           });
   }
   
   function renderTablaRetencion(datos) {
       const tbody = document.getElementById('bodyRetencion');
       const total = datos.length;
   
       document.getElementById('totalRetencion').textContent = total + ' registro' + (total !== 1 ? 's' : '');
       document.getElementById('badgeRetencion').textContent = total;
   
       if (total === 0) {
           tbody.innerHTML = '<tr class="empty-row"><td colspan="10">Sin registros activos</td></tr>';
           return;
       }
   
       tbody.innerHTML = datos.map(row => {
           const estadoOt  = renderEstadoBadge(row.ESTADO_OT);
           const otCell    = row.OT
               ? `<span class="ot-numero">${row.OT}</span>`
               : `<span class="sin-ot">Sin OT</span>`;
           const btnAcciones = row.OT
               ? `<button class="btn-acciones" onclick="abrirModal('${row.OT}','${row.INCIDENTE}','retencion',${JSON.stringify(row).replace(/"/g,'&quot;')})">
                      <ion-icon name="create-outline"></ion-icon> Gestionar
                  </button>`
               : `<button class="btn-acciones" disabled title="Sin OT asignada">Sin OT</button>`;
   
           return `<tr>
               <td><strong>${row.INCIDENTE || '—'}</strong></td>
               <td>${row.NODO || '—'}</td>
               <td class="celda-mono">${row.IP || '—'}</td>
               <td>${row.UBICACION || '—'}</td>
               <td class="resumen-cell" title="${(row.RESUMEN || '').replace(/"/g,'&quot;')}">${row.RESUMEN || '—'}</td>
               <td>${row.FECHA_INICIO || '—'}</td>
               <td>${otCell}</td>
               <td>${estadoOt}</td>
               <td>${row.TIPO_RETENCION ? `<span class="tipo-retencion-badge">${row.TIPO_RETENCION}</span>` : '—'}</td>
               <td>${btnAcciones}</td>
           </tr>`;
       }).join('');
   }
   
   /* ========================================
      ESTADÍSTICAS RETENCIÓN HL5
      ======================================== */
   function cargarStatsRetencion() {
       // Mostrar estado de carga
       ['statRetencion', 'statEscaladas', 'statCerradas'].forEach(id => {
           const el = document.getElementById(id);
           if (el) { el.textContent = '…'; el.classList.add('cargando'); }
       });
   
       fetch('/api/n1/stats_retencion_hl5')
           .then(r => r.json())
           .then(data => renderStatsRetencion(data))
           .catch(err => {
               console.error('Error stats retencion:', err);
               renderStatsRetencion({ success: false, cerradas: 0, escaladas: 0, retencion: 0 });
           });
   }
   
   function renderStatsRetencion(data) {
       const set = (id, val) => {
           const el = document.getElementById(id);
           if (!el) return;
           el.textContent = data.success ? val : '—';
           el.classList.remove('cargando');
       };
       set('statRetencion', data.retencion ?? 0);
       set('statEscaladas', data.escaladas ?? 0);
       set('statCerradas',  data.cerradas  ?? 0);
   }
   
   /* ========================================
      MODAL DE ACCIONES OT
      ======================================== */
   function abrirModal(ot, incidente, tabla, rowData) {
       STATE.ot = ot;
       STATE.incidente = incidente;
   
       let infoHTML = '<div class="modal-info">';
       infoHTML += fila('OT', `<span class="ot-numero">${ot}</span>`);
       infoHTML += fila('Incidente', incidente || '—');
       if (rowData.NODO)           infoHTML += fila('Nodo HL5', rowData.NODO);
       if (rowData.IP)             infoHTML += fila('IP', rowData.IP);
       if (rowData.UBICACION)      infoHTML += fila('Ubicación', rowData.UBICACION);
       if (rowData.RESUMEN)        infoHTML += fila('Resumen', rowData.RESUMEN);
       if (rowData.FECHA_INICIO)   infoHTML += fila('Fecha Inicio', rowData.FECHA_INICIO);
       if (rowData.TIPO_RETENCION) infoHTML += fila('Tipo Retención', rowData.TIPO_RETENCION);
       if (rowData.HORAS != null)  infoHTML += fila('Horas', rowData.HORAS + 'h');
       infoHTML += fila('Estado OT', renderEstadoBadge(rowData.ESTADO_OT));
       infoHTML += fila('Grupo', rowData.GRUPO_OT || '—');
       infoHTML += '</div>';
   
       document.getElementById('modalInfo').innerHTML = infoHTML;
       volverMenu();
       document.getElementById('modalAcciones').classList.add('activo');
   }
   
   function cerrarModal() {
       document.getElementById('modalAcciones').classList.remove('activo');
       STATE.ot = null;
       STATE.incidente = null;
       limpiarFormularios();
   }
   
   function cerrarModalSiOverlay(e) {
       if (e.target === document.getElementById('modalAcciones')) cerrarModal();
   }
   
   function volverMenu() {
       document.getElementById('menuOpciones').style.display = 'flex';
       document.getElementById('formAvance').style.display   = 'none';
       document.getElementById('formCerrar').style.display   = 'none';
       document.getElementById('formEscalar').style.display  = 'none';
       limpiarFormularios();
   }
   
   function mostrarFormulario(tipo) {
       document.getElementById('menuOpciones').style.display = 'none';
       document.getElementById('formAvance').style.display   = tipo === 'avance'  ? 'block' : 'none';
       document.getElementById('formCerrar').style.display   = tipo === 'cerrar'  ? 'block' : 'none';
       document.getElementById('formEscalar').style.display  = tipo === 'escalar' ? 'block' : 'none';
   }
   
   function limpiarFormularios() {
       ['avanceComentario','cierreComentario','escalarMotivo'].forEach(id => {
           const el = document.getElementById(id); if (el) el.value = '';
       });
       ['cierreEstado','escalarArea'].forEach(id => {
           const el = document.getElementById(id); if (el) el.value = '';
       });
   }
   
   /* ---- Acciones API ---- */
   function enviarAvance(e) {
       e.preventDefault();
       const comentario = document.getElementById('avanceComentario').value.trim();
       if (!comentario || !STATE.ot) return;
       const btn = e.target.querySelector('button[type="submit"]');
       const otActual = STATE.ot;
       setLoadingBtn(btn, true, 'Guardando...');
       fetch('/api/hl5/gestionar-ot', {
           method: 'POST', headers: {'Content-Type': 'application/json'},
           body: JSON.stringify({ ot: otActual, tipo_accion: 'AVANCE', comentario, incidente: STATE.incidente || '' })
       })
       .then(r => r.json())
       .then(data => {
           cerrarModal();
           mostrarToast(data.success ? 'success' : 'error',
               data.success ? `✅ Avance registrado en OT ${otActual}` : `❌ ${data.error || data.message}`);
           if (data.success) cargarTodo();
       })
       .catch(() => mostrarToast('error', '❌ Error de conexión'))
       .finally(() => setLoadingBtn(btn, false, 'Guardar Avance'));
   }
   
   function cerrarOT(e) {
       e.preventDefault();
       const comentario = document.getElementById('cierreComentario').value.trim();
       const estado     = document.getElementById('cierreEstado').value;
       if (!comentario || !estado || !STATE.ot) return;
       const btn = e.target.querySelector('button[type="submit"]');
       const otActual = STATE.ot;
       setLoadingBtn(btn, true, 'Cerrando...');
       fetch('/api/hl5/gestionar-ot', {
           method: 'POST', headers: {'Content-Type': 'application/json'},
           body: JSON.stringify({ ot: otActual, tipo_accion: 'CERRAR', comentario, estado, incidente: STATE.incidente || '' })
       })
       .then(r => r.json())
       .then(data => {
           cerrarModal();
           mostrarToast(data.success ? 'success' : 'error',
               data.success ? `✅ OT ${otActual} cerrada correctamente` : `❌ ${data.error || data.message}`);
           if (data.success) cargarTodo();
       })
       .catch(() => mostrarToast('error', '❌ Error de conexión'))
       .finally(() => setLoadingBtn(btn, false, 'Cerrar OT'));
   }
   
   function escalarOT(e) {
       e.preventDefault();
       const area   = document.getElementById('escalarArea').value;
       const motivo = document.getElementById('escalarMotivo').value.trim();
       if (!area || !motivo || !STATE.ot) return;
       const btn = e.target.querySelector('button[type="submit"]');
       const otActual = STATE.ot;
       setLoadingBtn(btn, true, 'Escalando...');
       fetch('/api/hl5/gestionar-ot', {
           method: 'POST', headers: {'Content-Type': 'application/json'},
           body: JSON.stringify({ ot: otActual, tipo_accion: 'ESCALAR', area_destino: area, motivo, incidente: STATE.incidente || '' })
       })
       .then(r => r.json())
       .then(data => {
           cerrarModal();
           mostrarToast(data.success ? 'success' : 'error',
               data.success ? `✅ OT ${otActual} escalada a ${area}` : `❌ ${data.error || data.message}`);
           if (data.success) cargarTodo();
       })
       .catch(() => mostrarToast('error', '❌ Error de conexión'))
       .finally(() => setLoadingBtn(btn, false, 'Escalar OT'));
   }
   
   /* ========================================
      FILTROS DE COLUMNA
      ======================================== */
   function initFilterModal() {
       document.addEventListener('click', e => {
           const icon = e.target.closest('.filter-icon');
           if (icon) abrirFiltroColumna(icon.dataset.tabla, icon.dataset.col);
       });
       document.querySelector('.filter-modal-close').addEventListener('click', cerrarFiltro);
       document.getElementById('filter-btn-cancel').addEventListener('click', cerrarFiltro);
       document.getElementById('filter-btn-ok').addEventListener('click', aplicarFiltro);
       document.getElementById('filter-select-all').addEventListener('click', () => {
           document.querySelectorAll('#filter-options-container input[type="checkbox"]').forEach(cb => cb.checked = true);
       });
       document.getElementById('filter-clear').addEventListener('click', () => {
           document.querySelectorAll('#filter-options-container input[type="checkbox"]').forEach(cb => cb.checked = false);
       });
       document.getElementById('filter-search-input').addEventListener('input', e => {
           const q = e.target.value.toLowerCase();
           document.querySelectorAll('.filter-option').forEach(opt => {
               opt.style.display = opt.textContent.toLowerCase().includes(q) ? '' : 'none';
           });
       });
       document.getElementById('filter-modal').addEventListener('click', e => {
           if (e.target === document.getElementById('filter-modal')) cerrarFiltro();
       });
   }
   
   function abrirFiltroColumna(tabla, col) {
       filtroActivo = { tabla, col };
       const stateTabla = STATE[tabla];
       const valoresUnicos = [...new Set(stateTabla.datos.map(r => String(r[col] ?? '')))].sort();
       const filtrosActivos = stateTabla.filtros[col] || null;
   
       document.getElementById('filter-options-container').innerHTML = valoresUnicos.map(v => {
           const checked = !filtrosActivos || filtrosActivos.has(v) ? 'checked' : '';
           return `<label class="filter-option"><input type="checkbox" value="${v}" ${checked}> ${v || '(vacío)'}</label>`;
       }).join('');
   
       document.getElementById('filter-search-input').value = '';
       document.getElementById('filter-modal').classList.add('activo');
   }
   
   function cerrarFiltro() {
       document.getElementById('filter-modal').classList.remove('activo');
       filtroActivo = { tabla: null, col: null };
   }
   
   function aplicarFiltro() {
       const { tabla, col } = filtroActivo;
       if (!tabla || !col) { cerrarFiltro(); return; }
   
       const checks = [...document.querySelectorAll('#filter-options-container input[type="checkbox"]')];
       const seleccionados = checks.filter(c => c.checked).map(c => c.value);
       const stateTabla = STATE[tabla];
       const totalUnicos = new Set(stateTabla.datos.map(r => String(r[col] ?? ''))).size;
   
       if (seleccionados.length === totalUnicos) {
           delete stateTabla.filtros[col];
       } else {
           stateTabla.filtros[col] = new Set(seleccionados);
       }
   
       document.querySelectorAll(`.filter-icon[data-tabla="${tabla}"][data-col="${col}"]`)
           .forEach(ic => ic.classList.toggle('active', !!stateTabla.filtros[col]));
   
       aplicarFiltrosTabla(tabla);
       cerrarFiltro();
   }
   
   function aplicarFiltrosTabla(tabla) {
       const stateTabla = STATE[tabla];
       stateTabla.datosFiltrados = stateTabla.datos.filter(row =>
           Object.entries(stateTabla.filtros).every(([col, valores]) => valores.has(String(row[col] ?? '')))
       );
       if (tabla === 'bandeja')   renderTablaBandeja(stateTabla.datosFiltrados);
       if (tabla === 'retencion') renderTablaRetencion(stateTabla.datosFiltrados);
   }
   
   function limpiarFiltros(tabla) {
       STATE[tabla].filtros = {};
       STATE[tabla].datosFiltrados = [...STATE[tabla].datos];
       document.querySelectorAll(`.filter-icon[data-tabla="${tabla}"]`).forEach(ic => ic.classList.remove('active'));
       // Limpiar estado activo de cards contadores
       document.querySelectorAll('.contador-card, .ant-card').forEach(c => c.classList.remove('activo'));
       if (tabla === 'bandeja')   renderTablaBandeja(STATE.bandeja.datosFiltrados);
       if (tabla === 'retencion') renderTablaRetencion(STATE.retencion.datosFiltrados);
   }
   
   /* ---- Filtro rápido desde los cards de estadísticas ---- */
   // filtrarPorContador: clic en un card aplica un filtro de valor único en la tabla bandeja.
   // Si el mismo card se vuelve a clicar, quita el filtro (toggle).
   const CARD_ID_MAP = {
       'CATEGORIA:HL5':                  '.contador-hl5',
       'CATEGORIA:IPTV':                 '.contador-iptv',
       'CATEGORIA:Performance Fusión':   '.contador-performance',
       'CATEGORIA:Anillos y Cabeceras':  '.contador-anillos',
       'CATEGORIA:OTHERS':               '.contador-others',
       'ANTIGUEDAD:> 1 día':             '#cntVencidasCard',
       'ANTIGUEDAD:≤ 1 día':             '#cntEnTiempoCard',
   };
   
   function filtrarPorContador(col, valor) {
       const tabla     = 'bandeja';
       const stateTabla = STATE[tabla];
       const cardKey   = `${col}:${valor}`;
       const cardSel   = CARD_ID_MAP[cardKey];
       const cardEl    = cardSel ? document.querySelector(cardSel) : null;
       const yaActivo  = cardEl && cardEl.classList.contains('activo');
   
       // Quitar estado activo de TODOS los cards de conteo
       document.querySelectorAll('.contador-card, .ant-card').forEach(c => c.classList.remove('activo'));
   
       if (yaActivo) {
           // Toggle OFF: quitar el filtro de esta columna y mostrar todo
           delete stateTabla.filtros[col];
           document.querySelectorAll(`.filter-icon[data-tabla="${tabla}"][data-col="${col}"]`)
               .forEach(ic => ic.classList.remove('active'));
       } else {
           // Toggle ON: aplicar filtro de valor único
           stateTabla.filtros[col] = new Set([valor]);
           document.querySelectorAll(`.filter-icon[data-tabla="${tabla}"][data-col="${col}"]`)
               .forEach(ic => ic.classList.add('active'));
           if (cardEl) cardEl.classList.add('activo');
       }
   
       aplicarFiltrosTabla(tabla);
   }
   
   /* ========================================
      UTILIDADES
      ======================================== */
   function parsearFechaBandeja(str) {
       if (!str || str.trim() === '' || str.trim() === '-' || str.trim() === 'N/A') return null;
       str = str.trim();
       let m = str.match(/^(\d{2})\/(\d{2})\/(\d{4})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/);
       if (m) return new Date(+m[3], +m[2]-1, +m[1], +(m[4]||0), +(m[5]||0), +(m[6]||0));
       m = str.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/);
       if (m) return new Date(+m[1], +m[2]-1, +m[3], +(m[4]||0), +(m[5]||0), +(m[6]||0));
       const d = new Date(str);
       return isNaN(d) ? null : d;
   }
   
   function calcularAntiguedadBadge(fechaStr) {
       const UN_DIA_MS = 24 * 60 * 60 * 1000;
       const fecha     = parsearFechaBandeja(fechaStr);
       const vencida   = fecha && (Date.now() - fecha.getTime()) > UN_DIA_MS;
       return {
           vencida,
           html     : vencida
               ? '<span class="badge-antiguedad badge-vencida"><ion-icon name="warning-outline"></ion-icon> &gt; 1 día</span>'
               : '<span class="badge-antiguedad badge-en-tiempo"><ion-icon name="checkmark-circle-outline"></ion-icon> &le; 1 día</span>',
           dataValue: vencida ? '> 1 día' : '≤ 1 día'
       };
   }
   
   function mostrarLoading(tbodyId, cols) {
       document.getElementById(tbodyId).innerHTML =
           `<tr><td colspan="${cols}" class="loading"><div class="spinner"></div> Cargando datos...</td></tr>`;
   }
   
   function mostrarError(tbodyId, cols, msg) {
       document.getElementById(tbodyId).innerHTML =
           `<tr class="empty-row"><td colspan="${cols}">⚠️ ${msg}</td></tr>`;
   }
   
   function renderEstadoBadge(estado) {
       if (!estado) return '<span class="estado-badge estado-default">—</span>';
       const mapa = {
           'INPRG': 'estado-inprg', 'APPR': 'estado-appr',
           'COMP':  'estado-comp',  'CLOSE': 'estado-close',
           'CANCEL':'estado-cancel','WAPPR': 'estado-wappr',
           'ESCALADE':'estado-escalade'
       };
       return `<span class="estado-badge ${mapa[estado.toUpperCase()] || 'estado-default'}">${estado}</span>`;
   }
   
   function renderHoras(h) {
       if (h == null || h === '') return '<span class="horas-ok">—</span>';
       const n = parseFloat(h);
       let cls = n > 24 ? 'horas-danger' : n > 8 ? 'horas-warn' : 'horas-ok';
       return `<span class="${cls}">${n.toFixed(1)}h</span>`;
   }
   
   function fila(label, value) {
       return `<div class="modal-info-row">
           <span class="modal-info-label">${label}</span>
           <span class="modal-info-value">${value}</span>
       </div>`;
   }
   
   function setLoadingBtn(btn, loading, text) {
       if (!btn) return;
       btn.disabled = loading;
       btn.classList.toggle('loading-btn', loading);
       btn.textContent = text;
   }
   
   function mostrarToast(tipo, mensaje) {
       const toast = document.getElementById('toastNotif');
       toast.className = `toast-notif toast-${tipo}`;
       toast.textContent = mensaje;
       toast.style.display = 'block';
       setTimeout(() => { toast.style.display = 'none'; }, 4500);
   }