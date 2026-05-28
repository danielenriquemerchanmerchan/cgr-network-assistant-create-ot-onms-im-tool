"""
routes_trabajos_programados.py
Rutas de Flask para la funcionalidad de Trabajos Programados
"""

from flask import render_template, request, session, redirect, url_for
from functools import wraps
import mysql.connector
from mysql.connector import Error
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de la base de datos
DB_CONFIG = {
    'host': '192.168.44.114',
    'user': 'cgestion',
    'password': 'T3l3f0n1c4',
    'database': 'cgestion'
}

def login_required(f):
    """Decorador para verificar que el usuario esté autenticado"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'USUARIO' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def get_db_connection():
    """Establece y retorna una conexión a la base de datos"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            logger.info("Conexión exitosa a la base de datos")
            return connection
    except Error as e:
        logger.error(f"Error al conectar a la base de datos: {e}")
        return None


def consultar_inventario_por_ips(ips_list):
    """
    Consulta el inventario de equipos OLT por lista de IPs
    
    Args:
        ips_list: Lista de IPs de DSLAM a consultar
        
    Returns:
        Lista de diccionarios con los resultados
    """
    connection = None
    try:
        connection = get_db_connection()
        if not connection:
            logger.error("No se pudo establecer conexión a la base de datos")
            return []
        
        cursor = connection.cursor(dictionary=True)
        
        # Crear placeholders para la consulta
        placeholders = ','.join(['%s'] * len(ips_list))
        
        # Consulta SQL
        query = f"""
            SELECT 
                line_id,
                port,
                dslam,
                dslam_ip,
                cto,
                service_product,
                dba_profile,
                activated,
                velocidad,
                ssid,
                phonenumber,
                cinum,
                tipo_equipo,
                status,
                sit_description,
                operacion,
                persongroup,
                nombre_oss,
                direccion_ip,
                zona_operaciones,
                depto_description,
                mun_description,
                loc_description,
                baservicio,
                dxservicio,
                lineas_serv,
                circuitos_ser,
                e1_ser,
                iptv_servicio,
                fabricante,
                zona_operativa_pr,
                proveedor_red_pr,
                eecc_pe,
                fecha_actualizacion
            FROM inventario_clientes_olt
            WHERE dslam_ip IN ({placeholders})
            ORDER BY dslam_ip, line_id
        """
        
        cursor.execute(query, ips_list)
        resultados = cursor.fetchall()
        
        logger.info(f"Consulta exitosa. {len(resultados)} registros encontrados")
        
        return resultados
        
    except Error as e:
        logger.error(f"Error en la consulta: {e}")
        return []
        
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
            logger.info("Conexión cerrada")


@login_required
def trabajos_programados():
    """Ruta principal para la página de trabajos programados - ACTUALIZADA PARA IPS CON COMAS"""
    
    # Obtener permisos del usuario
    menu_permisos = session.get('menu_permisos', {})
    perfil_usuario = session.get('PERFIL', '')
    
    # Agregar el permiso de trabajos_programados
    if 'trabajos_programados' not in menu_permisos:
        menu_permisos['trabajos_programados'] = True
    
    resultados = []
    ips_consultadas = ''  # ← NUEVO: para mantener las IPs en el textarea
    
    if request.method == 'POST':
        try:
            # ← NUEVO: Obtener el campo de texto con las IPs separadas por comas
            ips_input = request.form.get('ips_input', '').strip()
            
            if ips_input:
                # Separar por comas, limpiar espacios y filtrar vacíos
                ips_list = [ip.strip() for ip in ips_input.split(',') if ip.strip()]
                
                # Guardar para mostrar en el textarea después de consultar
                ips_consultadas = ips_input
                
                # Consultar en la base de datos
                if ips_list:
                    resultados = consultar_inventario_por_ips(ips_list)
                    logger.info(f"Consulta realizada para {len(ips_list)} IPs")
                else:
                    logger.warning("No se proporcionaron IPs para consultar")
        
        except ValueError as e:
            logger.error(f"Error en los datos del formulario: {e}")
        except Exception as e:
            logger.error(f"Error inesperado: {e}")
    
    # ← ACTUALIZADO: ahora retorna ips_consultadas en lugar de cantidad_equipos
    return render_template(
        'trabajos_programados.html',
        resultados=resultados,
        ips_consultadas=ips_consultadas,
        menu_permisos=menu_permisos,
        perfil_usuario=perfil_usuario
    )

# INTEGRACIÓN CON TU APP FLASK PRINCIPAL
# Agregar esta línea a tu archivo principal de Flask (app.py o similar):

"""
from routes_trabajos_programados import trabajos_programados

# Registrar la ruta
app.route('/trabajos_programados', methods=['GET', 'POST'])(trabajos_programados)
"""
