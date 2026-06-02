"""
onms/catalogos.py
-----------------
Consultas de lectura a las tablas catalogo del schema 'onms'.

Cada funcion abre su propia conexion a Postgres y la cierra al terminar.
No mantiene pool ni cache (las queries son lo suficientemente rapidas).

Lee credenciales del .env:
    PG_HOST
    PG_PORT
    PG_USER
    PG_PASSWORD
    PG_DATABASE
"""

import os
import logging
import psycopg2
from dotenv import load_dotenv

load_dotenv()


# ══════════════════════════════════════════════════════════════════
# CONFIGURACION
# ══════════════════════════════════════════════════════════════════

def _requerir_env(nombre: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise RuntimeError(
            f"[onms.catalogos] Falta variable '{nombre}' en el .env."
        )
    return valor

PG_HOST:     str = _requerir_env("PG_HOST")
PG_PORT:     int = int(os.getenv("PG_PORT", "5432"))
PG_USER:     str = _requerir_env("PG_USER")
PG_PASSWORD: str = _requerir_env("PG_PASSWORD")
PG_DATABASE: str = _requerir_env("PG_DATABASE")


# ══════════════════════════════════════════════════════════════════
# CONEXION INTERNA
# ══════════════════════════════════════════════════════════════════

def _abrir_conexion():
    """
    Abre una conexion a Postgres. Las funciones del modulo la usan
    via context manager 'with' para garantizar el cierre.
    """
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DATABASE,
    )


# ══════════════════════════════════════════════════════════════════
# 1. RESOLVER ENLACE (inventario_anillo_bh_fusion)
# ══════════════════════════════════════════════════════════════════

def resolver_enlace(punta_a: str, punta_b: str):
    """
    Busca el enlace (Punta A, Punta B) en inventario_anillo_bh_fusion.
    Acepta el enlace en cualquier orden (A->B o B->A) para no depender
    de como el operador haya seleccionado las puntas en el frontend.

    Parametros:
        punta_a, punta_b (str): nombres de los devices HL5

    Retorna:
        dict con las columnas del enlace, o None si no existe.
    """
    sql = """
        SELECT id, anillo,
               device_origen,  mun_origen,  depto_origen,
               sit_location_origen,  sit_description_origen,
               device_destino, mun_destino, depto_destino,
               sit_location_destino, sit_description_destino
        FROM   onms.inventario_anillo_bh_fusion
        WHERE  (device_origen = %s AND device_destino = %s)
            OR (device_origen = %s AND device_destino = %s)
        LIMIT 1
    """
    try:
        with _abrir_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (punta_a, punta_b, punta_b, punta_a))
                row = cur.fetchone()
                if not row or cur.description is None:
                    return None
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
    except Exception as e:
        logging.error(f"[catalogos.resolver_enlace] {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# 2. RESOLVER COORDINADOR FIBRA (cat_coord_fibra)
# ══════════════════════════════════════════════════════════════════

def resolver_coord_fibra(departamento: str, municipio: str):
    """
    Busca la EECC y coordinador de red para una ubicacion.
    Aplica la regla de override por municipio:
      - Si hay fila para (depto, municipio), la usa.
      - Si no, cae al default del departamento (municipio NULL).

    Retorna dict con eecc_cuadrilla_fo y coordinador_red_fo,
    o None si no hay match en el catalogo.
    """
    sql = """
        SELECT eecc_cuadrilla_fo, coordinador_red_fo
        FROM   onms.cat_coord_fibra
        WHERE  departamento = %s
          AND  (municipio = %s OR municipio IS NULL)
        ORDER  BY municipio NULLS LAST
        LIMIT  1
    """
    try:
        with _abrir_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (departamento, municipio))
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "eecc_cuadrilla_fo":  row[0],
                    "coordinador_red_fo": row[1],
                }
    except Exception as e:
        logging.error(f"[catalogos.resolver_coord_fibra] {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# 3. RESOLVER LIDER DE ZONA PI (cat_coord_pi)
# ══════════════════════════════════════════════════════════════════

def resolver_coord_pi(departamento: str):
    """
    Busca el lider de zona de planta interna para un departamento.

    Retorna dict con lider_de_zona_fo, o None si no hay match.
    """
    sql = """
        SELECT lider_de_zona_fo
        FROM   onms.cat_coord_pi
        WHERE  departamento = %s
        LIMIT  1
    """
    try:
        with _abrir_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (departamento,))
                row = cur.fetchone()
                if not row:
                    return None
                return {"lider_de_zona_fo": row[0]}
    except Exception as e:
        logging.error(f"[catalogos.resolver_coord_pi] {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# 3b. RESOLVER SIT_LOCATION POR CINUM (inventario_hlx)
# ══════════════════════════════════════════════════════════════════

def resolver_sit_location(cinum: str):
    """
    Busca el SIT_LOCATION (codigo 'S####') de un CI en inventario_hlx.

    Se usa como respaldo para el caso en que Maximo rechaza el cinum
    original al crear la OT: en ese escenario la OT se reintenta con
    el cinum generico (ENLTEL_FOGEN), que NO trae ubicacion propia, y
    hay que pasarle explicitamente esta SIT_LOCATION.

    Por eso esta location se pre-captura ANTES de intentar crear la OT:
    asi, si Maximo rechaza el CI, ya la tenemos en mano y el reintento
    es inmediato.

    Parametros:
        cinum (str): el CI del nodo de despacho. Ej: 'ATL_BQA_VICT_N501'

    Retorna:
        str con el SIT_LOCATION (ej. 'S6849'), o None si el cinum no
        esta en inventario_hlx o si su SIT_LOCATION viene vacio.
    """
    cinum = (cinum or "").strip()
    if not cinum:
        return None

    # Las columnas de inventario_hlx son case-sensitive (creadas con
    # comillas dobles en mayuscula): hay que referenciarlas entre "".
    sql = """
        SELECT "SIT_LOCATION"
        FROM   onms.inventario_hlx
        WHERE  "CINUM" = %s
        LIMIT  1
    """
    try:
        with _abrir_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (cinum,))
                row = cur.fetchone()
                if not row:
                    return None
                sit_location = (row[0] or "").strip()
                return sit_location or None
    except Exception as e:
        logging.error(f"[catalogos.resolver_sit_location] {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# 4. BUSCAR PERSONAS (cat_persona_maximo) — para autocomplete
# ══════════════════════════════════════════════════════════════════

def buscar_personas(query: str, limit: int = 20):
    """
    Autocomplete de personas. Busca en displayname y personid.

    Parametros:
        query (str): texto a buscar (minimo 2 caracteres)
        limit (int): cantidad maxima de resultados (default 20)

    Retorna:
        lista de dicts con personid y displayname (y vacio si query < 2).
    """
    query = (query or "").strip()
    if len(query) < 2:
        return []

    patron = f"%{query}%"
    sql = """
        SELECT personid, displayname
        FROM   onms.cat_persona_maximo
        WHERE  status = 'ACTIVE'
          AND  (displayname ILIKE %s OR personid ILIKE %s)
        ORDER  BY displayname
        LIMIT  %s
    """
    try:
        with _abrir_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (patron, patron, limit))
                return [
                    {"personid": r[0], "displayname": r[1]}
                    for r in cur.fetchall()
                ]
    except Exception as e:
        logging.error(f"[catalogos.buscar_personas] {e}")
        return []


# ══════════════════════════════════════════════════════════════════
# 5. LISTAR AREAS (cat_area_reporta)
# ══════════════════════════════════════════════════════════════════

def listar_areas():
    """
    Devuelve la lista de codigos de area validos.
    Usado por el frontend para poblar el dropdown de AREA_QUE_REPORTA_FO.

    Retorna:
        lista de strings con los codigos, o [] si hay error.
    """
    sql = "SELECT codigo FROM onms.cat_area_reporta ORDER BY codigo"
    try:
        with _abrir_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [r[0] for r in cur.fetchall()]
    except Exception as e:
        logging.error(f"[catalogos.listar_areas] {e}")
        return []