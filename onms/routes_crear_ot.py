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

    logging.info(f"[onms.crear_ot POST] usuario={usuario} form={form_data}")

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

        # 7. Armar payload top-level y crear OT
        payload_top = armar_ot.armar_payload_toplevel(
            datos_despacho=datos_despacho,
            reported_by=usuario,
            lead=LEAD_FIJO,
            impacto=IMPACTO_FIJO,
        )
        res_crear = maximo_api.crear_ot(payload_top)

        if not res_crear.get("success"):
            # Caso especial: Maximo no reconoce el CI (cinum) que mandamos.
            if _es_error_cinum_invalido(res_crear):
                mensaje = _construir_mensaje_cinum_invalido(enlace, form_data["lado"])
                return _render_error(
                    menu_permisos, perfil_usuario, usuario, form_data,
                    mensaje=mensaje,
                    # Sin detalle JSON: ya le explicamos al usuario en lenguaje claro.
                )

            # Cualquier otro error de Maximo: mostramos el detalle tecnico.
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=f"Maximo rechazo la creacion de la OT: {res_crear.get('message')}",
                detalle=json.dumps(res_crear, indent=2, ensure_ascii=False),
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

        # 8. Armar payload de specs y actualizar
        payload_specs = armar_ot.armar_payload_specs(
            eecc_cuadrilla_fo    = coord_fibra["eecc_cuadrilla_fo"],
            coordinador_red_fo   = coord_fibra["coordinador_red_fo"],
            lider_de_zona_fo     = coord_pi["lider_de_zona_fo"],
            responsable_nivel3   = LEAD_FIJO,
            persona_que_reporta  = form_data["persona_que_reporta"],
            area_que_reporta_fo  = form_data["area_que_reporta_fo"],
        )
        res_specs = maximo_api.actualizar_ot(href, payload_specs)

        if not res_specs.get("success"):
            return _render_error(
                menu_permisos, perfil_usuario, usuario, form_data,
                mensaje=(f"OT {wonum} creada, pero fallo la carga de specs: "
                         f"{res_specs.get('message')}"),
                detalle=json.dumps(res_specs, indent=2, ensure_ascii=False),
            )

        # 9. Exito
        resultado = {
            "ok":           True,
            "wonum":        wonum,
            "description":  payload_top["description"],
            "specs_count":  len(payload_specs["spi:workorderspec"]),
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


def _construir_mensaje_cinum_invalido(enlace: dict, lado: str) -> str:
    """
    Arma el mensaje amigable para el caso de CI no registrado en Maximo.

    Identifica que nodo especifico fue rechazado (el del lado de despacho)
    y lo enmarca dentro del enlace completo para dar contexto al usuario.
    """
    if lado == "origen":
        nodo_problema = enlace["device_origen"]
    else:
        nodo_problema = enlace["device_destino"]

    return (
        f"CI no registrado en Maximo. El nodo {nodo_problema} "
        f"(lado {lado} del enlace {enlace['device_origen']} ↔ {enlace['device_destino']}) "
        f"no está cargado como CI en Maximo. No es posible crear la OT con ese nodo. "
        f"Verificá el inventario de Maximo o seleccioná el otro lado del enlace."
    )