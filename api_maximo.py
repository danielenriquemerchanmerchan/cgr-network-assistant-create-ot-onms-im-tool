import logging
import requests
from requests.auth import HTTPBasicAuth
import psw
import json

# Credenciales API
API_USER = psw.API_USER_MAX
API_PASS = psw.API_PASS_MAX
SESSION_COOKIES = None
LOGOUT_URL = "http://10.80.123.11:8001/maximo/oslc/logout"

# URL base de Maximo
MAXIMO_BASE_URL = "http://10.80.123.11:8001/maximo"

def insertar_avances_ot(ot_trabajo, avance, user):
    """
    Inserta un avance en una orden de trabajo específica de Maximo.
    
    Args:
        ot_trabajo (str): Número de la orden de trabajo
        avance (str): Texto del avance a insertar
        user (str): Usuario que registra el avance
    
    Returns:
        dict: {
            'success': bool,
            'message': str,
            'status': str,
            'ot': str
        }
    """
    global SESSION_COOKIES
    
    # 1. Consultar la OT para validar su existencia y estado
    url_get = (
        f'{MAXIMO_BASE_URL}/oslc/os/RESTWO'
        f'?lean=1&oslc.where=wonum="{ot_trabajo}"'
        f'&oslc.select=wonum,description,woclass,worklog,status,status_description'
    )
    
    try:
        # GET - Obtener información de la OT
        response = requests.get(
            url_get, 
            auth=HTTPBasicAuth(API_USER, API_PASS), 
            timeout=10
        )
        
        # Guardar cookies de sesión para reutilizar
        if not SESSION_COOKIES:
            SESSION_COOKIES = response.cookies.get_dict()
        
        # Validar respuesta HTTP
        if response.status_code != 200:
            logging.error(
                f"❌ Error al consultar OT {ot_trabajo} - "
                f"Código HTTP: {response.status_code}"
            )
            return {
                'success': False,
                'message': f'Error HTTP {response.status_code} al consultar OT',
                'status': 'http_error',
                'ot': ot_trabajo
            }
        
        # Parsear respuesta JSON
        data = response.json()
        logging.debug(
            f"📋 Respuesta completa para OT {ot_trabajo}: "
            f"{json.dumps(data, indent=2)}"
        )
        
        # 2. Validar que la OT existe
        members = data.get("rdfs:member") or data.get("member")
        
        if not members:
            logging.warning(f"⚠️ OT {ot_trabajo} no encontrada en Maximo")
            return {
                'success': False,
                'message': 'Orden de trabajo no encontrada',
                'status': 'not_found',
                'ot': ot_trabajo
            }
        
        if not isinstance(members, list) or len(members) == 0:
            logging.warning(f"⚠️ Formato de respuesta inválido para OT {ot_trabajo}")
            return {
                'success': False,
                'message': 'Formato de respuesta inválido',
                'status': 'invalid_format',
                'ot': ot_trabajo
            }
        
        # 3. Obtener datos de la OT
        wo_data = members[0]
        status = wo_data.get("status", "").upper()
        status_desc = wo_data.get("status_description", "")
        
        logging.info(
            f"📄 OT {ot_trabajo} encontrada - "
            f"Status: {status} ({status_desc})"
        )
        
        # 4. Validar que la OT esté activa (no cerrada)
        estados_cerrados = [
            "CLOSE", "CLOSED", 
            "COMP", "COMPLETED", 
            "CANCEL", "CANCELLED", 
            "HIST", "HISTORIC"
        ]
        
        if status in estados_cerrados:
            logging.warning(
                f"⏸️ OT {ot_trabajo} está CERRADA - "
                f"Status: {status} ({status_desc}). "
                f"No se puede agregar avance."
            )
            return {
                'success': False,
                'message': f'OT cerrada - Status: {status}',
                'status': 'closed',
                'ot': ot_trabajo,
                'wo_status': status
            }
        
        logging.info(f"✅ OT {ot_trabajo} está ACTIVA. Procediendo...")
        
        # 5. Obtener URL de worklog
        href_completo = wo_data.get("worklog_collectionref")
        
        if not href_completo:
            logging.error(
                f"⚠️ No existe 'worklog_collectionref' para OT {ot_trabajo}"
            )
            logging.debug(f"Keys disponibles: {list(wo_data.keys())}")
            return {
                'success': False,
                'message': 'No se encontró referencia de worklog',
                'status': 'no_worklog_ref',
                'ot': ot_trabajo
            }
        
        # Limpiar URL (remover /worklog1 si existe)
        href_base = href_completo.replace("/worklog1", "").rstrip('/')
        logging.debug(f"🔗 URL base para PATCH: {href_base}")
        
        # 6. Preparar PATCH request para insertar avance
        headers = {
            "x-method-override": "PATCH",
            "patchtype": "MERGE",
            "properties": "wonum,status",
            "Content-Type": "application/json"
        }
        
        payload = {
            "spi:worklog": [{
                "spi:description": f"Avance_Revisión_{user}",
                "spi:modifyby": "SMARTSOC",
                "spi:description_longdescription": avance
            }]
        }
        
        logging.debug(
            f"📤 Payload para OT {ot_trabajo}: "
            f"{json.dumps(payload, indent=2)}"
        )
        
        # 7. Ejecutar PATCH para insertar el avance
        response_patch = requests.post(
            href_base,
            auth=HTTPBasicAuth(API_USER, API_PASS),
            headers=headers,
            json=payload,
            timeout=10
        )
        
        # 8. Validar resultado del PATCH
        if response_patch.status_code == 200:
            logging.info(
                f"✅ Avance insertado exitosamente en OT {ot_trabajo}\n"
                f"Usuario: {user}\n"
                f"Avance: {avance[:100]}..."
            )
            return {
                'success': True,
                'message': 'Avance insertado correctamente',
                'status': 'success',
                'ot': ot_trabajo
            }
        else:
            # PATCH falló - intentar extraer detalle del error
            logging.error(
                f"❌ Error al insertar avance en OT {ot_trabajo} - "
                f"Código HTTP: {response_patch.status_code}"
            )
            
            try:
                error_data = response_patch.json()
                error_detail = json.dumps(error_data, indent=2)
                logging.error(f"Detalle del error: {error_detail}")
            except json.JSONDecodeError:
                error_detail = response_patch.text
                logging.error(f"Respuesta del servidor: {error_detail}")
            
            return {
                'success': False,
                'message': f'Error al insertar avance - HTTP {response_patch.status_code}',
                'status': 'patch_error',
                'ot': ot_trabajo,
                'detail': error_detail
            }
    
    except requests.exceptions.Timeout:
        logging.error(f"⏱️ Timeout al procesar OT {ot_trabajo}")
        return {
            'success': False,
            'message': 'Timeout en la petición a Maximo',
            'status': 'timeout',
            'ot': ot_trabajo
        }
    
    except requests.exceptions.RequestException as e:
        logging.error(f"🔌 Error de conexión al procesar OT {ot_trabajo}: {e}")
        return {
            'success': False,
            'message': f'Error de conexión: {str(e)}',
            'status': 'connection_error',
            'ot': ot_trabajo
        }
    
    except Exception as e:
        logging.error(f"❌ Error inesperado al procesar OT {ot_trabajo}: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return {
            'success': False,
            'message': f'Error inesperado: {str(e)}',
            'status': 'exception',
            'ot': ot_trabajo
        }

def cierre_ot(ot_trabajo, cierre, user, tipo_cierre):
    """
    Inserta un avance de solución y/o cambia el estado de una orden de trabajo.
    
    REGLAS:
    - Para CLOSE: La OT debe estar previamente en COMP. No se inserta comentario.
    - Para COMP u otros: Se inserta comentario con la solución.
    
    Args:
        ot_trabajo (str): Número de la orden de trabajo
        cierre (str): Texto de la solución (no usado para CLOSE)
        user (str): Usuario que registra el cierre
        tipo_cierre (str): Estado final deseado ('COMP', 'CLOSE', etc.)
    
    Returns:
        dict: {
            'success': bool,
            'message': str,
            'status': str,
            'ot': str
        }
    """
    global SESSION_COOKIES
    
    # PASO 1: Consultar la OT para validar su existencia y estado
    url_get = (
        f'{MAXIMO_BASE_URL}/oslc/os/RESTWO'
        f'?lean=1&oslc.where=wonum="{ot_trabajo}"'
        f'&oslc.select=wonum,description,woclass,worklog,status,status_description'
    )
    
    try:
        # GET - Obtener información de la OT
        response = requests.get(
            url_get, 
            auth=HTTPBasicAuth(API_USER, API_PASS), 
            timeout=10
        )
        
        # Guardar cookies de sesión para reutilizar
        if not SESSION_COOKIES:
            SESSION_COOKIES = response.cookies.get_dict()
        
        # Validar respuesta HTTP
        if response.status_code != 200:
            logging.error(
                f"❌ Error al consultar OT {ot_trabajo} - "
                f"Código HTTP: {response.status_code}"
            )
            return {
                'success': False,
                'message': f'Error HTTP {response.status_code} al consultar OT',
                'status': 'http_error',
                'ot': ot_trabajo
            }
        
        # Parsear respuesta JSON
        data = response.json()
        logging.debug(
            f"📋 Respuesta completa para OT {ot_trabajo}: "
            f"{json.dumps(data, indent=2)}"
        )
        
        # PASO 2: Validar que la OT existe
        members = data.get("rdfs:member") or data.get("member")
        
        if not members:
            logging.warning(f"⚠️ OT {ot_trabajo} no encontrada en Maximo")
            return {
                'success': False,
                'message': 'Orden de trabajo no encontrada',
                'status': 'not_found',
                'ot': ot_trabajo
            }
        
        if not isinstance(members, list) or len(members) == 0:
            logging.warning(f"⚠️ Formato de respuesta inválido para OT {ot_trabajo}")
            return {
                'success': False,
                'message': 'Formato de respuesta inválido',
                'status': 'invalid_format',
                'ot': ot_trabajo
            }
        
        # PASO 3: Obtener datos de la OT
        wo_data = members[0]
        status = wo_data.get("status", "").upper()
        status_desc = wo_data.get("status_description", "")
        
        logging.info(
            f"📄 OT {ot_trabajo} encontrada - "
            f"Status: {status} ({status_desc})"
        )
        
        # PASO 4: Validar que la OT no esté ya cerrada
        estados_cerrados = [
            "CLOSE", "CLOSED", 
            "CANCEL", "CANCELLED", 
            "HIST", "HISTORIC"
        ]
        
        if status in estados_cerrados:
            logging.warning(
                f"⏸️ OT {ot_trabajo} está CERRADA - "
                f"Status: {status} ({status_desc}). "
                f"No se puede modificar."
            )
            return {
                'success': False,
                'message': f'OT cerrada - Status: {status}',
                'status': 'closed',
                'ot': ot_trabajo,
                'wo_status': status
            }
        
        # PASO 4.5: VALIDACIÓN NUEVA - Para CLOSE, debe estar en COMP
        if tipo_cierre.upper() == "CLOSE":
            if status != "COMP":
                logging.warning(
                    f"⚠️ No se puede cerrar OT {ot_trabajo}. "
                    f"Estado actual: {status}, se requiere estado COMP"
                )
                return {
                    'success': False,
                    'message': f'Para cerrar (CLOSE) la OT debe estar en estado COMP. Estado actual: {status}',
                    'status': 'invalid_transition',
                    'ot': ot_trabajo,
                    'current_status': status,
                    'required_status': 'COMP'
                }
            
            logging.info(f"✅ OT {ot_trabajo} está en COMP. Procediendo a CLOSE sin comentario...")
            
            # Para CLOSE: Solo cambiar estado, sin insertar worklog
            return cambiar_estado_directo(ot_trabajo, "CLOSE", wo_data)
        
        # PASO 5: Para COMP u otros estados - Obtener URL de worklog
        logging.info(f"✅ OT {ot_trabajo} está ACTIVA. Procediendo con cierre tipo {tipo_cierre}...")
        
        href_completo = wo_data.get("worklog_collectionref")
        
        if not href_completo:
            logging.error(
                f"⚠️ No existe 'worklog_collectionref' para OT {ot_trabajo}"
            )
            logging.debug(f"Keys disponibles: {list(wo_data.keys())}")
            return {
                'success': False,
                'message': 'No se encontró referencia de worklog',
                'status': 'no_worklog_ref',
                'ot': ot_trabajo
            }
        
        # Limpiar URL (remover /worklog1 si existe)
        href_base = href_completo.replace("/worklog1", "").rstrip('/')
        logging.debug(f"🔗 URL base para PATCH: {href_base}")
        
        # PASO 6: Preparar PATCH request para insertar avance (SIN spi:status en el worklog)
        # El spi:status dentro del worklog es un campo de la bitácora, NO cambia el estado de la OT
        headers = {
            "x-method-override": "PATCH",
            "patchtype": "MERGE",
            "properties": "wonum,status",
            "Content-Type": "application/json"
        }
        
        payload = {
            "spi:worklog": [{
                "spi:description": f"Avance_Solución_{user}",
                "spi:modifyby": "SMARTSOC",
                "spi:description_longdescription": cierre
            }]
        }
        
        logging.debug(
            f"📤 Payload para OT {ot_trabajo}: "
            f"{json.dumps(payload, indent=2)}"
        )
        
        # PASO 7: Ejecutar PATCH para insertar el avance en worklog_collectionref
        response_patch = requests.post(
            href_base,
            auth=HTTPBasicAuth(API_USER, API_PASS),
            headers=headers,
            json=payload,
            timeout=10
        )
        
        # PASO 8: Validar resultado del PATCH de worklog
        if response_patch.status_code != 200:
            logging.error(
                f"❌ Error al insertar avance en OT {ot_trabajo} - "
                f"Código HTTP: {response_patch.status_code}"
            )
            try:
                error_data = response_patch.json()
                error_detail = json.dumps(error_data, indent=2)
                logging.error(f"Detalle del error: {error_detail}")
            except json.JSONDecodeError:
                error_detail = response_patch.text
                logging.error(f"Respuesta del servidor: {error_detail}")
            
            return {
                'success': False,
                'message': f'Error al insertar avance - HTTP {response_patch.status_code}',
                'status': 'patch_error',
                'ot': ot_trabajo,
                'detail': error_detail
            }
        
        logging.info(f"✅ Avance insertado en worklog de OT {ot_trabajo}")
        
        # PASO 9: Cambiar estado de la OT vía su href (separado del worklog)
        # El cambio de estado debe hacerse directamente sobre el recurso OT, no sobre worklog
        logging.info(f"🔄 PASO 9: Cambiando estado de OT {ot_trabajo} a {tipo_cierre}...")
        resultado_estado = cambiar_estado_directo(ot_trabajo, tipo_cierre, wo_data)
        
        if resultado_estado.get('success'):
            logging.info(
                f"✅ Cierre procesado exitosamente en OT {ot_trabajo}\n"
                f"Usuario: {user}\n"
                f"Estado: {status} → {tipo_cierre}\n"
                f"Solución: {cierre[:100]}..."
            )
            return {
                'success': True,
                'message': f'OT cerrada correctamente con estado {tipo_cierre}',
                'status': 'success',
                'ot': ot_trabajo,
                'new_status': tipo_cierre
            }
        else:
            logging.error(
                f"❌ Avance insertado pero falló el cambio de estado en OT {ot_trabajo}"
            )
            return {
                'success': False,
                'message': f'Avance insertado pero error al cambiar estado: {resultado_estado.get("message")}',
                'status': 'state_change_error',
                'ot': ot_trabajo,
                'detail': resultado_estado
            }
    
    except requests.exceptions.Timeout:
        logging.error(f"⏱️ Timeout al procesar OT {ot_trabajo}")
        return {
            'success': False,
            'message': 'Timeout en la petición a Maximo',
            'status': 'timeout',
            'ot': ot_trabajo
        }
    
    except requests.exceptions.RequestException as e:
        logging.error(f"🔌 Error de conexión al procesar OT {ot_trabajo}: {e}")
        return {
            'success': False,
            'message': f'Error de conexión: {str(e)}',
            'status': 'connection_error',
            'ot': ot_trabajo
        }
    
    except Exception as e:
        logging.error(f"❌ Error inesperado al procesar OT {ot_trabajo}: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return {
            'success': False,
            'message': f'Error inesperado: {str(e)}',
            'status': 'exception',
            'ot': ot_trabajo
        }


def cambiar_estado_directo(ot_trabajo, nuevo_estado, wo_data):
    """
    Cambia el estado de una OT sin insertar worklog.
    Usado específicamente para transición COMP → CLOSE.
    
    Args:
        ot_trabajo (str): Número de la OT
        nuevo_estado (str): Estado destino (típicamente "CLOSE")
        wo_data (dict): Datos de la OT obtenidos previamente
    
    Returns:
        dict: Resultado de la operación
    """
    try:
        # Obtener href de la OT
        href_completo = wo_data.get("rdf:about") or wo_data.get("href")
        
        if not href_completo:
            logging.error(f"⚠️ No se encontró 'href' para OT {ot_trabajo}")
            return {
                'success': False,
                'message': 'No se encontró referencia href de la OT',
                'status': 'no_href',
                'ot': ot_trabajo
            }
        
        logging.info(f"🔗 href obtenido: {href_completo}")
        
        # Preparar headers para cambio de estado
        headers = {
            "x-method-override": "PATCH",
            "patchtype": "MERGE",
            "properties": "status",
            "Content-Type": "application/json"
        }
        
        # Payload solo con cambio de estado
        payload = {
            "spi:status": nuevo_estado
        }
        
        logging.info(
            f"🔄 Cambiando estado de OT {ot_trabajo} a {nuevo_estado} "
            f"(sin insertar comentario)..."
        )
        
        # Ejecutar PATCH
        response_patch = requests.post(
            href_completo,
            auth=HTTPBasicAuth(API_USER, API_PASS),
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response_patch.status_code == 200:
            logging.info(
                f"✅ Estado cambiado exitosamente para OT {ot_trabajo}\n"
                f"Nuevo Estado: {nuevo_estado}"
            )
            return {
                'success': True,
                'message': f'OT cerrada correctamente (COMP → {nuevo_estado})',
                'status': 'success',
                'ot': ot_trabajo,
                'new_status': nuevo_estado
            }
        else:
            logging.error(
                f"❌ Error al cambiar estado de OT {ot_trabajo} - "
                f"Código HTTP: {response_patch.status_code}"
            )
            
            try:
                error_data = response_patch.json()
                error_detail = json.dumps(error_data, indent=2)
                logging.error(f"Detalle del error: {error_detail}")
            except json.JSONDecodeError:
                error_detail = response_patch.text
                logging.error(f"Respuesta del servidor: {error_detail}")
            
            return {
                'success': False,
                'message': f'Error al cambiar estado - HTTP {response_patch.status_code}',
                'status': 'patch_error',
                'ot': ot_trabajo,
                'detail': error_detail
            }
    
    except Exception as e:
        logging.error(f"❌ Error al cambiar estado directo de OT {ot_trabajo}: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return {
            'success': False,
            'message': f'Error inesperado: {str(e)}',
            'status': 'exception',
            'ot': ot_trabajo
        }

def cerrar_sesion():
    """
    Cierra la sesión en Maximo usando cookies previas.
    
    Returns:
        bool: True si se cerró correctamente, False en caso contrario
    """
    global SESSION_COOKIES
    
    if not SESSION_COOKIES:
        logging.info("ℹ️ No hay sesión activa que cerrar")
        return True
    
    ltpa_token = SESSION_COOKIES.get("LtpaToken2")
    jsession_id = SESSION_COOKIES.get("JSESSIONID")
    
    if not (ltpa_token and jsession_id):
        logging.warning("⚠️ No se encontraron cookies válidas para cerrar sesión")
        SESSION_COOKIES = None
        return False
    
    logout_headers = {
        "Cookie": f"LtpaToken2={ltpa_token}; JSESSIONID={jsession_id}"
    }
    
    try:
        logout_response = requests.get(
            LOGOUT_URL, 
            headers=logout_headers, 
            timeout=10
        )
        
        if logout_response.status_code == 200:
            logging.info("🔒 Sesión cerrada exitosamente")
            SESSION_COOKIES = None
            return True
        
        elif logout_response.status_code == 400 and "BMXAA9500E" in logout_response.text:
            logging.info(
                "ℹ️ Token inválido o expirado (BMXAA9500E). "
                "La sesión ya estaba cerrada."
            )
            SESSION_COOKIES = None
            return True
        
        else:
            logging.warning(
                f"⚠️ Error al cerrar sesión: "
                f"{logout_response.status_code} - {logout_response.text}"
            )
            return False
    
    except requests.exceptions.Timeout:
        logging.error("⏱️ Timeout al cerrar sesión")
        return False
    
    except Exception as e:
        logging.error(f"❌ Error al hacer logout: {e}")
        return False


def job_insertar_avances_ots(ot, avance, user):
    """
    Job principal: Inserta avance en Maximo y cierra sesión.
    
    Args:
        ot (str): Número de orden de trabajo
        avance (str): Texto del avance
        user (str): Usuario que registra el avance
    
    Returns:
        dict: Resultado de la operación
    """
    try:
        # Insertar avance en Maximo
        resultado = insertar_avances_ot(ot, avance, user)
        
        return resultado
    
    finally:
        # Siempre cerrar sesión al finalizar
        cerrar_sesion()


def job_cierre_ot(ot, cierre, user, tipo_cierre='COMP'):
    #Se procesa cierre
    cierre_ot(ot, cierre, user, tipo_cierre)
    #Se cierra cesioon
    cerrar_sesion()

def cambiar_grupo_ot(ot_trabajo, grupo_destino, motivo=""):
    """
    Cambia el grupo de personas asignado a una orden de trabajo en Maximo.
    Basado en el documento: API Reasignar Grupo de Personas OT
    
    Args:
        ot_trabajo (str): Número de la orden de trabajo
        grupo_destino (str): Código del grupo al que se reasignará la OT
                           Ejemplos: O_GESFO, O_CAMBO, O_CAMBA, etc.
        motivo (str): Motivo del cambio de grupo (opcional)
    
    Returns:
        dict: {
            'success': bool,
            'message': str,
            'status': str,
            'ot': str,
            'grupo_anterior': str (opcional),
            'grupo_nuevo': str (opcional)
        }
    """
    global SESSION_COOKIES
    
    # PASO 1: Consultar la OT para obtener el href y validar existencia
    url_get = (
        f'{MAXIMO_BASE_URL}/oslc/os/RESTWO'
        f'?lean=1&oslc.where=wonum="{ot_trabajo}"'
        f'&oslc.select=wonum,description,woclass,status,status_description,ownergroup'
    )
    
    try:
        logging.info(f"📡 PASO 1: Consultando OT {ot_trabajo} para obtener href...")
        
        # GET - Obtener información de la OT
        response = requests.get(
            url_get, 
            auth=HTTPBasicAuth(API_USER, API_PASS), 
            timeout=15
        )
        
        # Guardar cookies de sesión para reutilizar
        if not SESSION_COOKIES:
            SESSION_COOKIES = response.cookies.get_dict()
        
        # Validar respuesta HTTP
        if response.status_code != 200:
            logging.error(
                f"❌ Error al consultar OT {ot_trabajo} - "
                f"Código HTTP: {response.status_code}"
            )
            return {
                'success': False,
                'message': f'Error HTTP {response.status_code} al consultar OT',
                'status': 'http_error',
                'ot': ot_trabajo
            }
        
        # Parsear respuesta JSON
        data = response.json()
        logging.debug(
            f"📋 Respuesta completa para OT {ot_trabajo}: "
            f"{json.dumps(data, indent=2)}"
        )
        
        # PASO 2: Validar que la OT existe
        members = data.get("rdfs:member") or data.get("member")
        
        if not members:
            logging.warning(f"⚠️ OT {ot_trabajo} no encontrada en Maximo")
            return {
                'success': False,
                'message': 'Orden de trabajo no encontrada',
                'status': 'not_found',
                'ot': ot_trabajo
            }
        
        if not isinstance(members, list) or len(members) == 0:
            logging.warning(f"⚠️ Formato de respuesta inválido para OT {ot_trabajo}")
            return {
                'success': False,
                'message': 'Formato de respuesta inválido',
                'status': 'invalid_format',
                'ot': ot_trabajo
            }
        
        # PASO 3: Obtener datos de la OT
        wo_data = members[0]
        status = wo_data.get("status", "").upper()
        status_desc = wo_data.get("status_description", "")
        grupo_actual = wo_data.get("ownergroup", "")
        
        logging.info(
            f"📄 OT {ot_trabajo} encontrada - "
            f"Status: {status} ({status_desc}) - "
            f"Grupo Actual: {grupo_actual}"
        )
        
        # PASO 4: Validar que la OT esté activa (no cerrada)
        estados_cerrados = [
            "CLOSE", "CLOSED", 
            "COMP", "COMPLETED", 
            "CANCEL", "CANCELLED", 
            "HIST", "HISTORIC"
        ]
        
        if status in estados_cerrados:
            logging.warning(
                f"⏸️ OT {ot_trabajo} está CERRADA - "
                f"Status: {status} ({status_desc}). "
                f"No se puede cambiar grupo."
            )
            return {
                'success': False,
                'message': f'OT cerrada - Status: {status}',
                'status': 'closed',
                'ot': ot_trabajo,
                'wo_status': status
            }
        
        # PASO 5: Obtener href de la OT
        href_completo = wo_data.get("rdf:about") or wo_data.get("href")
        
        if not href_completo:
            logging.error(f"⚠️ No se encontró 'href' para OT {ot_trabajo}")
            logging.debug(f"Keys disponibles: {list(wo_data.keys())}")
            return {
                'success': False,
                'message': 'No se encontró referencia href de la OT',
                'status': 'no_href',
                'ot': ot_trabajo
            }
        
        logging.info(f"🔗 href obtenido: {href_completo}")
        
        # PASO 6: Construir URL para cambiar grupo según manual PDF
        if "/restwo/" in href_completo:
            url_cambio = f"{href_completo}?action=OWNER&p_grupo={grupo_destino}"
        else:
            url_cambio = f"{MAXIMO_BASE_URL}/oslc/os/restwo/{href_completo}?action=OWNER&p_grupo={grupo_destino}"
        
        logging.info(f"🔗 URL para cambio de grupo: {url_cambio}")
        
        # PASO 7: Preparar headers según manual PDF
        headers = {
            "x-method-override": "PATCH",
            "patchtype": "MERGE",
            "properties": "*",
            "Content-Type": "application/json"
        }
        
        # Payload vacío según manual PDF
        payload = {}
        
        # PASO 8: Insertar avance con el motivo del escalamiento
        if motivo:
            logging.info(f"📝 Insertando avance con motivo de escalamiento...")
            avance_texto = f"🔄 ESCALAMIENTO - Grupo: {grupo_destino}\nMotivo: {motivo}"
            resultado_avance = insertar_avances_ot(ot_trabajo, avance_texto, "SMARTSOC")
            
            if not resultado_avance.get('success'):
                logging.warning(f"⚠️ No se pudo insertar avance: {resultado_avance.get('message')}")
        
        # PASO 9: Ejecutar POST con PATCH para cambiar grupo
        logging.info(f"🔄 PASO 2: Cambiando grupo de OT {ot_trabajo} a {grupo_destino}...")
        
        response_patch = requests.post(
            url_cambio,
            auth=HTTPBasicAuth(API_USER, API_PASS),
            headers=headers,
            json=payload,
            timeout=15
        )
        
        # PASO 10: Validar resultado del cambio
        if response_patch.status_code == 200:
            logging.info(
                f"✅ Grupo cambiado exitosamente para OT {ot_trabajo}\n"
                f"Grupo Anterior: {grupo_actual}\n"
                f"Grupo Nuevo: {grupo_destino}\n"
                f"Motivo: {motivo}"
            )
            return {
                'success': True,
                'message': 'Grupo cambiado correctamente',
                'status': 'success',
                'ot': ot_trabajo,
                'grupo_anterior': grupo_actual,
                'grupo_nuevo': grupo_destino
            }
        else:
            logging.error(
                f"❌ Error al cambiar grupo de OT {ot_trabajo} - "
                f"Código HTTP: {response_patch.status_code}"
            )
            
            try:
                error_data = response_patch.json()
                error_detail = json.dumps(error_data, indent=2)
                logging.error(f"Detalle del error: {error_detail}")
            except json.JSONDecodeError:
                error_detail = response_patch.text
                logging.error(f"Respuesta del servidor: {error_detail}")
            
            return {
                'success': False,
                'message': f'Error al cambiar grupo - HTTP {response_patch.status_code}',
                'status': 'patch_error',
                'ot': ot_trabajo,
                'detail': error_detail
            }
    
    except requests.exceptions.Timeout:
        logging.error(f"⏱️ Timeout al procesar cambio de grupo para OT {ot_trabajo}")
        return {
            'success': False,
            'message': 'Timeout en la petición a Maximo',
            'status': 'timeout',
            'ot': ot_trabajo
        }
    
    except requests.exceptions.RequestException as e:
        logging.error(f"🔌 Error de conexión al procesar OT {ot_trabajo}: {e}")
        return {
            'success': False,
            'message': f'Error de conexión: {str(e)}',
            'status': 'connection_error',
            'ot': ot_trabajo
        }
    
    except Exception as e:
        logging.error(f"❌ Error inesperado al cambiar grupo de OT {ot_trabajo}: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return {
            'success': False,
            'message': f'Error inesperado: {str(e)}',
            'status': 'exception',
            'ot': ot_trabajo
        }


def job_cambiar_grupo_ot(ot, grupo_destino, motivo=""):
    """
    Job principal: Cambia el grupo de una OT en Maximo y cierra sesión.
    
    Args:
        ot (str): Número de orden de trabajo
        grupo_destino (str): Código del grupo destino
        motivo (str): Motivo del cambio (opcional)
    
    Returns:
        dict: Resultado de la operación
    """
    try:
        # Cambiar grupo en Maximo
        resultado = cambiar_grupo_ot(ot, grupo_destino, motivo)
        return resultado
    finally:
        # Siempre cerrar sesión al finalizar
        cerrar_sesion()

"""
# Ejemplo de uso
if __name__ == "__main__":
    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Ejemplo de inserción
    resultado = job_insertar_avances_ots(
        ot="12345",
        avance="Se realizó la inspección del equipo. Todo en orden.",
        user="FRODRIGUEZ"
    )
    
    print(f"\nResultado: {json.dumps(resultado, indent=2)}")
    #Se inserta avance en máximo
    insertar_avances_ot(ot, avance, user)
    #Se cierra cesion maximo
    cerrar_sesion()"""