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
URL_BASE:   str = f"{MAXIMO_BASE_URL}/RESTWO"
LOGOUT_URL: str = MAXIMO_BASE_URL.replace("/oslc/os", "/oslc/logout")


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