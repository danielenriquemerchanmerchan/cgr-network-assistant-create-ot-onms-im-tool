from conexiones_db import maximo
from conexiones_db import ptm
from conexiones_db import rose
from sqlalchemy import create_engine, text, Table, MetaData
from sqlalchemy.exc import SQLAlchemyError
import time 
from datetime import datetime, timedelta

#--------------------------------- QUERIES DB ---------------------------------
def q_rose_alarmas_outage_fija():
    consulta="""select manager, manager_first_ocurrance, cinum, node,ip, ciname, ao_alarm_name, emplazamiento, codelocation, departamento, municipio,latitude, longitude, ownergroup from realtime_alarms_view 
where 
ao_alarm_name = 'Linkdown' OR ao_alarm_name = 'Communication with the device failed' OR ao_alarm_name = 'The link between the server and the NE is broken' OR ao_alarm_name = 'Not found the Node'
and ao_source_ip NOT LIKE ('%10.89.245.5%') AND ip NOT LIKE ('%10.37.32.%')
order by manager_first_ocurrance desc"""
    return consulta 

def q_inventario_red_ptm():
    consulta="""SELECT
CINUM,
DESCRIPTION,
CLASSSTRUCTUREID,
DESCRIPTIONCLASSTRUCTUREID,
CILOCATION,
STATUS,
NIVEL,
depto_location,
depto_description,
mun_location,
mun_description,
loc_location,
loc_description,
sit_location,
sit_description,
PERSONGROUP,
RED,
SISTEMA,
BASERVICIO,
IPTV_SERVICIO IPTV,
DXSERVICIO,
LINEAS_SERV,
CIRCUITOS_SER,
E1_SER,
NOMBRE_OSS,
DIRECCION_IP,
FABRICANTE,
MODELO
FROM
    (
       select
       a.CINUM,
       a.DESCRIPTION,
       a.CLASSSTRUCTUREID,
       c.DESCRIPTION DESCRIPTIONCLASSTRUCTUREID,
       a.CILOCATION,
       a.STATUS,
       a.NIVEL,
       b.alnvalue,
       b.assetattrid,
       a.persongroup,
       l.depto_location,
       l.depto_description,
       l.mun_location,
       l.mun_description,
       l.loc_location,
       l.loc_description,
       l.sit_location,
       l.sit_description
       from maximo.ci@CTGINST a
       join maximo.location_view@CTGINST l
       on l.sit_location = a.cilocation
       join maximo.cispec@CTGINST b
       on a.cinum=b.cinum
       JOIN maximo.CLASSSTRUCTURE@CTGINST CL
       on CL.CLASSSTRUCTUREID  = a.CLASSSTRUCTUREID
       LEFT JOIN maximo.classification@CTGINST c
       on c.CLASSIFICATIONID = CL.CLASSIFICATIONID
       where STATUS='OPERATING' and
 a.classstructureid in ('3289', '3804'
       )
    )
    PIVOT (min(alnvalue) FOR assetattrid IN (
        'BASERVICIO' as BASERVICIO,
        'IPTV_SERVICIO' as IPTV_SERVICIO,
        'DXSERVICIO' as DXSERVICIO,
        'LINEAS_SERV' as LINEAS_SERV,
        'CIRCUITOS_SER' as CIRCUITOS_SER,
        'RED' as RED,
        'E1_SER' as E1_SER,
        'SISTEMA' as SISTEMA,
        'NOMBRE OSS' as NOMBRE_OSS,
        'DIRECCION IP' as DIRECCION_IP,
        'FABRICANTE' as FABRICANTE,
        'MODELO' as MODELO
      ))"""
    return consulta
#------------------------------------------------------------------------------

#-------------------------------- CONSULTAS DB --------------------------------
def consulta_rose_outage_fija():
    intentos = 3  # Número máximo de intentos
    for intento in range(intentos):
        try:
            connection = rose()  # Intento de conexión
            print(f"Intento {intento + 1}: Conexión a Rose establecida.")
            cursor = connection.cursor()
            consulta = q_rose_alarmas_outage_fija()
            cursor.execute(consulta)
            resultado = cursor.fetchall()
            connection.close()
            print("Consulta realizada a Rose.")
            if resultado != []:
                print("Se retorna data encontrada en Rose.")
                return resultado
            else:
                return False
        except Exception as exception:
            print(f"Intento {intento + 1}: No se pudo establecer conexión con Rose. Error: {exception}")
            # Si no es el último intento, espera un tiempo antes de reintentar
            if intento < intentos - 1:
                print("Reintentando en 5 segundos...")
                time.sleep(5)
            else:
                print("Se alcanzó el número máximo de intentos.")
                return False

def consulta_ptm_inventario_red_fija():
    try:
        connection=ptm()
        print(connection.version)
        print("Conexion a PTM Exitosa")
        cursor=connection.cursor()
        print("Se va a lanzar consulta de inventario de red fija...")
        consulta=q_inventario_red_ptm()
        cursor.execute(consulta)
        resultado=cursor.fetchall()
        connection.close()
        print('Consulta Realizada del inventario')
        if resultado!=[]:
            print('Se Envia la consulta de PTM')
            return(resultado)          
        else:
            return(False)
            
    except Exception as excepcion:
        print(excepcion)
        return(False)

"""
def insertar_data_tabla_mysql_alarmas_rose(df_alarmas):
    # Parámetros de conexión a MySQL
    user = 'root'
    password = ''
    host = '10.81.37.37'  # o la IP de tu servidor de base de datos
    database = 'reportex'

    print("Se va crear el motor de conexion a MySQL")
    # Crear el motor de conexión a MySQL
    engine = create_engine(f'mysql://{user}:{password}@{host}/{database}')

    # Verificar la conexión a la base de datos
    try:
        with engine.connect() as conn:
            print("Conexión exitosa a la base de datos.")
              
            # Ahora insertar los datos del DataFrame en la tabla
            print("Insertando los datos del DataFrame en la tabla db_dash_impacto_fija_rose...")
            df_alarmas.to_sql('db_dash_impacto_fija_rose', con=engine, if_exists='append', index=False)
            print("Datos insertados correctamente en la tabla db_dash_impacto_fija_rose.")

    except SQLAlchemyError as e:
        print(f"Error al ejecutar la operación: {e}")

def insertar_data_tabla_mysql_inventario_red_fija(df_inv):
    # Parámetros de conexión a MySQL
    user = 'root'
    password = ''
    host = '10.81.37.37'  # o la IP de tu servidor de base de datos
    database = 'reportex'

    print("Se va crear el motor de conexion a MySQL")
    # Crear el motor de conexión a MySQL
    engine = create_engine(f'mysql://{user}:{password}@{host}/{database}')

    # Verificar la conexión a la base de datos
    try:
        with engine.connect() as conn:
            print("Conexión exitosa a la base de datos.")
            
            # Ejecutar el TRUNCATE en la tabla 'db_dash_impacto_fija_inv'
            print("Ejecutando TRUNCATE...")
            conn.execute(text('TRUNCATE TABLE db_dash_impacto_fija_inv'))
            print("Tabla db_dash_impacto_fija_inv truncada correctamente.")
            
            # Ahora insertar los datos del DataFrame en la tabla
            print("Insertando los datos del DataFrame en la tabla...")
            df_inv.to_sql('db_dash_impacto_fija_inv', con=engine, if_exists='append', index=False)
            print("Datos insertados correctamente en la tabla db_dash_impacto_fija_inv.")

    except SQLAlchemyError as e:
        print(f"Error al ejecutar la operación: {e}")

"""
#------------------------------------------------------------------------------