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
   
   /* -----------------------------------------------
      INFERENCIA DE ETAPA POR TÍTULO DE AVANCE
      Normaliza el título a minúsculas y aplica keywords.
      Retorna la etapa inferida o null si no hay coincidencia.
      ----------------------------------------------- */
   const ONMS_ETAPA_RULES = [
       { etapa: 'Desplazamiento',      test: t => /desplazamiento|v[ií]a/.test(t) },
       { etapa: 'En Sitio',            test: t => /en sitio|\bsitio\b|validando ingreso|\bingreso\b/.test(t) },
       { etapa: 'Hallazgo',            test: t => /hallazgo/.test(t) },
       { etapa: 'Diagnóstico',         test: t => /pruebas|diagn[oó]stico/.test(t) },
       { etapa: 'Búsqueda',            test: t => /buscando|b[uú]squeda/.test(t) },
       { etapa: 'Ejecución/Reparación',test: t => /ejecuci[oó]n|reparaci[oó]n/.test(t) },
       { etapa: 'Empalmería',          test: t => /empalme|empalmer[ií]a|tendido|fusi[oó]n/.test(t) },
       { etapa: 'Medida',              test: t => /\bmedida\b/.test(t) },
   ];

   function onmsInferirEtapa(titulo) {
       if (!titulo) return null;
       const t = titulo.toLowerCase();
       for (const rule of ONMS_ETAPA_RULES) {
           if (rule.test(t)) return rule.etapa;
       }
       return null;
   }

   const DAR_SOLUCION_REGEX   = /dar soluci[oó]n al incidente/i;
   const SOLUCION_TITULO_REGEX = /soluci[oó]n/i;

   const OPERADORES_CORTE_ASIGNADO = /claro|une|ufinet|azteca/i;

   function onmsNormalizarFila(d) {
       if (DAR_SOLUCION_REGEX.test(d.ultAvanceComentario || '') ||
           SOLUCION_TITULO_REGEX.test(d.ultAvanceTitulo   || '')) {
           d._excluir = true;
           return d;
       }
       const etapaInferida = onmsInferirEtapa(d.ultAvanceTitulo);
       d.etapa = etapaInferida || 'Por Asignar';

       // Si quedó en Por Asignar: promover a Corte Asignado si tiene PDR activa o si el operador FO es externo
       if (d.etapa === 'Por Asignar') {
           if (PDR_REGEX.test(d.ultAvanceTitulo || '') ||
               OPERADORES_CORTE_ASIGNADO.test(d.operadorFo || '')) {
               d.etapa = 'Corte Asignado';
           }
       }
       return d;
   }

   async function onmsCargarDatos() {
       onmsMostrarCargando(true);
       try {
           const resp = await fetch('/api/onms/incidentes');
           if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
           const json = await resp.json();
           if (!json.ok) throw new Error(json.error || 'Error desconocido');
   
           ONMS_DATOS.length = 0;
           json.data.forEach(d => {
               const fila = onmsNormalizarFila(d);
               if (!fila._excluir) ONMS_DATOS.push(fila);
           });
           onmsDatosActivos = [...ONMS_DATOS];

           onmsPoblarFiltrosDinamicos();
           onmsRenderTabla(onmsDatosActivos);
           onmsActualizarKpis(onmsDatosActivos);
           onmsRegistrarHistorial(ONMS_DATOS);
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
           <td colspan="16" style="text-align:center;padding:32px;color:#9ca3af;">
               <ion-icon name="sync-outline" style="font-size:20px;animation:spin 1s linear infinite;vertical-align:middle;margin-right:8px;"></ion-icon>
               Cargando incidentes...
           </td></tr>`;
   }
   
   /* -----------------------------------------------
      PARADA DE RELOJ (PDR)
      Detecta estado por keywords en titulo del ultimo avance.
      Estados: 'en_pdr' | 'por_aprobar' | 'sin_parada'
      ----------------------------------------------- */
   const PDR_REGEX = /\bPDR\b|\bPR\b|parada|reloj|espera ingreso|vulnerabilidad|visita fallida|compra/i;

   function onmsEstadoPDR(fila) {
       if (fila.pdrEstado === 'por_aprobar') return 'por_aprobar';
       if (fila.pdrEstado === 'sin_parada')  return 'sin_parada';
       return PDR_REGEX.test(fila.ultAvanceTitulo || '') ? 'en_pdr' : 'sin_parada';
   }

   function onmsBadgePDR(fila) {
       const estado = onmsEstadoPDR(fila);
       if (estado === 'en_pdr') {
           return `<span class="onms-badge onms-badge-pdr-activa"><span class="onms-pdr-dot"></span>En parada de reloj</span>`;
       }
       if (estado === 'por_aprobar') {
           return `<span class="onms-badge onms-badge-pdr-aprobar"><ion-icon name="hourglass-outline" style="font-size:10px;vertical-align:middle;margin-right:2px;"></ion-icon>Por aprobar</span>`;
       }
       return `<span class="onms-badge onms-badge-pdr-sin">Sin parada</span>`;
   }

   /* -----------------------------------------------
      RENDER TABLA
      Columnas: OT | Afectacion | Nodo A | Nodo B | Municipio | Inicio |
                Estado/Etapa | Parada reloj | Tipo tramo | Operador FO |
                EECC | Cuadrilla | Ult. avance | T. sin avance | Acciones -> 15
      ----------------------------------------------- */
   function onmsRenderTabla(datos) {
       const tbody          = document.getElementById('onmsTbody');
       const badgeContador  = document.getElementById('badgeContadorTabla');
       const registrosLabel = document.getElementById('onmsRegistrosLabel');

       if (badgeContador)  badgeContador.textContent  = datos.length;
       if (registrosLabel) registrosLabel.textContent = `${datos.length} registros`;

       if (!datos.length) {
           tbody.innerHTML = `<tr class="onms-empty-row"><td colspan="15">No hay incidentes que coincidan con los filtros aplicados.</td></tr>`;
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
               <td style="font-size:11px;">${fila.nodoA}<span class="onms-nodo-sep">&#x2192;</span></td>
               <td style="font-size:11px;">${fila.nodoB}</td>
               <td style="font-size:11px;">${fila.municipio || '&#x2014;'}</td>
               <td style="font-size:11px;color:#6b7280;">${fila.inicio}</td>
               <td>${onmsBadgeEtapa(fila.etapa)}</td>
               <td>${onmsBadgePDR(fila)}</td>
               <td>${tipoTramoHTML}</td>
               <td>${operadorHTML}</td>
               <td>${eeccHTML}</td>
               <td>${cuadrillaHTML}</td>
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
           'Corte Asignado':      'onms-badge-asignado',
           'Desplazamiento':      'onms-badge-desp',
           'En Sitio':            'onms-badge-ensitio',
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
       const pct        = Math.min(100, Math.round((min / umbral) * 100));
       const restantes  = Math.max(0, umbral - min);
       const restoTexto = restantes === 0
           ? 'Límite superado'
           : restantes === 1 ? '1 min restante' : `${restantes} min restantes`;
       const umbralTexto = afectacion === 'SI'
           ? 'Límite: 30 min (afecta servicio)'
           : 'Límite: 60 min (sin afectación)';

       let nivel;
       if (min >= umbral)          nivel = 'crit';
       else if (min >= umbralWarn) nivel = 'warn';
       else                        nivel = 'ok';

       const alertaDot = nivel === 'crit'
           ? `<span class="onms-alerta-dot">!</span>` : '';

       return `<div class="onms-tiempo-wrap" title="${umbralTexto} · ${restoTexto}">
           <span class="onms-tiempo ${nivel}">${alertaDot}${texto}</span>
           <div class="onms-progreso-bar">
               <div class="onms-progreso-fill ${nivel}" style="width:${pct}%"></div>
           </div>
       </div>`;
   }
   
   function onmsAccionHTML(fila) {
       const estadoPDR = onmsEstadoPDR(fila);
       const btnFinPR  = estadoPDR === 'en_pdr'
           ? `<button class="btn-accion-tabla fin-pr" onclick="onmsAbrirFinPR('${fila.ot}')">
               <ion-icon name="timer-outline"></ion-icon> Fin PR</button>`
           : '';

       let btnPrincipal;
       if (fila.etapa === 'Por Asignar') {
           btnPrincipal = `<button class="btn-accion-tabla asignar" onclick="onmsAbrirAsignar('${fila.ot}')">
               <ion-icon name="person-add-outline"></ion-icon> Asignar</button>`;
       } else if (fila.etapa === 'Validación') {
           btnPrincipal = `<button class="btn-accion-tabla confirmar" onclick="onmsAbrirConfirmar('${fila.ot}')">
               <ion-icon name="checkmark-circle-outline"></ion-icon> Confirmar</button>`;
       } else {
           btnPrincipal = `<button class="btn-accion-tabla" onclick="onmsAbrirAvance('${fila.ot}')">
               <ion-icon name="create-outline"></ion-icon> Avance</button>`;
       }

       return btnFinPR
           ? `<div class="onms-acciones-grupo">${btnFinPR}${btnPrincipal}</div>`
           : btnPrincipal;
   }
   
   /* -----------------------------------------------
      KPIs
      ----------------------------------------------- */
   const ETAPAS_EN_ATENCION = [
       'Corte Asignado','Desplazamiento','En Sitio','Medida','Búsqueda','Hallazgo',
       'Diagnóstico','Ejecución/Reparación','Empalmería'
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
       set('kpiPDR',       datos.filter(d => onmsEstadoPDR(d) === 'en_pdr').length);
   
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
       const estado      = document.getElementById('filtroEstado').value;
       const afecta      = document.getElementById('filtroAfectacion').value;
       const tipoTramo   = document.getElementById('filtroTipoTramo') ? document.getElementById('filtroTipoTramo').value : '';
       const operadorFo  = document.getElementById('filtroOperadorFo').value;
       const eecc        = document.getElementById('filtroEecc').value;
       const otTexto     = (document.getElementById('filtroOt').value || '').trim().toLowerCase();

       const filtrado = ONMS_DATOS.filter(d =>
           (!estado     || d.etapa      === estado)                              &&
           (!afecta     || d.afectacion === afecta)                              &&
           (!tipoTramo  || d.tipoTramo  === tipoTramo)                           &&
           (!operadorFo || (d.operadorFo || '') === operadorFo)                  &&
           (!eecc       || (d.eecc || '') === eecc)                              &&
           (!otTexto    || String(d.ot).toLowerCase().includes(otTexto))
       );
       onmsDatosActivos = filtrado;
       onmsRenderTabla(filtrado);
   }

   function onmsLimpiarFiltros() {
       ['filtroEstado','filtroAfectacion','filtroTipoTramo','filtroOperadorFo','filtroEecc'].forEach(id => {
           const el = document.getElementById(id); if (el) el.value = '';
       });
       const otEl = document.getElementById('filtroOt');
       if (otEl) otEl.value = '';
       onmsDatosActivos = [...ONMS_DATOS];
       onmsRenderTabla(onmsDatosActivos);
   }

   function onmsPoblarFiltrosDinamicos() {
       const operadores = [...new Set(ONMS_DATOS.map(d => d.operadorFo).filter(Boolean))].sort();
       const eeccs      = [...new Set(ONMS_DATOS.map(d => d.eecc).filter(Boolean))].sort();

       const selOp   = document.getElementById('filtroOperadorFo');
       const selEecc = document.getElementById('filtroEecc');

       if (selOp) {
           const valActual = selOp.value;
           selOp.innerHTML = '<option value="">Todo operador FO</option>' +
               operadores.map(o => `<option value="${o}">${o}</option>`).join('');
           selOp.value = valActual;
       }
       if (selEecc) {
           const valActual = selEecc.value;
           selEecc.innerHTML = '<option value="">Todo EECC</option>' +
               eeccs.map(e => `<option value="${e}">${e}</option>`).join('');
           selEecc.value = valActual;
       }
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

   function onmsAbrirFinPR(ot) {
       document.getElementById('finPrOtId').value          = ot;
       document.getElementById('finPrOtLabel').textContent = ot;
       document.getElementById('finPrComentario').value    = '';
       document.getElementById('onmsModalFinPR').style.display = 'flex';
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
       ['onmsModalAvance','onmsModalAsignar','onmsModalConfirmar','onmsModalFinPR','onmsPopoverAvance'].forEach(id => {
           const modal = document.getElementById(id);
           if (modal && e.target === modal) modal.style.display = 'none';
       });
   });
   
   document.addEventListener('keydown', e => {
       if (e.key === 'Escape') {
           ['onmsModalAvance','onmsModalAsignar','onmsModalConfirmar','onmsModalFinPR','onmsPopoverAvance'].forEach(id => {
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
       const tituloEl   = document.getElementById('avanceTitulo');
       const titulo     = tituloEl ? tituloEl.value.trim() : '';
       if (!etapa || !comentario) { onmsToast('Complete todos los campos requeridos.', 'warning'); return; }

       const etapaFinal = (titulo && onmsInferirEtapa(titulo)) || etapa;

       onmsCerrarModal('onmsModalAvance');
       onmsToast(`Avance registrado para OT ${ot}.`, 'success');
       const idx = ONMS_DATOS.findIndex(d => d.ot === ot);
       if (idx !== -1) {
           ONMS_DATOS[idx].etapa                = etapaFinal;
           ONMS_DATOS[idx].minSinAvance         = 0;
           ONMS_DATOS[idx].ultAvance            = onmsHoraActual();
           ONMS_DATOS[idx].ultAvanceTitulo      = titulo || etapaFinal;
           ONMS_DATOS[idx].ultAvanceComentario  = comentario;
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

   function onmsGuardarFinPR() {
       const ot         = document.getElementById('finPrOtId').value;
       const comentario = document.getElementById('finPrComentario').value.trim();
       if (!comentario) { onmsToast('Ingrese un comentario de reactivación.', 'warning'); return; }

       onmsCerrarModal('onmsModalFinPR');
       const idx = ONMS_DATOS.findIndex(d => d.ot === ot);
       if (idx !== -1) {
           ONMS_DATOS[idx].pdrEstado          = 'por_aprobar';
           ONMS_DATOS[idx].ultAvance          = onmsHoraActual();
           ONMS_DATOS[idx].ultAvanceTitulo    = 'Fin Parada de Reloj';
           ONMS_DATOS[idx].ultAvanceComentario = comentario;
           ONMS_DATOS[idx].minSinAvance        = 0;
       }
       onmsToast(`Fin PR registrado para OT ${ot}. Se reactivan labores.`, 'success');
       onmsFiltrar();
       onmsActualizarKpis(ONMS_DATOS);
   }
   
   /* -----------------------------------------------
      REFRESH / COUNTDOWN
      ----------------------------------------------- */
   let onmsCountdownInterval = null;
   let onmsCountdownSeg      = 60;
   let onmsPausado           = false;

   function onmsIniciarCountdown(segundos) {
       onmsCountdownSeg = segundos;
       clearInterval(onmsCountdownInterval);
       if (onmsPausado) return;
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

   function onmsTogglePausa() {
       onmsPausado = !onmsPausado;
       const btn      = document.getElementById('btnPausaRefresh');
       const icon     = document.getElementById('iconPausaRefresh');
       const badge    = document.querySelector('.badge-live-onms');
       const countdown = document.getElementById('onmsCountdown');

       if (onmsPausado) {
           clearInterval(onmsCountdownInterval);
           if (icon)     icon.setAttribute('name', 'play-outline');
           if (btn)      btn.classList.add('pausado');
           if (btn)      btn.title = 'Reanudar actualización automática';
           if (badge)    badge.classList.add('pausado');
           if (countdown) countdown.textContent = '—';
       } else {
           if (icon)     icon.setAttribute('name', 'pause-outline');
           if (btn)      btn.classList.remove('pausado');
           if (btn)      btn.title = 'Pausar actualización automática';
           if (badge)    badge.classList.remove('pausado');
           onmsIniciarCountdown(60);
       }
   }
   
   function onmsActualizarTimestamp() {
       const el = document.getElementById('onmsUltimaAct');
       if (el) el.textContent = new Date().toLocaleTimeString('es-CO');
   }
   
   /* -----------------------------------------------
      HISTORIAL DE OTs
      Registra en PostgreSQL las OTs visibles en el tablero.
      Usa INSERT ... ON CONFLICT DO NOTHING → una OT por día.
      Se ejecuta silenciosamente; los errores solo se loguean.
      ----------------------------------------------- */
   async function onmsRegistrarHistorial(datos) {
       if (!datos || datos.length === 0) return;
       try {
           const payload = datos.map(d => ({
               ot:         d.ot,
               afectacion: d.afectacion,
               nodoA:      d.nodoA      || '',
               nodoB:      d.nodoB      || '',
               tipoTramo:  d.tipoTramo  || '',
               operadorFo: d.operadorFo || '',
               eecc:       d.eecc       || '',
               cuadrilla:  d.cuadrilla  || '',
           }));
           await fetch('/api/onms/historial/registrar', {
               method:  'POST',
               headers: { 'Content-Type': 'application/json' },
               body:    JSON.stringify({ ots: payload }),
           });
       } catch (err) {
           console.warn('[ONMS historial] No se pudo registrar:', err);
       }
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