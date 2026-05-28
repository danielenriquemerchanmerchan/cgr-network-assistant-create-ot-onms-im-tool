import mysql.connector
import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('replicacion_enlaces.log'),
        logging.StreamHandler()
    ]
)

# Configuración de conexiones
MARIADB_CONFIG = {
    'host': '10.30.4.104',
    'user': 'cgestion',
    'password': 'RO_consulta!2025',
    'database': 'Enlaces'
}

POSTGRES_CONFIG = {
    'host': '192.168.44.114',
    'user': 'cgestion',
    'password': 'T3l3f0n1c4',
    'database': 'cgestion',
    'port': 5432
}

def extraer_datos_mariadb():
    """Extrae datos de la tabla enlaces en MariaDB"""
    try:
        conn = mysql.connector.connect(**MARIADB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT 
                SitioOrg,
                Origen,
                IP_Origen,
                Puerto_Origen,
                SitioDest,
                Destino,
                IP_Destino,
                Puerto_Destino
            FROM enlaces
        """
        
        cursor.execute(query)
        datos = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        logging.info(f"Extraídos {len(datos)} registros de MariaDB (Enlaces.enlaces)")
        return datos
        
    except Exception as e:
        logging.error(f"Error extrayendo datos de MariaDB: {e}")
        raise

def cargar_datos_postgres(datos):
    """Carga datos en la tabla enlaces de PostgreSQL en el schema smartsoc"""
    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        cursor = conn.cursor()
        
        # Crear schema si no existe
        cursor.execute("CREATE SCHEMA IF NOT EXISTS smartsoc")
        
        # Eliminar tabla existente
        cursor.execute("DROP TABLE IF EXISTS smartsoc.enlaces")
        
        # Crear tabla con los tipos de datos correctos
        crear_tabla = """
            CREATE TABLE IF NOT EXISTS smartsoc.enlaces (
                id SERIAL PRIMARY KEY,
                sitio_org VARCHAR(255),
                origen VARCHAR(255),
                ip_origen VARCHAR(45),
                puerto_origen VARCHAR(64),
                sitio_dest VARCHAR(255),
                destino VARCHAR(255),
                ip_destino VARCHAR(45),
                puerto_destino VARCHAR(64),
                fecha_replicacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        cursor.execute(crear_tabla)
        
        # Preparar datos para inserción
        query_insert = """
            INSERT INTO smartsoc.enlaces 
            (sitio_org, origen, ip_origen, puerto_origen, sitio_dest, destino, ip_destino, puerto_destino)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        datos_insert = [
            (
                d['SitioOrg'],
                d['Origen'],
                d['IP_Origen'],
                d['Puerto_Origen'],
                d['SitioDest'],
                d['Destino'],
                d['IP_Destino'],
                d['Puerto_Destino']
            )
            for d in datos
        ]
        
        # Inserción por lotes para mejor rendimiento
        execute_batch(cursor, query_insert, datos_insert, page_size=1000)
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logging.info(f"Cargados {len(datos)} registros en PostgreSQL (cgestion.smartsoc.enlaces)")
        
    except Exception as e:
        logging.error(f"Error cargando datos en PostgreSQL: {e}")
        raise

def replicar_enlaces():
    """Proceso principal de replicación"""
    try:
        logging.info("=== Iniciando proceso de replicación de enlaces ===")
        inicio = datetime.now()
        
        # Extraer datos de MariaDB
        datos = extraer_datos_mariadb()
        
        if not datos:
            logging.warning("No hay datos para replicar")
            return
        
        # Cargar datos en PostgreSQL
        cargar_datos_postgres(datos)
        
        fin = datetime.now()
        duracion = (fin - inicio).total_seconds()
        
        logging.info(f"=== Replicación completada en {duracion:.2f} segundos ===")
        
    except Exception as e:
        logging.error(f"Error en el proceso de replicación: {e}")
        raise

if __name__ == "__main__":
    replicar_enlaces()