"""
onms/armar_ot.py
----------------
Logica pura de armado de payloads para crear OTs RBHFO en Maximo.

Este modulo NO toca BD ni hace requests HTTP. Solo recibe datos y
devuelve dicts/strings listos para enviar a maximo_api.crear_ot()
y maximo_api.actualizar_ot().

Funciones publicas:
    armar_description(mun_origen, mun_destino)         -> str
    extraer_datos_despacho(enlace, lado)               -> dict
    armar_payload_toplevel(...)                        -> dict
    armar_payload_specs(...)                           -> dict
"""

# ══════════════════════════════════════════════════════════════════
# CONSTANTES DEL PAYLOAD (no cambian segun el input)
# ══════════════════════════════════════════════════════════════════

# Top-level
WOCLASS           = "WORKORDER"
WORKTYPE          = "MC"
STATUS_INICIAL    = "INPRG"
OWNERGROUP        = "O_GESFO"
CLASSSTRUCTUREID  = "4213"

# Specs
TIPO_TRAMO            = "RBHFO"
TIPO_OPERACION_FO     = "Red Movil"
TIPO_CUADRILLA_FO     = "Cuadrilla de Disponibilidad"
OPERADOR_FO           = "Colombia Telecomunicaciones"
OBSERV_CIERRE         = "Pendiente Informe"
COORDENADA_NA         = "NA"
PARADA_RELOJ_INI      = "0,0000"
TIEMPO_EFECT_INI      = "0,0000"


# ══════════════════════════════════════════════════════════════════
# 1. ARMAR DESCRIPTION
# ══════════════════════════════════════════════════════════════════

def armar_description(mun_origen: str, mun_destino: str) -> str:
    """
    Devuelve la description en el formato exacto que usa Maximo:
        'Falla FiOp, Mov. {Mun_Origen} - Mov. {Mun_Destino}'

    Capitaliza los municipios (en la BD vienen en mayusculas).
    """
    def cap(s: str) -> str:
        return s.title() if s else ""
    return f"Falla FiOp, Mov. {cap(mun_origen)} - Mov. {cap(mun_destino)}"


# ══════════════════════════════════════════════════════════════════
# 2. EXTRAER DATOS DE LA PUNTA DE DESPACHO
# ══════════════════════════════════════════════════════════════════

def extraer_datos_despacho(enlace: dict, lado: str) -> dict:
    """
    Dado el dict del enlace (de catalogos.resolver_enlace) y el lado al
    que se despacha la cuadrilla, devuelve los datos del lado de despacho.

    La description se arma SIEMPRE con el orden origen -> destino del
    anillo, independiente de a que lado se despache.

    Parametros:
        enlace (dict): retorno de catalogos.resolver_enlace()
        lado   (str):  'origen' o 'destino'

    Retorna dict con:
        cinum_despacho, location_despacho, municipio_despacho,
        depto_despacho, mun_origen_anillo, mun_destino_anillo
    """
    if lado == "origen":
        cinum    = enlace["device_origen"]
        location = enlace["sit_location_origen"]
        muni     = enlace["mun_origen"]
        depto    = enlace["depto_origen"]
    elif lado == "destino":
        cinum    = enlace["device_destino"]
        location = enlace["sit_location_destino"]
        muni     = enlace["mun_destino"]
        depto    = enlace["depto_destino"]
    else:
        raise ValueError(
            f"lado debe ser 'origen' o 'destino', recibido: {lado}"
        )

    return {
        "cinum_despacho":      cinum,
        "location_despacho":   location,
        "municipio_despacho":  muni,
        "depto_despacho":      depto,
        "mun_origen_anillo":   enlace["mun_origen"],
        "mun_destino_anillo":  enlace["mun_destino"],
    }


# ══════════════════════════════════════════════════════════════════
# 3. ARMAR PAYLOAD TOP-LEVEL
# ══════════════════════════════════════════════════════════════════

def armar_payload_toplevel(
    datos_despacho: dict,
    reported_by: str,
    lead: str,
    impacto: str = "1",
) -> dict:
    """
    Arma el dict que se va a enviar a maximo_api.crear_ot().
    Combina constantes + datos resueltos desde Postgres + inputs del operador.

    Parametros:
        datos_despacho (dict): retorno de extraer_datos_despacho()
        reported_by    (str):  username Maximo de quien crea la OT
        lead           (str):  username Maximo del responsable (default LGMELENDEZHE)
        impacto        (str):  nivel de afectacion ('1' = alto, default '1')

    Retorna dict listo para crear_ot().
    """
    return {
        "description": armar_description(
            datos_despacho["mun_origen_anillo"],
            datos_despacho["mun_destino_anillo"],
        ),
        "woclass":          WOCLASS,
        "worktype":         WORKTYPE,
        "status":           STATUS_INICIAL,
        "ownergroup":       OWNERGROUP,
        "classstructureid": CLASSSTRUCTUREID,
        "cinum":            datos_despacho["cinum_despacho"],
        "location":         datos_despacho["location_despacho"],
        "reportedby":       reported_by,
        "lead":             lead,
        "impacto":          impacto,
    }


# ══════════════════════════════════════════════════════════════════
# 4. HELPERS PRIVADOS PARA SPECS
# ══════════════════════════════════════════════════════════════════

def _spec_aln(attr_id: str, value: str) -> dict:
    """Spec con valor alfanumerico (alnvalue)."""
    return {
        "spi:assetattrid":      attr_id,
        "spi:alnvalue":         value,
        "spi:classstructureid": CLASSSTRUCTUREID,
    }


def _spec_table(attr_id: str, value: str) -> dict:
    """Spec con valor referenciado a tabla (tablevalue)."""
    return {
        "spi:assetattrid":      attr_id,
        "spi:tablevalue":       value,
        "spi:classstructureid": CLASSSTRUCTUREID,
    }


# ══════════════════════════════════════════════════════════════════
# 5. ARMAR PAYLOAD DE SPECS
# ══════════════════════════════════════════════════════════════════

def armar_payload_specs(
    eecc_cuadrilla_fo:    str,
    coordinador_red_fo:   str,
    lider_de_zona_fo:     str,
    responsable_nivel3:   str,
    persona_que_reporta:  str,
    area_que_reporta_fo:  str,
) -> dict:
    """
    Arma el payload de workorderspec que va a actualizar_ot().

    Parametros (todos resueltos antes desde catalogos + frontend):
        eecc_cuadrilla_fo:    EECC asignada al sitio
        coordinador_red_fo:   coordinador de red FO
        lider_de_zona_fo:     personid del lider de zona PI
        responsable_nivel3:   personid del responsable Nivel 3
        persona_que_reporta:  personid del operador que crea la OT
        area_que_reporta_fo:  codigo del area que reporta

    Retorna dict con spi:workorderspec listo para actualizar_ot().
    """
    specs = [
        # Asignacion de campo (desde catalogos)
        _spec_aln  ("EECC_CUADRILLA_FO",         eecc_cuadrilla_fo),
        _spec_aln  ("TIPO_CUADRILLA_FO",         TIPO_CUADRILLA_FO),
        _spec_aln  ("OPERADOR_FO",               OPERADOR_FO),
        _spec_aln  ("COORDINADOR_RED_FO",        coordinador_red_fo),
        _spec_table("LIDER_DE_ZONA_FO",          lider_de_zona_fo),
        _spec_table("RESPONSABLE_ZONA_NIVEL3_FO", responsable_nivel3),

        # Identificacion de quien reporta (desde frontend)
        _spec_table("PERSONA_QUE_REPORTA",       persona_que_reporta),
        _spec_table("AREA_QUE_REPORTA_FO",       area_que_reporta_fo),

        # Tipologia del tramo (constantes para RBHFO)
        _spec_aln  ("TIPO_TRAMO",                TIPO_TRAMO),
        _spec_aln  ("TIPO_OPERACION_FO",         TIPO_OPERACION_FO),

        # Campos de cierre (placeholders al crear)
        _spec_aln  ("OBSERV_CIERRE",             OBSERV_CIERRE),
        _spec_aln  ("COORDENADA_CORTE_LONG",     COORDENADA_NA),
        _spec_aln  ("COORDENADA_CORTE_LAT",      COORDENADA_NA),
        _spec_aln  ("PARADA_RELOJ",              PARADA_RELOJ_INI),
        _spec_aln  ("TIEMPO_EFECT",              TIEMPO_EFECT_INI),
    ]

    return {"spi:workorderspec": specs}