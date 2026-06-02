"""
onms/routes_crear_ot.py
-----------------------
Endpoints Flask para el modulo de creacion de OTs RBHFO.

Expone:
    onms_crear_ot_get  -> GET  /onms/crear_ot  (formulario)
    onms_crear_ot_post -> POST /onms/crear_ot  (procesa y crea OT en Maximo)

Como integrar en app.py:

    from onms.routes_crear_ot import onms_crear_ot_get, onms_crear_ot_post
    app.route('/onms/crear_ot', methods=['GET'])(onms_crear_ot_get)
    app.route('/onms/crear_ot', methods=['POST'])(onms_crear_ot_post)

NOTA: esta vista es una DEMO funcional. El frontend definitivo lo integrará
el equipo de UI dentro de templates/onms.html. No optimizar ni estilizar
nada aquí.
"""

import json
import logging
from flask import render_template, request, session

from middleware_permisos import login_requerido, permiso_requerido

from onms import catalogos
from onms import armar_ot
from onms import maximo_api


# Constantes hardcoded para la demo (no se preguntan en el formulario).
# Si el equipo de UI necesita hacerlos editables, los agrega en el form
# y los pasa por request.form en el POST.
LEAD_FIJO    = "LGMELENDEZHE"
IMPACTO_FIJO = "1"


# ══════════════════════════════════════════════════════════════════
# GET /onms/crear_ot
# ══════════════════════════════════════════════════════════════════

@login_requerido
@permiso_requerido('onms')
def onms_crear_ot_get():
    """
    Renderiza el formulario vacio para crear una OT RBHFO.
    """
    menu_permisos  = session.get('menu_permisos', {})
    perfil_usuario = session.get('PERFIL', '')
    usuario        = session.get('USUARIO', '')

    logging.info(f"[onms.crear_ot GET] usuario={usuario}")

    return render_template(
        'crear_ot.html',
        menu_permisos=menu_permisos,
        perfil_usuario=perfil_usuario,
        usuario=usuario,
        form_data=None,
        resultado=None,
    )


# ══════════════════════════════════════════════════════════════════
# POST /onms/crear_ot
# ══════════════════════════════════════════════════════════════════

@login_requerido
@permiso_requerido('onms')
def onms_crear_ot_post():
    """
    Procesa el formulario. Resuelve enlace + EECC + lider PI, arma el
    payload, llama a Maximo (crear + actualizar specs) y renderiza el
    mismo template con el resultado.
    """
    menu_permisos  = session.get('menu_permisos', {})
    perfil_usuario = session.get('PERFIL', '')
    usuario        = session.get('USUARIO', '')

    # 1. Recoger inputs del form
    form_data = {
        "punta_a":             request.form.get("punta_a", "").strip(),
        "punta_b":             request.form.get("punta_b", "").strip(),
        "lado":                request.form.get("lado", "").strip(),
        "persona_que_reporta": request.form.get("persona_que_reporta", "").strip(),
        "area_que_reporta_fo": request.form.get("area_que_reporta_fo", "").strip(),
    }

    # Distingue cual de los dos botones se uso. Default 'solo_ot' para
    # compatibilidad si llegara un POST sin el campo (ej. tests viejos).
    accion = request.form.get("accion", "solo_ot").strip()

    # Si el usuario pidio el flujo incidente+OT, delegamos al handler
    # especifico. Comparte validaciones y resolucion de catalogos via
    # _resolver_contexto_creacion(), pero el resto del flujo es distinto.
    if accion == "incidente_ot":
        return _flujo_incidente_ot(
            menu_permisos, perfil_usuario, usuario, form_data
        )

    logging.info(
        f"[crear_ot][INICIO] usuario={usuario} "
        f"puntas={form_data['punta_a']} <-> {form_data['punta_b']} "
        f"lado={form_data['lado']} "
        f"persona={form_data['persona_que_reporta']} "
        f"area={form_data['area_que_reporta_fo']}"
    )

    # 2. Validacion minima
    for campo, valor in form_data.items():
        if not valor:
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=f"El campo '{campo}' es obligatorio.",
            )

    if form_data["lado"] not in ("origen", "destino"):
        return _render_error(
            menu_permisos, perfil_usuario, usuario, form_data,
            mensaje=f"Lado invalido: {form_data['lado']!r}. Debe ser 'origen' o 'destino'.",
        )

    try:
        # 3. Resolver enlace en inventario
        enlace = catalogos.resolver_enlace(form_data["punta_a"], form_data["punta_b"])
        if not enlace:
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=(f"No se encontro enlace para puntas "
                         f"{form_data['punta_a']!r} / {form_data['punta_b']!r} "
                         f"en inventario_anillo_bh_fusion."),
            )

        # 4. Extraer datos del lado de despacho
        datos_despacho = armar_ot.extraer_datos_despacho(enlace, form_data["lado"])
        logging.info(
            f"[crear_ot][ENLACE] device_origen={enlace['device_origen']} "
            f"device_destino={enlace['device_destino']} "
            f"cinum_despacho={datos_despacho['cinum_despacho']} "
            f"location_enlace={datos_despacho['location_despacho']} "
            f"mun={datos_despacho['mun_origen_anillo']}-{datos_despacho['mun_destino_anillo']}"
        )

        # 5. Resolver EECC + coordinador de red
        coord_fibra = catalogos.resolver_coord_fibra(
            datos_despacho["depto_despacho"],
            datos_despacho["municipio_despacho"],
        )
        if not coord_fibra:
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=(f"No hay match en cat_coord_fibra para "
                         f"depto={datos_despacho['depto_despacho']!r} "
                         f"muni={datos_despacho['municipio_despacho']!r}."),
            )

        # 6. Resolver lider de zona PI
        coord_pi = catalogos.resolver_coord_pi(datos_despacho["depto_despacho"])
        if not coord_pi:
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=(f"No hay lider PI en cat_coord_pi para "
                         f"depto={datos_despacho['depto_despacho']!r}."),
            )

        # 7. Pre-capturar el SIT_LOCATION del CI desde inventario_hlx.
        #    Se hace ANTES de crear la OT para tenerlo listo por si
        #    Maximo rechaza el cinum original y hay que reintentar con
        #    el CI generico (que no trae ubicacion propia).
        sit_location_respaldo = catalogos.resolver_sit_location(
            datos_despacho["cinum_despacho"]
        )
        if sit_location_respaldo:
            logging.info(
                f"[crear_ot][RESPALDO_HLX] sit_location encontrado en inventario_hlx: "
                f"{sit_location_respaldo} (preventivo, por si Maximo rechaza el CI)"
            )
        else:
            logging.info(
                f"[crear_ot][RESPALDO_HLX] NO hay sit_location en inventario_hlx "
                f"para cinum={datos_despacho['cinum_despacho']} "
                f"(si Maximo rechaza el CI, no podra crearse la OT)"
            )

        # 8. Armar payload top-level y crear OT con el CI original
        payload_top = armar_ot.armar_payload_toplevel(
            datos_despacho=datos_despacho,
            reported_by=usuario,
            lead=LEAD_FIJO,
            impacto=IMPACTO_FIJO,
        )
        logging.info(
            f"[crear_ot][MAXIMO_INTENTO_1] enviando cinum={payload_top['cinum']} "
            f"location={payload_top['location']}"
        )
        res_crear = maximo_api.crear_ot(payload_top)

        # Estado del flujo del CI: 'ORIGINAL' o 'GENERICO'. Sirve para el
        # log RESUMEN_FINAL y para saber si hay que mostrar aviso al usuario.
        cinum_final     = payload_top["cinum"]
        location_final  = payload_top["location"]
        flujo_cinum     = "ORIGINAL"
        aviso_generico  = None  # mensaje para el usuario; None si fue ORIGINAL

        if not res_crear.get("success"):
            # Caso especial: Maximo no reconoce el CI (cinum) original.
            if _es_error_cinum_invalido(res_crear):
                logging.warning(
                    f"[crear_ot][MAXIMO_INTENTO_1_RECHAZO] cinum={payload_top['cinum']} "
                    f"rechazado por Maximo (BMXAA6199E): {res_crear.get('message')}"
                )

                # Sin SIT_LOCATION de respaldo no podemos reintentar:
                # el CI generico no trae ubicacion. Error y no se crea.
                if not sit_location_respaldo:
                    logging.error(
                        f"[crear_ot][ERROR_SIN_RESPALDO] cinum={payload_top['cinum']} "
                        f"rechazado y SIN sit_location de respaldo en inventario_hlx. "
                        f"Se aborta sin crear OT."
                    )
                    mensaje = _construir_mensaje_sin_respaldo(
                        enlace, form_data["lado"]
                    )
                    return _render_error(
                        menu_permisos, perfil_usuario, usuario, form_data,
                        mensaje=mensaje,
                    )

                # Reintento automatico con CI generico + SIT_LOCATION.
                cinum_rechazado = datos_despacho["cinum_despacho"]
                payload_generico = armar_ot.adaptar_payload_a_generico(
                    payload_top, sit_location_respaldo
                )
                logging.warning(
                    f"[crear_ot][FALLBACK_GENERICO] activando: "
                    f"cinum {cinum_rechazado} -> {armar_ot.CINUM_GENERICO}, "
                    f"location {payload_top['location']} -> {sit_location_respaldo} "
                    f"(de inventario_hlx)"
                )
                logging.info(
                    f"[crear_ot][MAXIMO_INTENTO_2] enviando cinum={payload_generico['cinum']} "
                    f"location={payload_generico['location']}"
                )
                res_crear = maximo_api.crear_ot(payload_generico)

                if not res_crear.get("success"):
                    # El reintento con generico tambien fallo: error tecnico.
                    logging.error(
                        f"[crear_ot][MAXIMO_INTENTO_2_FALLO] el reintento con CI "
                        f"generico tambien fallo: {res_crear.get('message')}"
                    )
                    return _render_error(
                        menu_permisos, perfil_usuario, usuario, form_data,
                        mensaje=(f"El CI {cinum_rechazado} fue rechazado y el "
                                 f"reintento con CI generico tambien fallo: "
                                 f"{res_crear.get('message')}"),
                        detalle=json.dumps(res_crear, indent=2, ensure_ascii=False),
                    )

                # Reintento exitoso. Actualizamos el estado del flujo.
                logging.info(
                    f"[crear_ot][MAXIMO_INTENTO_2_OK] OT creada con generico: "
                    f"wonum={res_crear.get('ot')}"
                )
                cinum_final    = payload_generico["cinum"]
                location_final = payload_generico["location"]
                flujo_cinum    = "GENERICO"
                aviso_generico = (
                    f"El CI original {cinum_rechazado} no esta registrado en "
                    f"Maximo. La OT se creo con el CI generico "
                    f"{armar_ot.CINUM_GENERICO} y la ubicacion "
                    f"{sit_location_respaldo} (tomada de inventario_hlx)."
                )
            else:
                # Cualquier otro error de Maximo: mostramos el detalle tecnico.
                logging.error(
                    f"[crear_ot][MAXIMO_INTENTO_1_FALLO] error no relacionado a CI: "
                    f"{res_crear.get('message')}"
                )
                return _render_error(
                    menu_permisos, perfil_usuario, usuario, form_data,
                    mensaje=f"Maximo rechazo la creacion de la OT: {res_crear.get('message')}",
                    detalle=json.dumps(res_crear, indent=2, ensure_ascii=False),
                )
        else:
            logging.info(
                f"[crear_ot][MAXIMO_INTENTO_1_OK] OT creada con CI original: "
                f"wonum={res_crear.get('ot')}"
            )

        wonum = res_crear.get("ot")
        href  = res_crear.get("href")

        if not href:
            # Maximo creo la OT pero no devolvio Location, hay que resolverla.
            href = maximo_api.obtener_href(wonum)
            if not href:
                return _render_error(
                    menu_permisos, perfil_usuario, usuario, form_data,
                    mensaje=(f"OT {wonum} creada pero no se pudo resolver href "
                             f"para cargar las specs. Las specs deben cargarse manualmente."),
                )

        # 9. Armar payload de specs y actualizar
        payload_specs = armar_ot.armar_payload_specs(
            eecc_cuadrilla_fo    = coord_fibra["eecc_cuadrilla_fo"],
            coordinador_red_fo   = coord_fibra["coordinador_red_fo"],
            lider_de_zona_fo     = coord_pi["lider_de_zona_fo"],
            responsable_nivel3   = LEAD_FIJO,
            persona_que_reporta  = form_data["persona_que_reporta"],
            area_que_reporta_fo  = form_data["area_que_reporta_fo"],
        )
        # Log DEBUG con los valores que se cargan en specs (para auditoria
        # detallada solo cuando se activa DEBUG; no inunda INFO).
        logging.debug(
            f"[crear_ot][SPECS_DATOS] eecc={coord_fibra['eecc_cuadrilla_fo']} "
            f"coord_red={coord_fibra['coordinador_red_fo']} "
            f"lider_zona={coord_pi['lider_de_zona_fo']} "
            f"responsable_n3={LEAD_FIJO} "
            f"persona_reporta={form_data['persona_que_reporta']} "
            f"area={form_data['area_que_reporta_fo']}"
        )
        res_specs = maximo_api.actualizar_ot(href, payload_specs)

        if not res_specs.get("success"):
            logging.error(
                f"[crear_ot][SPECS_FALLO] wonum={wonum} no se pudieron cargar "
                f"los specs: {res_specs.get('message')}"
            )
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=(f"OT {wonum} creada, pero fallo la carga de specs: "
                         f"{res_specs.get('message')}"),
                detalle=json.dumps(res_specs, indent=2, ensure_ascii=False),
            )

        logging.info(
            f"[crear_ot][SPECS_OK] {len(payload_specs['spi:workorderspec'])} "
            f"specs cargados en wonum={wonum}"
        )

        # 10. Exito. Si se uso el CI generico, aviso_generico lleva el
        #     mensaje explicativo; si fue el CI normal, queda None.
        if flujo_cinum == "GENERICO":
            logging.info(
                f"[crear_ot][RESUMEN_FINAL] wonum={wonum} "
                f"cinum_final={cinum_final} (GENERICO, original "
                f"{datos_despacho['cinum_despacho']} rechazado) "
                f"location={location_final} "
                f"specs={len(payload_specs['spi:workorderspec'])}"
            )
        else:
            logging.info(
                f"[crear_ot][RESUMEN_FINAL] wonum={wonum} "
                f"cinum_final={cinum_final} (ORIGINAL) "
                f"location={location_final} "
                f"specs={len(payload_specs['spi:workorderspec'])}"
            )

        resultado = {
            "ok":           True,
            "wonum":        wonum,
            "description":  payload_top["description"],
            "specs_count":  len(payload_specs["spi:workorderspec"]),
            "aviso":        aviso_generico,
            "detalle":      None,
        }
        return render_template(
            'crear_ot.html',
            menu_permisos=menu_permisos,
            perfil_usuario=perfil_usuario,
            usuario=usuario,
            form_data=None,        # limpiamos el form en el exito
            resultado=resultado,
        )

    except Exception as e:
        logging.exception("[onms.crear_ot POST] excepcion no controlada")
        return _render_error(
            menu_permisos, perfil_usuario, usuario, form_data,
            mensaje=f"Excepcion no controlada: {e}",
        )


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════
# FLUJO INCIDENTE + OT (boton "Crear incidente + OT" del frontend)
# ══════════════════════════════════════════════════════════════════
#
# Diferencia con el flujo "OT sola":
#   - Antes de crear nada, hace POST a RESTINCIDENT (con fallback al CI
#     generico si Maximo rechaza). Maximo genera incidente + OT en una
#     sola operacion. La OT nace con classstructureid=1887, ownergroup=
#     O_GESRED (heredados del incidente).
#   - Como la OT nace "pelada" en lo que respecta a fibra, hay que
#     actualizarla en 3 fases despues:
#       Fase A (estructural):  ownergroup -> O_GESFO, classstructureid
#                              -> 4213, woclass, worktype, status.
#       Fase B (dependiente):  lead, cinum, location, reportedby,
#                              description, impacto, schedstart, actstart.
#                              Necesita que A ya este aplicado.
#       Fase C (specs):        los 18 specs de fibra. Necesita que el
#                              classstructureid ya sea 4213.
#   - El cinum de Fase B es el mismo del incidente (rechazado -> generico),
#     asi que el aviso_generico se mantiene si aplico el fallback.

def _flujo_incidente_ot(menu_permisos, perfil_usuario, usuario, form_data):
    """
    Orquesta el flujo "Crear incidente + OT" disparado desde el frontend.
    Reusa las mismas validaciones, resolucion de enlace, catalogos y
    pre-captura de SIT_LOCATION que el flujo OT sola.
    """
    from datetime import datetime

    logging.info(
        f"[crear_inc_ot][INICIO] usuario={usuario} "
        f"puntas={form_data['punta_a']} <-> {form_data['punta_b']} "
        f"lado={form_data['lado']} "
        f"persona={form_data['persona_que_reporta']} "
        f"area={form_data['area_que_reporta_fo']}"
    )

    # ── Validacion minima (espejo del flujo OT sola) ──────────────
    for campo, valor in form_data.items():
        if not valor:
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=f"El campo '{campo}' es obligatorio.",
            )
    if form_data["lado"] not in ("origen", "destino"):
        return _render_error(
            menu_permisos, perfil_usuario, usuario, form_data,
            mensaje=f"Lado invalido: {form_data['lado']!r}.",
        )

    try:
        # ── Resolver enlace ───────────────────────────────────────
        enlace = catalogos.resolver_enlace(form_data["punta_a"], form_data["punta_b"])
        if not enlace:
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=(f"No se encontro enlace para puntas "
                         f"{form_data['punta_a']!r} / {form_data['punta_b']!r}."),
            )

        datos_despacho = armar_ot.extraer_datos_despacho(enlace, form_data["lado"])
        logging.info(
            f"[crear_inc_ot][ENLACE] device_origen={enlace['device_origen']} "
            f"device_destino={enlace['device_destino']} "
            f"cinum_despacho={datos_despacho['cinum_despacho']} "
            f"location_enlace={datos_despacho['location_despacho']} "
            f"mun={datos_despacho['mun_origen_anillo']}-{datos_despacho['mun_destino_anillo']}"
        )

        # ── Catalogos para los specs (Fase C) ─────────────────────
        coord_fibra = catalogos.resolver_coord_fibra(
            datos_despacho["depto_despacho"],
            datos_despacho["municipio_despacho"],
        )
        if not coord_fibra:
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=(f"No hay match en cat_coord_fibra para "
                         f"depto={datos_despacho['depto_despacho']!r} "
                         f"muni={datos_despacho['municipio_despacho']!r}."),
            )
        coord_pi = catalogos.resolver_coord_pi(datos_despacho["depto_despacho"])
        if not coord_pi:
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=(f"No hay lider PI en cat_coord_pi para "
                         f"depto={datos_despacho['depto_despacho']!r}."),
            )

        # ── Pre-capturar SIT_LOCATION ─────────────────────────────
        sit_location_respaldo = catalogos.resolver_sit_location(
            datos_despacho["cinum_despacho"]
        )
        if sit_location_respaldo:
            logging.info(
                f"[crear_inc_ot][RESPALDO_HLX] sit_location encontrado: "
                f"{sit_location_respaldo} (preventivo)"
            )
        else:
            logging.info(
                f"[crear_inc_ot][RESPALDO_HLX] NO hay sit_location para "
                f"cinum={datos_despacho['cinum_despacho']}"
            )

        # ── Crear incidente ───────────────────────────────────────
        ahora_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S-05:00")
        payload_inc = armar_ot.armar_payload_incidente(datos_despacho, ahora_iso)
        logging.info(
            f"[crear_inc_ot][INCIDENTE_INTENTO_1] enviando "
            f"cinum={payload_inc['cinum']} "
            f"location={payload_inc['multiassetlocci']['location']}"
        )
        res_inc = maximo_api.crear_incidente_con_ot(payload_inc)

        cinum_final     = payload_inc["cinum"]
        location_final  = payload_inc["multiassetlocci"]["location"]
        flujo_cinum     = "ORIGINAL"
        aviso_generico  = None

        if not res_inc.get("success"):
            if _es_error_cinum_invalido(res_inc):
                logging.warning(
                    f"[crear_inc_ot][INCIDENTE_INTENTO_1_RECHAZO] "
                    f"cinum={payload_inc['cinum']} rechazado: {res_inc.get('message')}"
                )
                if not sit_location_respaldo:
                    logging.error(
                        f"[crear_inc_ot][ERROR_SIN_RESPALDO] cinum rechazado y "
                        f"sin sit_location en inventario_hlx. Aborto sin crear nada."
                    )
                    return _render_error(
                        menu_permisos, perfil_usuario, usuario, form_data,
                        mensaje=_construir_mensaje_sin_respaldo(enlace, form_data["lado"]),
                    )

                cinum_rechazado = payload_inc["cinum"]
                payload_inc_gen = armar_ot.adaptar_payload_incidente_a_generico(
                    payload_inc, sit_location_respaldo
                )
                logging.warning(
                    f"[crear_inc_ot][FALLBACK_GENERICO_INC] "
                    f"cinum {cinum_rechazado} -> {armar_ot.CINUM_GENERICO}, "
                    f"location -> {sit_location_respaldo}"
                )
                logging.info(
                    f"[crear_inc_ot][INCIDENTE_INTENTO_2] enviando "
                    f"cinum={payload_inc_gen['cinum']} "
                    f"location={payload_inc_gen['multiassetlocci']['location']}"
                )
                res_inc = maximo_api.crear_incidente_con_ot(payload_inc_gen)
                if not res_inc.get("success"):
                    logging.error(
                        f"[crear_inc_ot][INCIDENTE_INTENTO_2_FALLO] "
                        f"reintento con generico tambien fallo: {res_inc.get('message')}"
                    )
                    return _render_error(
                        menu_permisos, perfil_usuario, usuario, form_data,
                        mensaje=(f"El CI {cinum_rechazado} fue rechazado y el "
                                 f"reintento con CI generico tambien fallo: "
                                 f"{res_inc.get('message')}"),
                        detalle=json.dumps(res_inc, indent=2, ensure_ascii=False),
                    )
                logging.info(
                    f"[crear_inc_ot][INCIDENTE_INTENTO_2_OK] "
                    f"ticket={res_inc.get('ticket')} wonum={res_inc.get('wonum') or '(buscar)'}"
                )
                cinum_final    = payload_inc_gen["cinum"]
                location_final = payload_inc_gen["multiassetlocci"]["location"]
                flujo_cinum    = "GENERICO"
                aviso_generico = (
                    f"El CI original {cinum_rechazado} no esta registrado en "
                    f"Maximo. El incidente y la OT se crearon con el CI generico "
                    f"{armar_ot.CINUM_GENERICO} y la ubicacion "
                    f"{sit_location_respaldo} (tomada de inventario_hlx)."
                )
            else:
                logging.error(
                    f"[crear_inc_ot][INCIDENTE_INTENTO_1_FALLO] "
                    f"error no relacionado a CI: {res_inc.get('message')}"
                )
                return _render_error(
                    menu_permisos, perfil_usuario, usuario, form_data,
                    mensaje=f"Maximo rechazo la creacion del incidente: {res_inc.get('message')}",
                    detalle=json.dumps(res_inc, indent=2, ensure_ascii=False),
                )
        else:
            logging.info(
                f"[crear_inc_ot][INCIDENTE_INTENTO_1_OK] "
                f"ticket={res_inc.get('ticket')} wonum={res_inc.get('wonum') or '(buscar)'}"
            )

        ticket = res_inc.get("ticket")

        # ── Resolver wonum de la OT generada ──────────────────────
        # Maximo a veces lo trae en el response, a veces no. Si no,
        # lo buscamos en /relatedrecord.
        wonum = res_inc.get("wonum")
        if not wonum:
            logging.info(
                f"[crear_inc_ot][OT_GENERADA] wonum no vino en el response; "
                f"consultando relaciones del incidente {ticket}..."
            )
            wonum = maximo_api.obtener_wonum_de_incidente(ticket)
            if not wonum:
                logging.error(
                    f"[crear_inc_ot][OT_GENERADA] no se pudo obtener wonum "
                    f"del incidente {ticket}. Aborto antes de actualizar."
                )
                return _render_error(
                    menu_permisos, perfil_usuario, usuario, form_data,
                    mensaje=(f"Incidente {ticket} creado, pero no se pudo "
                             f"localizar la OT generada para actualizarla."),
                )
        logging.info(f"[crear_inc_ot][OT_GENERADA] wonum={wonum}")

        # ── Resolver href de la OT generada (para los 3 PATCH) ────
        href = maximo_api.obtener_href(wonum)
        if not href:
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=(f"OT {wonum} no se pudo resolver para actualizar."),
            )

        # ══════════════════════════════════════════════════════════
        # FASE A: campos estructurales
        # ══════════════════════════════════════════════════════════
        # Cambia ownergroup y classstructureid para que la Fase B
        # pueda validar lead contra el grupo correcto, y la Fase C
        # pueda aplicar specs de fibra.
        fase_a_payload = {
            "spi:ownergroup":       armar_ot.OWNERGROUP,
            "spi:classstructureid": armar_ot.CLASSSTRUCTUREID,
            "spi:woclass":          armar_ot.WOCLASS,
            "spi:worktype":         armar_ot.WORKTYPE,
            "spi:status":           armar_ot.STATUS_INICIAL,
        }
        logging.info(
            f"[crear_inc_ot][FASE_A] estructural: "
            f"ownergroup->{armar_ot.OWNERGROUP} "
            f"classstructureid->{armar_ot.CLASSSTRUCTUREID}"
        )
        r_a = maximo_api.actualizar_ot(href, fase_a_payload)
        if not r_a.get("success"):
            logging.error(f"[crear_inc_ot][FASE_A_FALLO] {r_a.get('message')}")
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=(f"OT {wonum} creada por el incidente {ticket}, pero "
                         f"fallo la Fase A (estructural): {r_a.get('message')}"),
                detalle=json.dumps(r_a, indent=2, ensure_ascii=False),
            )
        logging.info(f"[crear_inc_ot][FASE_A_OK] wonum={wonum}")

        # ══════════════════════════════════════════════════════════
        # FASE B: campos dependientes (lead, cinum, location, etc.)
        # ══════════════════════════════════════════════════════════
        # schedstart y actstart con hora actual.
        ahora_iso_b = datetime.now().strftime("%Y-%m-%dT%H:%M:%S-05:00")
        ts_legible  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fase_b_payload = {
            "spi:description":  armar_ot.armar_description(
                datos_despacho["mun_origen_anillo"],
                datos_despacho["mun_destino_anillo"],
            ),
            "spi:cinum":        cinum_final,
            "spi:location":     location_final,
            "spi:reportedby":   usuario,
            "spi:lead":         LEAD_FIJO,
            "spi:impacto":      IMPACTO_FIJO,
            "spi:schedstart":   ahora_iso_b,
            "spi:actstart":     ahora_iso_b,
        }
        logging.info(
            f"[crear_inc_ot][FASE_B] dependiente: "
            f"cinum={cinum_final} location={location_final} "
            f"lead={LEAD_FIJO} schedstart/actstart={ts_legible}"
        )
        r_b = maximo_api.actualizar_ot(href, fase_b_payload)
        if not r_b.get("success"):
            logging.error(f"[crear_inc_ot][FASE_B_FALLO] {r_b.get('message')}")
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=(f"OT {wonum} con Fase A aplicada, pero fallo la "
                         f"Fase B (dependiente): {r_b.get('message')}"),
                detalle=json.dumps(r_b, indent=2, ensure_ascii=False),
            )
        logging.info(f"[crear_inc_ot][FASE_B_OK] wonum={wonum}")

        # ══════════════════════════════════════════════════════════
        # FASE C: specs
        # ══════════════════════════════════════════════════════════
        payload_specs = armar_ot.armar_payload_specs(
            eecc_cuadrilla_fo    = coord_fibra["eecc_cuadrilla_fo"],
            coordinador_red_fo   = coord_fibra["coordinador_red_fo"],
            lider_de_zona_fo     = coord_pi["lider_de_zona_fo"],
            responsable_nivel3   = LEAD_FIJO,
            persona_que_reporta  = form_data["persona_que_reporta"],
            area_que_reporta_fo  = form_data["area_que_reporta_fo"],
        )
        logging.debug(
            f"[crear_inc_ot][SPECS_DATOS] eecc={coord_fibra['eecc_cuadrilla_fo']} "
            f"coord_red={coord_fibra['coordinador_red_fo']} "
            f"lider_zona={coord_pi['lider_de_zona_fo']} "
            f"responsable_n3={LEAD_FIJO} "
            f"persona_reporta={form_data['persona_que_reporta']} "
            f"area={form_data['area_que_reporta_fo']}"
        )
        logging.info(f"[crear_inc_ot][FASE_C] specs ({len(payload_specs['spi:workorderspec'])})")
        r_c = maximo_api.actualizar_ot(href, payload_specs)
        if not r_c.get("success"):
            logging.error(f"[crear_inc_ot][FASE_C_FALLO] {r_c.get('message')}")
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=(f"OT {wonum} con Fases A y B aplicadas, pero fallo "
                         f"la carga de specs: {r_c.get('message')}"),
                detalle=json.dumps(r_c, indent=2, ensure_ascii=False),
            )
        logging.info(
            f"[crear_inc_ot][SPECS_OK] {len(payload_specs['spi:workorderspec'])} "
            f"specs cargados en wonum={wonum}"
        )

        # ── Resumen final ─────────────────────────────────────────
        if flujo_cinum == "GENERICO":
            logging.info(
                f"[crear_inc_ot][RESUMEN_FINAL] ticket={ticket} wonum={wonum} "
                f"cinum_final={cinum_final} (GENERICO, original "
                f"{datos_despacho['cinum_despacho']} rechazado) "
                f"location={location_final} "
                f"specs={len(payload_specs['spi:workorderspec'])}"
            )
        else:
            logging.info(
                f"[crear_inc_ot][RESUMEN_FINAL] ticket={ticket} wonum={wonum} "
                f"cinum_final={cinum_final} (ORIGINAL) "
                f"location={location_final} "
                f"specs={len(payload_specs['spi:workorderspec'])}"
            )

        resultado = {
            "ok":           True,
            "wonum":        wonum,
            "ticket":       ticket,           # NUEVO: el template puede mostrarlo
            "description":  fase_b_payload["spi:description"],
            "specs_count":  len(payload_specs["spi:workorderspec"]),
            "aviso":        aviso_generico,
            "detalle":      None,
        }
        return render_template(
            'crear_ot.html',
            menu_permisos=menu_permisos,
            perfil_usuario=perfil_usuario,
            usuario=usuario,
            form_data=None,
            resultado=resultado,
        )

    except Exception as e:
        logging.exception(f"[crear_inc_ot] excepcion no manejada: {e}")
        return _render_error(
            menu_permisos, perfil_usuario, usuario, form_data,
            mensaje=f"Error inesperado en el flujo incidente+OT: {e}",
        )


def _render_error(menu_permisos, perfil_usuario, usuario, form_data, mensaje, detalle=None):
    """Renderiza el template con un bloque de error y manteniendo los inputs."""
    return render_template(
        'crear_ot.html',
        menu_permisos=menu_permisos,
        perfil_usuario=perfil_usuario,
        usuario=usuario,
        form_data=form_data,
        resultado={"ok": False, "mensaje": mensaje, "detalle": detalle},
    )


def _es_error_cinum_invalido(res_crear: dict) -> bool:
    """
    Detecta si la respuesta de Maximo es el caso 'cinum no reconocido'.

    Maximo devuelve typicamente:
        errorattrname = "cinum"
        moreInfo URL termina en .../messages/BMXAA6199E

    Chequeamos ambas pistas para ser tolerantes a variaciones del mensaje.
    """
    msg = (res_crear.get("message") or "").lower()
    # Pista 1: nombre del atributo que fallo (ignorando espacios alrededor del valor).
    if '"errorattrname":"cinum"' in msg.replace(" ", ""):
        return True
    # Pista 2: codigo de error de Maximo (ya en minusculas por el .lower() de arriba).
    if "bmxaa6199e" in msg:
        return True
    return False


def _construir_mensaje_sin_respaldo(enlace: dict, lado: str) -> str:
    """
    Arma el mensaje de error para el caso en que Maximo rechaza el CI
    y, ademas, NO hay SIT_LOCATION de respaldo en inventario_hlx.

    En ese escenario no podemos reintentar con el CI generico (porque
    quedaria sin ubicacion), asi que la OT no se crea y se le explica
    al usuario que falta el dato de ubicacion.
    """
    if lado == "origen":
        nodo_problema = enlace["device_origen"]
    else:
        nodo_problema = enlace["device_destino"]

    return (
        f"CI no registrado en Maximo y sin respaldo de ubicacion. "
        f"El nodo {nodo_problema} (lado {lado} del enlace "
        f"{enlace['device_origen']} ↔ {enlace['device_destino']}) no esta "
        f"cargado como CI en Maximo, y tampoco se encontro su SIT_LOCATION "
        f"en inventario_hlx. Sin esa ubicacion no es posible crear la OT "
        f"con el CI generico. Verifica el inventario o selecciona el otro "
        f"lado del enlace."
    )