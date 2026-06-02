"""
onms/maximo_api.py
-------------------
Cliente REST mínimo para Maximo. Adaptado del módulo
integrations/maximo/rest_api.py del proyecto cgr-network-assistant.

Solo expone las funciones necesarias para el módulo de creación de OTs:
    crear_ot(datos)            -> dict
    actualizar_ot(href, datos) -> dict
    obtener_href(wonum)        -> str | None

Lee credenciales del .env:
    MAXIMO_BASE_URL
    MAXIMO_USER
    MAXIMO_PASSWORD
    MAXIMO_TIMEOUT (opcional, default 30)
"""

import os
import logging
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Cargar .env (idempotente)
load_dotenv()

# ══════════════════════════════════════════════════════════════════
# CONFIGURACION
# ══════════════════════════════════════════════════════════════════
# Validamos al import. Si falta alguna variable obligatoria, el modulo
# se niega a cargar con un mensaje claro. Esto evita errores raros mas
# tarde y deja a Pylance saber que estas variables son str, no None.

def _requerir_env(nombre: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise RuntimeError(
            f"[onms.maximo_api] Falta variable '{nombre}' en el .env. "
            f"El modulo no puede inicializarse sin esta credencial."
        )
    return valor

MAXIMO_BASE_URL: str = _requerir_env("MAXIMO_BASE_URL")
MAXIMO_USER:     str = _requerir_env("MAXIMO_USER")
MAXIMO_PASSWORD: str = _requerir_env("MAXIMO_PASSWORD")
MAXIMO_TIMEOUT:  int = int(os.getenv("MAXIMO_TIMEOUT", "30"))

# URLs derivadas
URL_BASE:     str = f"{MAXIMO_BASE_URL}/RESTWO"
URL_INCIDENT: str = f"{MAXIMO_BASE_URL}/RESTINCIDENT"
LOGOUT_URL:   str = MAXIMO_BASE_URL.replace("/oslc/os", "/oslc/logout")


# ══════════════════════════════════════════════════════════════════
# HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════════

def _cerrar_sesion(response):
    """
    Cierra la sesion REST de Maximo usando las cookies del response.
    Sin esto, Maximo acumula sesiones huerfanas hasta saturarse.
    """
    try:
        cookies = response.cookies.get_dict()
        if not cookies:
            return
        cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        requests.get(
            LOGOUT_URL,
            auth=HTTPBasicAuth(MAXIMO_USER, MAXIMO_PASSWORD),
            headers={"Cookie": cookie_header},
            timeout=MAXIMO_TIMEOUT,
        )
        logging.debug("Sesion Maximo cerrada")
    except Exception as e:
        logging.warning(f"Error cerrando sesion Maximo: {e}")


def obtener_href(wonum):
    """
    Resuelve el href de una OT a partir de su wonum.
    """
    r = None
    try:
        r = requests.get(
            f'{URL_BASE}?lean=1&oslc.where=wonum="{wonum}"'
            f'&oslc.select=wonum,href',
            auth=HTTPBasicAuth(MAXIMO_USER, MAXIMO_PASSWORD),
            timeout=MAXIMO_TIMEOUT,
        )
        if r.status_code != 200:
            logging.error(f"Error HTTP {r.status_code} al obtener href de OT {wonum}")
            return None
        members = r.json().get("rdfs:member") or r.json().get("member")
        if not members:
            logging.warning(f"OT {wonum} no encontrada")
            return None
        return members[0].get("href") or None
    except Exception as e:
        logging.error(f"Error obteniendo href de OT {wonum}: {e}")
        return None
    finally:
        if r is not None:
            _cerrar_sesion(r)


# ══════════════════════════════════════════════════════════════════
# 1. CREAR OT
# ══════════════════════════════════════════════════════════════════

def crear_ot(datos):
    """
    Crea una OT en Maximo.

    Parametros:
        datos (dict): payload top-level. Minimo requiere description,
                      woclass, worktype, status, ownergroup,
                      classstructureid, cinum, location.

    Retorna:
        dict con: success, message, status, ot (wonum), href
    """
    r = None
    try:
        payload = {
            "orgid":  "MOVISTAR",
            "siteid": "REDES",
            **datos,
        }

        r = requests.post(
            f"{URL_BASE}?lean=1",
            auth=HTTPBasicAuth(MAXIMO_USER, MAXIMO_PASSWORD),
            headers={
                "Content-Type": "application/json",
                "properties":   "wonum,description,status",
            },
            json=payload,
            timeout=MAXIMO_TIMEOUT,
        )

        if r.status_code in (200, 201):
            data  = r.json()
            wonum = data.get("wonum", "")
            href  = r.headers.get("Location", "")
            logging.info(f"OT creada: {wonum}")
            return {
                "success": True,
                "message": f"OT {wonum} creada correctamente",
                "status":  "success",
                "ot":      wonum,
                "href":    href,
            }
        else:
            logging.error(f"Error creando OT HTTP {r.status_code}: {r.text}")
            return {
                "success": False,
                "message": f"Error HTTP {r.status_code}: {r.text[:200]}",
                "status":  "http_error",
                "ot":      None,
            }

    except Exception as e:
        logging.error(f"Error creando OT: {e}")
        return {
            "success": False,
            "message": str(e),
            "status":  "exception",
            "ot":      None,
        }

    finally:
        if r is not None:
            _cerrar_sesion(r)


# ══════════════════════════════════════════════════════════════════
# 2. ACTUALIZAR OT (usado para cargar workorderspec)
# ══════════════════════════════════════════════════════════════════

def actualizar_ot(href, datos):
    """
    Actualiza campos de una OT existente via PATCH al href.
    Usado principalmente para agregar workorderspec despues de crear la OT.

    Parametros:
        href  (str): href completo de la OT (devuelto por crear_ot())
        datos (dict): campos a actualizar con prefijo spi:

    Retorna:
        dict con: success, message, status, ot
    """
    r = None
    try:
        r = requests.post(
            href,
            auth=HTTPBasicAuth(MAXIMO_USER, MAXIMO_PASSWORD),
            headers={
                "x-method-override": "PATCH",
                "patchtype":         "MERGE",
                "properties":        "*",
                "Content-Type":      "application/json",
            },
            json=datos,
            timeout=MAXIMO_TIMEOUT,
        )

        if r.status_code == 200:
            logging.info(f"OT actualizada correctamente: {href}")
            return {
                "success": True,
                "message": "OT actualizada correctamente",
                "status":  "success",
                "ot":      href,
            }
        else:
            logging.error(f"Error actualizando OT HTTP {r.status_code}: {r.text}")
            return {
                "success": False,
                "message": f"Error HTTP {r.status_code}: {r.text[:200]}",
                "status":  "patch_error",
                "ot":      href,
            }

    except Exception as e:
        logging.error(f"Error actualizando OT {href}: {e}")
        return {
            "success": False,
            "message": str(e),
            "status":  "exception",
            "ot":      href,
        }

    finally:
        if r is not None:
            _cerrar_sesion(r)


# ══════════════════════════════════════════════════════════════════
# 3. CREAR INCIDENTE (+ OT automatica)
# ══════════════════════════════════════════════════════════════════
#
# Un unico POST a RESTINCIDENT crea el incidente Y, por configuracion
# de Maximo (createwomulti), genera la OT asociada en la misma operacion.
#
# Nosotros solo enviamos el JSON del incidente; Maximo se encarga
# de crear y vincular la OT.
#
# La OT nace heredando del incidente: classstructureid=1887 y
# ownergroup=O_GESRED. Para dejarla con los datos de fibra
# (classstructureid=4213, O_GESFO, specs, etc.) hay que actualizarla
# despues con actualizar_ot() en 3 fases (estructural / dependiente /
# specs); el orquestador del route se encarga de eso.

def crear_incidente_con_ot(datos):
    """
    Crea un incidente en Maximo (objeto RESTINCIDENT) y dispara la
    generacion automatica de la OT asociada.

    Parametros:
        datos (dict): payload del incidente. Campos minimos:
            description, reportedby, assetsiteid, assetorgid,
            externalsystem, severidad, impact, cinum, ownergroup,
            classificationid, classstructureid, affectedstart,
            multiassetlocci (objeto o lista con el CI afectado)

    Retorna dict:
        success    (bool)
        message    (str)
        status     (str)  'success' | 'http_error' | 'exception'
        ticket     (str)  ticketid del incidente, o None si fallo
        wonum      (str)  wonum de la OT si Maximo lo devuelve en el response.
                          Puede venir vacio: si es asi, consultar con
                          obtener_wonum_de_incidente(ticketid).
        href       (str)  Location header del incidente
        raw        (dict) response completo de Maximo
    """
    r = None
    try:
        r = requests.post(
            f"{URL_INCIDENT}?lean=1",
            auth=HTTPBasicAuth(MAXIMO_USER, MAXIMO_PASSWORD),
            headers={
                "Content-Type": "application/json",
                "properties":   "*",
            },
            json=datos,
            timeout=MAXIMO_TIMEOUT,
        )

        if r.status_code in (200, 201):
            data = r.json()
            ticketid = data.get("spi:ticketid") or data.get("ticketid", "")
            wonum    = data.get("spi:wonum")    or data.get("wonum", "")
            href     = r.headers.get("Location", "")

            logging.info(
                f"Incidente creado: ticketid={ticketid}"
                + (f", wonum={wonum}" if wonum else " (wonum NO en response)")
            )
            return {
                "success": True,
                "message": f"Incidente {ticketid} creado correctamente",
                "status":  "success",
                "ticket":  ticketid,
                "wonum":   wonum,
                "href":    href,
                "raw":     data,
            }
        else:
            logging.error(
                f"Error creando incidente HTTP {r.status_code}: {r.text[:500]}"
            )
            return {
                "success": False,
                "message": f"Error HTTP {r.status_code}: {r.text[:200]}",
                "status":  "http_error",
                "ticket":  None,
                "wonum":   None,
                "href":    "",
                "raw":     None,
            }

    except Exception as e:
        logging.error(f"Error creando incidente: {e}")
        return {
            "success": False,
            "message": str(e),
            "status":  "exception",
            "ticket":  None,
            "wonum":   None,
            "href":    "",
            "raw":     None,
        }

    finally:
        if r is not None:
            _cerrar_sesion(r)


# ══════════════════════════════════════════════════════════════════
# 4. RELACIONES DE INCIDENTE (para obtener el wonum de la OT generada)
# ══════════════════════════════════════════════════════════════════
#
# Cuando crear_incidente_con_ot() no devuelve el wonum en el response
# inmediato (caso comun en algunas versiones de Maximo), hay que ir a
# buscarlo. Las relaciones del incidente se exponen como subrecurso:
#     GET {href_incidente}/relatedrecord
# Los miembros incluyen tanto incidentes como work orders mezclados;
# filtramos por relatedrecclass="WORKORDER" para encontrar la OT
# generada (suele venir con relatetype="FOLLOWUP").

def listar_relaciones_incidente(ticketid):
    """
    Devuelve las relaciones (otros incidentes y OTs) de un incidente.

    Retorna dict:
        success      (bool)
        message      (str)
        relacionados (list[dict])
    """
    r1 = None
    r2 = None
    try:
        r1 = requests.get(
            f'{URL_INCIDENT}/?lean=1'
            f'&oslc.where=ticketid="{ticketid}"'
            f'&oslc.select=ticketid,href',
            auth=HTTPBasicAuth(MAXIMO_USER, MAXIMO_PASSWORD),
            timeout=MAXIMO_TIMEOUT,
        )
        if r1.status_code != 200:
            return {"success": False,
                    "message": f"Error HTTP {r1.status_code} buscando ticket",
                    "relacionados": []}
        members = r1.json().get("rdfs:member") or r1.json().get("member")
        if not members:
            return {"success": False,
                    "message": f"Ticket {ticketid} no encontrado",
                    "relacionados": []}
        href_inc = members[0].get("href", "")
        if not href_inc:
            return {"success": False,
                    "message": "Sin href en el ticket",
                    "relacionados": []}

        r2 = requests.get(
            f"{href_inc}/relatedrecord",
            params={"lean": "1", "oslc.select": "*"},
            auth=HTTPBasicAuth(MAXIMO_USER, MAXIMO_PASSWORD),
            timeout=MAXIMO_TIMEOUT,
        )
        if r2.status_code != 200:
            return {"success": False,
                    "message": f"Error HTTP {r2.status_code} en /relatedrecord",
                    "relacionados": []}
        data = r2.json()
        miembros = data.get("rdfs:member") or data.get("member") or []
        return {"success": True,
                "message": f"{len(miembros)} relacion(es)",
                "relacionados": list(miembros)}

    except Exception as e:
        logging.error(f"Error listando relaciones de ticket {ticketid}: {e}")
        return {"success": False, "message": str(e), "relacionados": []}

    finally:
        if r1 is not None:
            _cerrar_sesion(r1)
        if r2 is not None:
            _cerrar_sesion(r2)


def obtener_wonum_de_incidente(ticketid):
    """
    Filtra las relaciones del incidente y devuelve el wonum de la OT
    generada (relatedrecclass='WORKORDER'). Retorna None si no hay.
    """
    info = listar_relaciones_incidente(ticketid)
    if not info["success"]:
        return None
    for rel in info["relacionados"]:
        clase = (rel.get("relatedrecclass") or "").upper()
        if clase == "WORKORDER":
            return rel.get("relatedreckey")
    return None