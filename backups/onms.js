/* ============================================
   ONMS — Monitoreo de Cortes Fibra Óptica
   SmartSOC — versión definitiva
   ============================================ */

   'use strict';

   const UMBRAL_CON_AFECTA = 30;
   const UMBRAL_SIN_AFECTA = 60;
   const UMBRAL_WARN_CON   = 20;
   const UMBRAL_WARN_SIN   = 45;
   
   const ONMS_DATOS = [];
   let   onmsDatosActivos = [];
   
   function onmsUmbral(a)     { return a === 'SI' ? UMBRAL_CON_AFECTA : UMBRAL_SIN_AFECTA; }
   function onmsUmbralWarn(a) { return a === 'SI' ? UMBRAL_WARN_CON   : UMBRAL_WARN_SIN;   }
   function onmsEsAlerta(fila) {
       if (!fila.ultAvance || fila.ultAvance === '—') return false;
       return fila.minSinAvance >= onmsUmbral(fila.afectacion);
   }
   
   /* -----------------------------------------------
      INICIALIZACIÓN
      ----------------------------------------------- */
   document.addEventListener('DOMContentLoaded', () => {
       onmsCargarDatos();
       onmsActualizarTimestamp();
       onmsIniciarCountdown(60);
   });
   
   async function onmsCargarDatos() {
       onmsMostrarCargando(true);
       try {
           const resp = await fetch('/api/onms/incidentes');
           if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
           const json = await resp.json();
           if (!json.ok) throw new Error(json.error || 'Error desconocido');
   
           ONMS_DATOS.length = 0;
           json.data.forEach(d => ONMS_DATOS.push(d));
           onmsDatosActivos = [...ONMS_DATOS];
   
           onmsRenderTabla(onmsDatosActivos);
           onmsActualizarKpis(onmsDatosActivos);
       } catch (err) {
           console.error('[ONMS] Error cargando datos:', err);
           onmsToast(`Error al cargar incidentes: ${err.message}`, 'error');
           onmsRenderTabla(onmsDatosActivos);
           onmsActualizarKpis(onmsDatosActivos);
       } finally {
           onmsMostrarCargando(false);
       }
   }
   
   function onmsMostrarCargando(activo) {
       const tbody = document.getElementById('onmsTbody');
       if (!tbody || !activo) return;
       tbody.innerHTML = `<tr class="onms-empty-row">
           <td colspan="15" style="text-align:center;padding:32px;color:#9ca3af;">
               <ion-icon name="sync-outline" style="font-size:20px;animation:spin 1s linear infinite;vertical-align:middle;margin-right:8px;"></ion-icon>
               Cargando incidentes...
           </td></tr>`;
   }
   
   /* -----------------------------------------------
      RENDER TABLA
      Columnas: OT | Afectación | Nodo A | Nodo B | Municipio | Inicio |
                Estado/Etapa | Tipo tramo | Cuadrilla | EECC | Operador FO |
                Últ. avance | T. sin avance | Acciones  → 14 columnas
      ----------------------------------------------- */
   function onmsRenderTabla(datos) {
       const tbody          = document.getElementById('onmsTbody');
       const badgeContador  = document.getElementById('badgeContadorTabla');
       const registrosLabel = document.getElementById('onmsRegistrosLabel');
   
       if (badgeContador)  badgeContador.textContent  = datos.length;
       if (registrosLabel) registrosLabel.textContent = `${datos.length} registros`;
   
       if (!datos.length) {
           tbody.innerHTML = `<tr class="onms-empty-row"><td colspan="14">No hay incidentes que coincidan con los filtros aplicados.</td></tr>`;
           return;
       }
   
       tbody.innerHTML = datos.map(fila => {
           const clsFila       = onmsEsAlerta(fila) ? 'fila-alerta' : '';
           const tipoTramoHTML = fila.tipoTramo
               ? `<span class="onms-badge-tramo">${fila.tipoTramo}</span>`
               : `<span style="color:#9ca3af;font-size:11px;">—</span>`;
           const cuadrillaHTML = fila.cuadrilla
               ? `<span style="font-size:11px;">${fila.cuadrilla}</span>`
               : `<span class="onms-sin-asignar">Sin asignar</span>`;
           const eeccHTML      = fila.eecc
               ? `<span style="font-size:11px;font-weight:500;">${fila.eecc}</span>`
               : `<span style="color:#9ca3af;font-size:11px;">—</span>`;
           const operadorHTML  = fila.operadorFo
               ? `<span style="font-size:11px;">${fila.operadorFo}</span>`
               : `<span style="color:#9ca3af;font-size:11px;">—</span>`;
   
           return `<tr class="${clsFila}" data-ot="${fila.ot}" data-afecta="${fila.afectacion}" data-etapa="${fila.etapa}" data-municipio="${fila.municipio}">
               <td><span class="onms-ot-id">${fila.ot}</span></td>
               <td>${onmsBadgeAfectacion(fila.afectacion)}</td>
               <td style="font-size:11px;">${fila.nodoA}<span class="onms-nodo-sep">→</span></td>
               <td style="font-size:11px;">${fila.nodoB}</td>
               <td style="font-size:11px;">${fila.municipio || '—'}</td>
               <td style="font-size:11px;color:#6b7280;">${fila.inicio}</td>
               <td>${onmsBadgeEtapa(fila.etapa)}</td>
               <td>${tipoTramoHTML}</td>
               <td>${cuadrillaHTML}</td>
               <td>${eeccHTML}</td>
               <td>${operadorHTML}</td>
               <td>${onmsUltAvanceHTML(fila.ultAvance, fila.ultAvanceTitulo, fila.ultAvanceComentario)}</td>
               <td>${onmsTiempoHTML(fila.minSinAvance, fila.etapa, fila.afectacion, fila.ultAvance)}</td>
               <td>${onmsAccionHTML(fila)}</td>
           </tr>`;
       }).join('');
   }
   
   /* -----------------------------------------------
      HELPERS BADGES
      ----------------------------------------------- */
   function onmsBadgeEtapa(etapa) {
       const mapa = {
           'Por Asignar':         'onms-badge-nueva',
           'Desplazamiento':      'onms-badge-desp',
           'Medida':              'onms-badge-medida',
           'Búsqueda':            'onms-badge-busqueda',
           'Hallazgo':            'onms-badge-hallazgo',
           'Diagnóstico':         'onms-badge-diag',
           'Ejecución/Reparación':'onms-badge-ejecucion',
           'Empalmería':          'onms-badge-emp',
           'Validación':          'onms-badge-validacion',
           'Retiro':              'onms-badge-retiro',
       };
       return `<span class="onms-badge ${mapa[etapa] || 'onms-badge-nueva'}">${etapa}</span>`;
   }
   
   function onmsBadgeAfectacion(afecta) {
       return afecta === 'SI'
           ? `<span class="onms-badge onms-badge-afecta">Afecta servicio</span>`
           : `<span class="onms-badge onms-badge-sinafecta">Sin afectación</span>`;
   }
   
   function onmsUltAvanceHTML(hora, titulo, comentario) {
       if (!hora || hora === '—' || !comentario) {
           return `<span style="font-size:11px;color:#9ca3af;">${hora || '—'}</span>`;
       }
       const t = (titulo    || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
       const c = (comentario).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
       return `<div class="onms-avance-cell" onclick="onmsMostrarComentario('${t}','${c}','${hora}')">
           <span class="onms-avance-hora">${hora}</span>
           <span class="onms-avance-ico" title="Ver comentario"><ion-icon name="eye-outline"></ion-icon></span>
       </div>`;
   }
   
   function onmsMostrarComentario(titulo, comentario, hora) {
       document.getElementById('popoverHora').textContent   = hora;
       document.getElementById('popoverTitulo').textContent = titulo;
       document.getElementById('popoverTexto').textContent  = comentario;
       document.getElementById('onmsPopoverAvance').style.display = 'flex';
   }
   
   function onmsTiempoHTML(min, etapa, afectacion, ultAvance) {
       if (!ultAvance || ultAvance === '—') return `<span class="onms-tiempo warn">Sin inicio</span>`;
       const umbral     = onmsUmbral(afectacion);
       const umbralWarn = onmsUmbralWarn(afectacion);
       const texto      = min >= 60 ? `${Math.floor(min/60)}h ${min%60}min` : `${min}min`;
       if (min >= umbral) {
           return `<span class="onms-tiempo crit"><span class="onms-alerta-dot">!</span>${texto}</span>`;
       }
       return `<span class="onms-tiempo ${min >= umbralWarn ? 'warn' : 'ok'}">${texto}</span>`;
   }
   
   function onmsAccionHTML(fila) {
       if (fila.etapa === 'Por Asignar') {
           return `<button class="btn-accion-tabla asignar" onclick="onmsAbrirAsignar('${fila.ot}')">
               <ion-icon name="person-add-outline"></ion-icon> Asignar</button>`;
       }
       if (fila.etapa === 'Validación') {
           return `<button class="btn-accion-tabla confirmar" onclick="onmsAbrirConfirmar('${fila.ot}')">
               <ion-icon name="checkmark-circle-outline"></ion-icon> Confirmar</button>`;
       }
       return `<button class="btn-accion-tabla" onclick="onmsAbrirAvance('${fila.ot}')">
           <ion-icon name="create-outline"></ion-icon> Avance</button>`;
   }
   
   /* -----------------------------------------------
      KPIs
      ----------------------------------------------- */
   const ETAPAS_EN_ATENCION = [
       'Desplazamiento','Medida','Búsqueda','Hallazgo',
       'Diagnóstico','Ejecución/Reparación','Empalmería','Retiro'
   ];
   
   function onmsActualizarKpis(datos) {
       const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
   
       // Tarjetas principales
       set('kpiTotal',     datos.length);
       set('kpiAfecta',    datos.filter(d => d.afectacion === 'SI').length);
       set('kpiNuevas',    datos.filter(d => d.etapa === 'Por Asignar').length);
       set('kpiAtencion',  datos.filter(d => ETAPAS_EN_ATENCION.includes(d.etapa)).length);
       set('kpiPendConf',  datos.filter(d => d.etapa === 'Validación').length);
       set('kpiSinAvance', datos.filter(d => onmsEsAlerta(d)).length);
   
       // Tarjetas por tipo de tramo
       const ct = { RLFO: 0, RTNFO: 0, RDFO: 0, RBHFO: 0, sinTipo: 0 };
       datos.forEach(d => {
           const t = (d.tipoTramo || '').toUpperCase().trim();
           if      (t === 'RLFO')  ct.RLFO++;
           else if (t === 'RTNFO') ct.RTNFO++;
           else if (t === 'RDFO')  ct.RDFO++;
           else if (t === 'RBHFO') ct.RBHFO++;
           else                    ct.sinTipo++;
       });
       set('kpiRLFO',    ct.RLFO);
       set('kpiRTNFO',   ct.RTNFO);
       set('kpiRDFO',    ct.RDFO);
       set('kpiRBHFO',   ct.RBHFO);
       set('kpiSinTipo', ct.sinTipo);
   }
   
   /* -----------------------------------------------
      FILTROS
      ----------------------------------------------- */
   function onmsFiltrar() {
       const estado    = document.getElementById('filtroEstado').value;
       const afecta    = document.getElementById('filtroAfectacion').value;
       const tipoTramo = document.getElementById('filtroTipoTramo') ? document.getElementById('filtroTipoTramo').value : '';
       const region    = document.getElementById('filtroRegion').value;
   
       const filtrado = ONMS_DATOS.filter(d =>
           (!estado    || d.etapa      === estado)    &&
           (!afecta    || d.afectacion === afecta)    &&
           (!tipoTramo || d.tipoTramo  === tipoTramo) &&
           (!region    || (d.municipio || '').toLowerCase().includes(region.toLowerCase()))
       );
       onmsDatosActivos = filtrado;
       onmsRenderTabla(filtrado);
   }
   
   function onmsLimpiarFiltros() {
       ['filtroEstado','filtroAfectacion','filtroTipoTramo','filtroRegion'].forEach(id => {
           const el = document.getElementById(id); if (el) el.value = '';
       });
       onmsDatosActivos = [...ONMS_DATOS];
       onmsRenderTabla(onmsDatosActivos);
   }
   
   /* -----------------------------------------------
      VALIDACIÓN OT
      ----------------------------------------------- */
   function onmsUpdateTramo() {
       const a = document.getElementById('onmsNodoA').value;
       const b = document.getElementById('onmsNodoB').value;
       const el = document.getElementById('onmsTramoPreview');
       if (a && b) { el.textContent = `${a} → ${b}`; el.classList.add('activo'); }
       else        { el.textContent = 'Seleccione nodos A y B'; el.classList.remove('activo'); }
       document.getElementById('onmsOtResultado').style.display = 'none';
   }
   
   function onmsValidarOT() {
       const a   = document.getElementById('onmsNodoA').value;
       const b   = document.getElementById('onmsNodoB').value;
       const div = document.getElementById('onmsOtResultado');
       if (!a || !b) {
           div.innerHTML = `<div class="onms-ot-encontrada"><ion-icon name="warning-outline"></ion-icon>
               <span>Seleccione el nodo A y el nodo B para validar.</span></div>`;
           div.style.display = 'block'; return;
       }
       div.innerHTML = `<div class="onms-ot-nueva"><ion-icon name="checkmark-circle-outline"></ion-icon>
           <span>Validando tramo <strong>${a} → ${b}</strong> en la base de datos...</span></div>`;
       div.style.display = 'block';
   }
   
   /* -----------------------------------------------
      MODALES
      ----------------------------------------------- */
   function onmsAbrirAvance(ot) {
       document.getElementById('avanceOtId').value          = ot;
       document.getElementById('avanceOtLabel').textContent = ot;
       document.getElementById('avanceComentario').value    = '';
       document.getElementById('avanceEtapa').value         = '';
       document.getElementById('onmsModalAvance').style.display = 'flex';
   }
   
   function onmsAbrirAsignar(ot) {
       document.getElementById('asignarOtId').value          = ot;
       document.getElementById('asignarOtLabel').textContent = ot;
       document.getElementById('asignarContratista').value   = '';
       document.getElementById('asignarCuadrilla').value     = '';
       document.getElementById('asignarObs').value           = '';
       document.getElementById('onmsModalAsignar').style.display = 'flex';
   }
   
   function onmsAbrirConfirmar(ot) {
       document.getElementById('confirmarOtId').value           = ot;
       document.getElementById('confirmarOtLabel').textContent  = ot;
       document.getElementById('confirmarComentario').value     = '';
       document.getElementById('onmsModalConfirmar').style.display = 'flex';
   }
   
   function onmsAbrirModalSolicitud() {
       const form = document.querySelector('.seccion-card');
       if (form) form.scrollIntoView({ behavior:'smooth', block:'start' });
       document.getElementById('onmsNodoA').focus();
   }
   
   function onmsCerrarModal(id) {
       document.getElementById(id).style.display = 'none';
   }
   
   document.addEventListener('click', e => {
       ['onmsModalAvance','onmsModalAsignar','onmsModalConfirmar','onmsPopoverAvance'].forEach(id => {
           const modal = document.getElementById(id);
           if (modal && e.target === modal) modal.style.display = 'none';
       });
   });
   
   document.addEventListener('keydown', e => {
       if (e.key === 'Escape') {
           ['onmsModalAvance','onmsModalAsignar','onmsModalConfirmar','onmsPopoverAvance'].forEach(id => {
               const el = document.getElementById(id); if (el) el.style.display = 'none';
           });
       }
   });
   
   /* -----------------------------------------------
      GUARDAR ACCIONES
      ----------------------------------------------- */
   function onmsGuardarAvance() {
       const ot         = document.getElementById('avanceOtId').value;
       const etapa      = document.getElementById('avanceEtapa').value;
       const comentario = document.getElementById('avanceComentario').value.trim();
       if (!etapa || !comentario) { onmsToast('Complete todos los campos requeridos.', 'warning'); return; }
   
       onmsCerrarModal('onmsModalAvance');
       onmsToast(`Avance registrado para OT ${ot}.`, 'success');
       const idx = ONMS_DATOS.findIndex(d => d.ot === ot);
       if (idx !== -1) {
           ONMS_DATOS[idx].etapa               = etapa;
           ONMS_DATOS[idx].minSinAvance        = 0;
           ONMS_DATOS[idx].ultAvance           = onmsHoraActual();
           ONMS_DATOS[idx].ultAvanceComentario = comentario;
       }
       onmsFiltrar();
   }
   
   function onmsGuardarAsignacion() {
       const ot          = document.getElementById('asignarOtId').value;
       const contratista = document.getElementById('asignarContratista').value;
       const cuadrilla   = document.getElementById('asignarCuadrilla').value;
       if (!contratista || !cuadrilla) { onmsToast('Seleccione contratista y cuadrilla.', 'warning'); return; }
   
       onmsCerrarModal('onmsModalAsignar');
       onmsToast(`Cuadrilla ${cuadrilla} (${contratista}) asignada a OT ${ot}.`, 'success');
       const idx = ONMS_DATOS.findIndex(d => d.ot === ot);
       if (idx !== -1) {
           ONMS_DATOS[idx].contratista  = contratista;
           ONMS_DATOS[idx].cuadrilla    = cuadrilla;
           ONMS_DATOS[idx].etapa        = 'Desplazamiento';
           ONMS_DATOS[idx].ultAvance    = onmsHoraActual();
           ONMS_DATOS[idx].minSinAvance = 0;
       }
       onmsFiltrar();
   }
   
   function onmsGuardarConfirmacion() {
       const ot         = document.getElementById('confirmarOtId').value;
       const comentario = document.getElementById('confirmarComentario').value.trim();
       if (!comentario) { onmsToast('Ingrese un comentario de cierre.', 'warning'); return; }
   
       onmsCerrarModal('onmsModalConfirmar');
       onmsToast(`OT ${ot} cerrada exitosamente.`, 'success');
       const idx = ONMS_DATOS.findIndex(d => d.ot === ot);
       if (idx !== -1) ONMS_DATOS.splice(idx, 1);
       onmsFiltrar();
       onmsActualizarKpis(ONMS_DATOS);
   }
   
   /* -----------------------------------------------
      REFRESH / COUNTDOWN
      ----------------------------------------------- */
   let onmsCountdownInterval = null;
   let onmsCountdownSeg      = 60;
   
   function onmsIniciarCountdown(segundos) {
       onmsCountdownSeg = segundos;
       clearInterval(onmsCountdownInterval);
       onmsCountdownInterval = setInterval(() => {
           onmsCountdownSeg--;
           const el = document.getElementById('onmsCountdown');
           if (el) el.textContent = onmsCountdownSeg;
           if (onmsCountdownSeg <= 0) onmsRefrescar();
       }, 1000);
   }
   
   function onmsRefrescar() {
       onmsActualizarTimestamp();
       onmsIniciarCountdown(60);
       onmsCargarDatos();
   }
   
   function onmsActualizarTimestamp() {
       const el = document.getElementById('onmsUltimaAct');
       if (el) el.textContent = new Date().toLocaleTimeString('es-CO');
   }
   
   /* -----------------------------------------------
      TOAST
      ----------------------------------------------- */
   let onmsToastTimer = null;
   function onmsToast(msg, tipo = 'info') {
       const el = document.getElementById('onmsToast');
       if (!el) return;
       el.textContent = msg; el.className = `onms-toast ${tipo}`; el.style.display = 'block';
       clearTimeout(onmsToastTimer);
       onmsToastTimer = setTimeout(() => { el.style.display = 'none'; }, 3500);
   }
   
   /* -----------------------------------------------
      UTILIDADES
      ----------------------------------------------- */
   function onmsHoraActual() {
       const n = new Date(), p = v => String(v).padStart(2,'0');
       return `${p(n.getDate())}/${p(n.getMonth()+1)} ${p(n.getHours())}:${p(n.getMinutes())}:${p(n.getSeconds())}`;
   }
   
   console.log('✅ ONMS — Monitoreo Cortes FO inicializado');