from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from datetime import timedelta, datetime
import cx_Oracle
import config
import mysql.connector
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import config_permisos
from middleware_permisos import login_requerido, permiso_requerido, solo_admin, inyectar_permisos
import hashlib
from config import ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD
from functools import lru_cache
from threading import Lock
from typing import cast
import time
from decimal import Decimal
from api_maximo import job_insertar_avances_ots, job_cierre_ot, job_cambiar_grupo_ot
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Response
import requests
from dotenv import load_dotenv
import os

load_dotenv() 

DB_MAXIMO_USER=os.getenv('DB_MAXIMO_USER')
DB_MAXIMO_PASSWORD=os.getenv('DB_MAXIMO_PASSWORD')
DB_MAXIMO_DSN=os.getenv('DB_MAXIMO_DSN')
DB_MAXIMO_HOST=os.getenv('DB_MAXIMO_HOST')
DB_MAXIMO_PORT=os.getenv('DB_MAXIMO_PORT')
DB_MAXIMO_SERVICE_NAME=os.getenv('DB_MAXIMO_SERVICE_NAME')
DB_PTM_USER=os.getenv('DB_PTM_USER')
DB_PTM_PASSWORD=os.getenv('DB_PTM_PASSWORD')
DB_PTM_DSN=os.getenv('DB_PTM_DSN')
DB_MYSQL_114_USER=os.getenv('DB_MYSQL_114_USER')
DB_MYSQL_114_PASSWORD=os.getenv('DB_MYSQL_114_PASSWORD')
DB_MYSQL_114_DB_CG=os.getenv('DB_MYSQL_114_DB_CG')
DB_MYSQL_114_DB_R=os.getenv('DB_MYSQL_114_DB_R')
DB_MYSQL_114_HOST=os.getenv('DB_MYSQL_114_HOST')
DB_POSTGRES_114_USER=os.getenv('DB_POSTGRES_114_USER')
DB_POSTGRES_114_PASSWORD=os.getenv('DB_POSTGRES_114_PASSWORD')
DB_POSTGRES_114_DB_CG=os.getenv('DB_POSTGRES_114_DB_CG')
DB_POSTGRES_114_DB_SOC=os.getenv('DB_POSTGRES_114_DB_SOC')
DB_POSTGRES_114_HOST=os.getenv('DB_POSTGRES_114_HOST')
API_MAXIMO_USER=os.getenv('API_MAXIMO_USER')
API_MAXIMO_PASSWORD=os.getenv('API_MAXIMO_PASSWORD')

# ============================================
# SISTEMA DE CACHÉ PARA TOTALES DE USUARIOS
# ============================================
cache_totales = {
    'datos': None,
    'timestamp': 0,
    'lock': Lock()
}

cache_anillos = {
    'datos': None,
    'timestamp': 0,
    'lock': Lock(),
    'ttl': 300
}

# Tiempo de expiración del caché (15 minutos = 900 segundos)
CACHE_EXPIRACION = 900

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = '1234567890'
app.config['JSON_AS_ASCII'] = False

# Configuración de Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.session_protection = "strong"
app.permanent_session_lifetime = timedelta(minutes=30)

# Clase de usuario para Flask-Login
class User(UserMixin):
    id = None

@login_manager.user_loader
def load_user(user_id):
    user = User()
    user.id = user_id
    return user

@app.context_processor
def utility_processor():
    """
    Inyecta variables globales en todas las plantillas
    """
    from middleware_permisos import inyectar_permisos
    return inyectar_permisos()

# Configuración de la conexión a Oracle
def get_db_connection():
    connection = cx_Oracle.connect(
        config.ORACLE_USER,
        config.ORACLE_PASSWORD,
        config.ORACLE_DSN
    )
    return connection

# Configuración de la conexión a MySQL
mysql_config = {
    'user': DB_MYSQL_114_USER,
    'password': DB_MYSQL_114_PASSWORD,
    'host': DB_MYSQL_114_HOST,
    'database': DB_MYSQL_114_DB_R,
    'port': 3306,
    'use_pure': True,
    'auth_plugin': 'mysql_native_password'
    }

def get_mysql_connection():
    """Obtiene una conexión a MySQL"""
    try:
        connection = mysql.connector.connect(**mysql_config)
        return connection
    except Exception as e:
        logging.error(f"Error conectando a MySQL: {e}")
        # Propaga el error para que el endpoint responda 500 y no intente usar None
        raise

# Configuración de la conexión a PostgreSQL
def get_postgres_connection():
    """
    Conexión a PostgreSQL para base de datos cgestion
    """
    try:
        connection = psycopg2.connect(
            host=DB_POSTGRES_114_HOST,
            database=DB_POSTGRES_114_DB_CG,
            user=DB_POSTGRES_114_USER,
            password=DB_POSTGRES_114_PASSWORD,
            port=5432
        )
        return connection
    except Exception as e:
        logging.error(f"Error conectando a PostgreSQL: {e}")
        raise

# ============================================
# RUTAS
# ============================================
@app.before_request
def verificar_sesion_personalizada():
    """
    Verifica el tipo de sesión del usuario y ajusta el timeout
    antes de procesar cada request
    """
    if 'USUARIO' in session:
        # Si el usuario tiene sesión permanente configurada
        if session.get('SESION_PERMANENTE') == 1:
            # Renovar la sesión en cada request (sin expiración)
            session.permanent = True
            session.modified = True
        else:
            # Sesión temporal con timeout de 30 minutos
            session.permanent = True
            # El lifetime ya está configurado globalmente

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['u']
        password = request.form['p']
        
        try:
            # Intentar autenticar desde la base de datos Oracle
            connection = cx_Oracle.connect(
                user=DB_PTM_USER, 
                password=DB_PTM_PASSWORD, 
                dsn=DB_PTM_DSN, 
                encoding='UTF-8'
            )
            cursor = connection.cursor()
            
            # â­ MODIFICADO: Incluir campo SESION_PERMANENTE
            cursor.execute("""
                SELECT USUARIO, PASSWORD, NOMBRE, APELLIDO, CORREO, PERFIL, ACTIVO, SESION_PERMANENTE
                FROM SMARTSOC_USUARIOS
                WHERE USUARIO = :usuario AND ACTIVO = 1
            """, {'usuario': username})
            
            user_data = cursor.fetchone()
            cursor.close()
            connection.close()
            
            if user_data and user_data[1] == hash_password(password):
                # Crear objeto de usuario para Flask-Login
                user = User()
                user.id = username
                login_user(user)
                
                # â­ MODIFICADO: Configurar sesión según el tipo de usuario
                sesion_permanente = user_data[7] if len(user_data) > 7 else 0
                
                if sesion_permanente == 1:
                    # Sesión sin timeout
                    session.permanent = True
                    app.permanent_session_lifetime = timedelta(days=365)  # Prácticamente sin límite
                else:
                    # Sesión con timeout de 30 minutos
                    session.permanent = True
                    app.permanent_session_lifetime = timedelta(minutes=30)
                
                # Guardar datos en la sesión
                session['USUARIO'] = user_data[0]
                session['NOMBRE'] = user_data[2]
                session['APELLIDO'] = user_data[3]
                session['CORREO'] = user_data[4]
                session['PERFIL'] = user_data[5]
                session['SESION_PERMANENTE'] = sesion_permanente  # â­ NUEVO
                session['FECHA_HORA_INGRESO'] = datetime.now().strftime('%d/%m/%y %H:%M:%S')
                
                # Registrar en auditoría
                tipo_sesion = "sin timeout" if sesion_permanente == 1 else "30 minutos"
                registrar_auditoria(username, 'LOGIN', 
                                   f'Inicio de sesión exitoso - Perfil: {user_data[5]} - Tipo sesión: {tipo_sesion}')
                
                flash(f'Bienvenido {user_data[2]}!', 'success')
                return redirect(url_for('home'))
            else:
                flash('Credenciales incorrectas. Inténtalo de nuevo.', 'error')
                return redirect(url_for('login'))
                
        except cx_Oracle.DatabaseError as e:
            print(f"Error de base de datos: {str(e)}")
            flash('Error de conexión. Inténtalo más tarde.', 'error')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/home')
@login_requerido  
def home():
    return render_template('home.html')

@app.route('/logout', methods=['POST'])
@login_requerido
def logout():
    registrar_auditoria(session.get('USUARIO', 'unknown'), 'LOGOUT', 'Cierre de sesión')
    flash('Se ha cerrado la sesión.', 'info')
    logout_user()
    session.clear()
    return redirect(url_for('login'))

@app.route('/actualizar_tipo_sesion', methods=['POST'])
@login_requerido
@solo_admin
def actualizar_tipo_sesion():
    """
    Actualiza el tipo de sesión de un usuario (con/sin timeout)
    """
    try:
        usuario_red = request.form.get('usuario_red')
        sesion_permanente = 1 if request.form.get('sesion_permanente') == 'on' else 0
        
        connection = cx_Oracle.connect(
            user=DB_PTM_USER,
            password=DB_PTM_PASSWORD,
            dsn=DB_PTM_DSN,
            encoding='UTF-8'
        )
        cursor = connection.cursor()
        
        # Verificar que el usuario existe
        cursor.execute("""
            SELECT NOMBRE, APELLIDO FROM SMARTSOC_USUARIOS
            WHERE USUARIO = :usuario
        """, {'usuario': usuario_red})
        
        usuario_info = cursor.fetchone()
        if not usuario_info:
            flash('Usuario no encontrado', 'error')
            return redirect(url_for('gestion_usuarios'))
        
        # Actualizar tipo de sesión
        cursor.execute("""
            UPDATE SMARTSOC_USUARIOS
            SET SESION_PERMANENTE = :sesion_permanente
            WHERE USUARIO = :usuario
        """, {
            'sesion_permanente': sesion_permanente,
            'usuario': usuario_red
        })
        
        connection.commit()
        cursor.close()
        connection.close()
        
        # Registrar en auditoría
        tipo = "sin timeout" if sesion_permanente == 1 else "con timeout 30min"
        registrar_auditoria(
            session.get('USUARIO'),
            'MODIFICAR_TIPO_SESION',
            f'Cambió tipo de sesión de {usuario_red} a: {tipo}'
        )
        
        nombre_completo = f"{usuario_info[0]} {usuario_info[1]}"
        flash(f'Tipo de sesión actualizado correctamente para {nombre_completo}', 'success')
        
    except Exception as e:
        logging.error(f"Error al actualizar tipo de sesión: {str(e)}")
        flash(f'Error al actualizar tipo de sesión: {str(e)}', 'error')
    
    return redirect(url_for('gestion_usuarios'))
    
@app.route('/callcenter', methods=['GET', 'POST'])
@login_requerido
@permiso_requerido('callcenter')
def consultar_callcenter():
    resultados = []
    total_servicios = 0

    if request.method == 'POST':
        try:
            # Obtener valores del formulario
            id_equipo = request.form.get('id_equipo', '').strip()
            tarjeta = request.form.get('tarjeta', '').strip()
            puerto = request.form.get('puerto', '').strip()

            # Conexión a MySQL
            connection = mysql.connector.connect(
                host=DB_MYSQL_114_HOST,
                user=DB_MYSQL_114_USER,
                password=DB_MYSQL_114_PASSWORD,
                database=DB_MYSQL_114_DB_CG
            )
            cursor = connection.cursor()

            # Construir query con lógica para detectar formato
            query = """
            SELECT 
                PhoneNumber AS Telefono, 
                LINE_ID AS ID_Cliente, 
                IFNULL(SUBSTRING(First_Contact_Time, 1, 10), '') AS fecha_creacion,
                PPPoEUser AS cuenta_padre, 
                'FTTH' AS tecnologia, 
                DSLAM AS zona_cobertura, 
                DSLAM_IP AS id_equipo,
                
                -- Detectar formato y extraer Tarjeta
                CASE 
                    WHEN PORT LIKE '0-%' THEN 
                        SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '-', 2), '-', -1)
                    WHEN PORT LIKE '1-1-%' THEN 
                        SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '-', 3), '-', -1)
                    ELSE ''
                END AS tarjeta,
                
                -- Detectar formato y extraer Puerto
                CASE 
                    WHEN PORT LIKE '0-%' THEN 
                        SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '#', 1), '-', -1)
                    WHEN PORT LIKE '1-1-%' THEN 
                        SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '#', 1), '-', -1)
                    ELSE ''
                END AS puerto,
                
                -- OntId es igual para ambos formatos
                SUBSTRING_INDEX(PORT, '#', -1) AS OntId,
                
                CTO AS cto,
                SERVICE_PRODUCT AS vel_plan, 
                BA_FS AS estado_servicio, 
                'PON' AS tipo_puerto, 
                PhoneNumber AS NUMERO_ABONADO
            FROM planta_ftth
            WHERE 1=1
            """
            
            params = []
            
            # Filtro por IP
            if id_equipo:
                query += " AND DSLAM_IP = %s"
                params.append(id_equipo)
            
            # Filtro por Tarjeta
            if tarjeta and id_equipo:
                query += """ AND (
                    (PORT LIKE '0-%' AND SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '-', 2), '-', -1) = %s)
                    OR
                    (PORT LIKE '1-1-%' AND SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '-', 3), '-', -1) = %s)
                )"""
                params.append(tarjeta)
                params.append(tarjeta)
            
            # Filtro por Puerto
            if puerto and tarjeta and id_equipo:
                query += " AND SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '#', 1), '-', -1) = %s"
                params.append(puerto)
            
            # ORDER BY dinámico
            if puerto and tarjeta and id_equipo:
                query += " ORDER BY CAST(SUBSTRING_INDEX(PORT, '#', -1) AS UNSIGNED)"
            elif tarjeta and id_equipo:
                query += " ORDER BY CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '#', 1), '-', -1) AS UNSIGNED), CAST(SUBSTRING_INDEX(PORT, '#', -1) AS UNSIGNED)"
            elif id_equipo:
                query += """ ORDER BY 
                    CASE 
                        WHEN PORT LIKE '0-%' THEN CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '-', 2), '-', -1) AS UNSIGNED)
                        WHEN PORT LIKE '1-1-%' THEN CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '-', 3), '-', -1) AS UNSIGNED)
                        ELSE 0
                    END,
                    CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '#', 1), '-', -1) AS UNSIGNED),
                    CAST(SUBSTRING_INDEX(PORT, '#', -1) AS UNSIGNED)
                """
            
            query += " LIMIT 1000"

            print(f"=== DEBUG ===")
            print(f"ID_Equipo: {id_equipo}")
            print(f"Tarjeta: {tarjeta}")
            print(f"Puerto: {puerto}")

            cursor.execute(query, tuple(params))
            
            # Obtener nombres de columnas
            column_names = [desc[0] for desc in (cursor.description or [])]
            
            # Convertir resultados a lista de diccionarios
            rows = cursor.fetchall()
            resultados = []
            for row in rows:
                resultados.append(dict(zip(column_names, row)))
            
            total_servicios = len(resultados)
            
            print(f"Total servicios encontrados: {total_servicios}")

            cursor.close()
            connection.close()
            
        except Exception as e:
            print(f"ERROR EN CONSULTA: {str(e)}")
            import traceback
            traceback.print_exc()

    return render_template('callcenter.html', resultados=resultados, total_servicios=total_servicios)

@app.route('/callcenter_abonados', methods=['GET', 'POST'])
@login_requerido
@permiso_requerido('callcenter_abonados')
def callcenter_abonados():
    resultados = []
    
    if request.method == 'POST':
        try:
            abonado = request.form.get('NUMERO_ABONADO', '').strip()
            
            if not abonado:
                return render_template('callcenter_abonados.html', resultados=[])
            
            # Conexión a MySQL
            connection = mysql.connector.connect(
                host=DB_MYSQL_114_HOST,
                user=DB_MYSQL_114_USER,
                password=DB_MYSQL_114_PASSWORD,
                database=DB_MYSQL_114_DB_CG
            )
            cursor = connection.cursor()
            
            # Query SIN columnas calculadas (más lento pero funciona)
            query = """
            SELECT 
                PhoneNumber AS Telefono, 
                LINE_ID AS ID_Cliente, 
                IFNULL(SUBSTRING(First_Contact_Time, 1, 10), '') AS fecha_creacion,
                PPPoEUser AS cuenta_padre, 
                'FTTH' AS tecnologia, 
                DSLAM AS zona_cobertura, 
                DSLAM_IP AS id_equipo,
                CASE 
                    WHEN PORT LIKE '0-%%' THEN SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '-', 2), '-', -1)
                    WHEN PORT LIKE '1-1-%%' THEN SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '-', 3), '-', -1)
                    ELSE ''
                END AS tarjeta,
                SUBSTRING_INDEX(SUBSTRING_INDEX(PORT, '#', 1), '-', -1) AS puerto,
                SUBSTRING_INDEX(PORT, '#', -1) AS OntId,
                CTO AS cto,
                SERVICE_PRODUCT AS vel_plan, 
                BA_FS AS estado_servicio, 
                'PON' AS tipo_puerto, 
                PhoneNumber AS NUMERO_ABONADO
            FROM planta_ftth
            WHERE PhoneNumber = %s
            LIMIT 100
            """
            
            cursor.execute(query, (abonado,))
            
            # Obtener nombres de columnas
            column_names = [desc[0] for desc in (cursor.description or [])]
            
            # Convertir resultados a lista de diccionarios
            rows = cursor.fetchall()
            resultados = []
            for row in rows:
                resultados.append(dict(zip(column_names, row)))
            
            print(f"=== DEBUG ABONADOS ===")
            print(f"Número buscado: {abonado}")
            print(f"Resultados encontrados: {len(resultados)}")
            
            cursor.close()
            connection.close()
            
        except Exception as e:
            print(f"ERROR EN CONSULTA ABONADOS: {str(e)}")
            import traceback
            traceback.print_exc()
    
    return render_template('callcenter_abonados.html', resultados=resultados)

@app.route('/dashboard')
@login_requerido
@permiso_requerido('dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/dash_fija')
@login_requerido
@permiso_requerido('dash_fija')
def dash_fija():
    return render_template('dash_fija.html')

@app.route('/dash_movil')
@login_requerido
@permiso_requerido('dash_movil')
def dash_movil():
    return render_template('dash_movil.html')

@app.route('/dash_backhaul')
@login_requerido
@permiso_requerido('dash_backhaul')
def dash_backhaul():
    return render_template('dash_backhaul.html')

@app.route('/monitoreo_hl5')
@login_requerido
@permiso_requerido('monitoreo_hl5') 
def monitoreo_hl5():
    return render_template('monitoreo_hl5.html')

@app.route('/seguimiento_hl5')
@login_requerido
@permiso_requerido('seguimiento_hl5')
def seguimiento_hl5():
    """
    Página principal de seguimiento HL5
    """
    return render_template('seguimiento_hl5.html')

@app.route('/aperturas_anillos')
@login_requerido
@permiso_requerido('aperturas_anillos')
def aperturas_anillos():
    return render_template('aperturas_anillos.html')

@app.route('/monitoreo_hl4')
@login_requerido
@permiso_requerido('dashboard')
def monitoreo_hl4():
    return render_template('monitoreo_hl4.html')

@app.route('/monitoreo_hl3')
@login_requerido
@permiso_requerido('dashboard')
def monitoreo_hl3():
    return render_template('monitoreo_hl3.html')

@app.route('/servicio_al_cliente')
@login_requerido
@permiso_requerido('servicio_al_cliente')
def servicio_al_cliente():
    return render_template('servicio_al_cliente.html')

@app.route('/onms')
@login_requerido
@permiso_requerido('onms')
def onms():
    return render_template('onms.html')

# ============================================
# RUTA PRINCIPAL DE GOBERNANZA
# ============================================
@app.route('/gobernanza')
@login_requerido
@permiso_requerido('gobernanza')
def gobernanza():
    return render_template('gobernanza.html')

@app.route('/gobernanza/sla-onnet')
@login_requerido
@permiso_requerido('gobernanza')
def sla_onnet():
    return render_template('sla_onnet.html')

@app.route('/gobernanza/sla-unired')
@login_requerido
@permiso_requerido('gobernanza')
def sla_unired():
    return render_template('sla_unired.html')

# ============================================
# SOLICITUDES DE USUARIO
# ============================================

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    """
    Ruta para manejar el registro de nuevos usuarios
    """
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        apellido = request.form.get('apellido', '').strip()
        correo = request.form.get('correo', '').strip()
        area = request.form.get('area', '').strip()
        usuario_red = request.form.get('usuario_red', '').strip()
        telefono = request.form.get('telefono', '').strip()
        password = request.form.get('password', '')
        confirmar_password = request.form.get('confirmar_password', '')
        
        errores = []
        
        if not all([nombre, apellido, correo, area, usuario_red, telefono, password, confirmar_password]):
            errores.append('Todos los campos son obligatorios')
        
        if correo and not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', correo):
            errores.append('El formato del correo electrónico no es válido')
        
        if password != confirmar_password:
            errores.append('Las contraseñas no coinciden')
        
        if password and not validar_password(password):
            errores.append('La contraseña debe tener al menos 8 caracteres, incluyendo mayúsculas, minúsculas y números')
        
        if not errores:
            try:
                connection = cx_Oracle.connect(user=DB_PTM_USER, password=DB_PTM_PASSWORD, 
                                              dsn=DB_PTM_DSN, encoding='UTF-8')
                cursor = connection.cursor()
                
                cursor.execute("""
                    SELECT COUNT(*) FROM SMARTSOC_SOLICITUDES_USUARIO 
                    WHERE (CORREO = :correo OR USUARIO_RED = :usuario) 
                    AND ESTADO = 'PENDIENTE'
                """, {'correo': correo, 'usuario': usuario_red})
                
                if cursor.fetchone()[0] > 0:
                    errores.append('Ya existe una solicitud pendiente con este correo o usuario de red')
                
                cursor.execute("""
                    SELECT COUNT(*) FROM SMARTSOC_USUARIOS 
                    WHERE (CORREO = :correo OR USUARIO = :usuario) 
                    AND ACTIVO = 1
                """, {'correo': correo, 'usuario': usuario_red})
                
                if cursor.fetchone()[0] > 0:
                    errores.append('Este correo o usuario ya existe en el sistema')
                
                cursor.close()
                connection.close()
                
            except Exception as e:
                print(f'Error verificando duplicados: {str(e)}')
                errores.append('Error al verificar datos. Intenta nuevamente.')
        
        if errores:
            for error in errores:
                flash(error, 'error')
            return render_template('registro.html', solicitud_enviada=False)
        
        try:
            connection = cx_Oracle.connect(user=DB_PTM_USER, password=DB_PTM_PASSWORD, 
                                          dsn=DB_PTM_DSN, encoding='UTF-8')
            cursor = connection.cursor()
            
            cursor.execute("""
                INSERT INTO SMARTSOC_SOLICITUDES_USUARIO 
                (ID_SOLICITUD, NOMBRE, APELLIDO, CORREO, AREA, USUARIO_RED, TELEFONO, PASSWORD_SOLICITADO, ESTADO)
                VALUES (SMARTSOC_SEQ_SOLICITUDES.NEXTVAL, :nombre, :apellido, :correo, :area, :usuario_red, :telefono, :password, 'PENDIENTE')
            """, {
                'nombre': nombre,
                'apellido': apellido,
                'correo': correo,
                'area': area,
                'usuario_red': usuario_red,
                'telefono': telefono,
                'password': password
            })
            
            connection.commit()
            cursor.close()
            connection.close()
            
            enviar_email_solicitud(nombre, apellido, correo, area, usuario_red, telefono, password)
            
            return render_template('registro.html', solicitud_enviada=True)
            
        except cx_Oracle.DatabaseError as e:
            error, = e.args
            print(f'Error guardando solicitud: {error.message}')
            flash('Error al procesar la solicitud. Por favor, intenta nuevamente.', 'error')
            return render_template('registro.html', solicitud_enviada=False)
        except Exception as e:
            print(f'Error general: {str(e)}')
            flash('Error al procesar la solicitud. Por favor, contacta al administrador.', 'error')
            return render_template('registro.html', solicitud_enviada=False)
    
    return render_template('registro.html', solicitud_enviada=False)


def validar_password(password):
    """Valida requisitos de contraseña"""
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'\d', password):
        return False
    return True


def enviar_email_solicitud(nombre, apellido, correo, area, usuario_red, telefono, password):
    """Envía correo de solicitud al administrador"""
    smtp_server = "10.80.19.186"
    smtp_port = 25
    sender_email = "centro.gestion.co.automatizacion@telefonica.com"
    receiver_emails = [
    "edgar.acevedo@telefonica.com",
    "deisy.camachov@telefonica.com",
    "daniel.merchan@telefonica.com"
]
    
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = f"Nueva Solicitud de Usuario SmartSOC - {nombre} {apellido}"
        message["From"] = sender_email
        message["To"] = ", ".join(receiver_emails)
        message["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S")
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #0166ff; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9f9f9; padding: 20px; border: 1px solid #ddd; }}
                table {{ width: 100%; border-collapse: collapse; background-color: white; margin-top: 15px; }}
                td {{ padding: 12px; border: 1px solid #ddd; }}
                td:first-child {{ background-color: #f0f0f0; font-weight: bold; width: 40%; }}
                .footer {{ background-color: #f0f0f0; padding: 15px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 5px 5px; }}
                .alert {{ background-color: #fff3cd; border: 1px solid #ffc107; padding: 10px; border-radius: 5px; margin-top: 15px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Nueva Solicitud de Usuario - SmartSOC</h2>
                </div>
                <div class="content">
                    <p>Se ha recibido una nueva solicitud de acceso al sistema SmartSOC.</p>
                    <p><strong>Fecha y hora:</strong> {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}</p>
                    <h3>Datos del Solicitante:</h3>
                    <table>
                        <tr><td>Nombre</td><td>{nombre} {apellido}</td></tr>
                        <tr><td>Correo</td><td>{correo}</td></tr>
                        <tr><td>Área</td><td>{area}</td></tr>
                        <tr><td>Usuario de Red</td><td>{usuario_red}</td></tr>
                        <tr><td>Teléfono</td><td>{telefono}</td></tr>
                        <tr><td>Contraseña</td><td>{password}</td></tr>
                    </table>
                    <div class="alert">
                        <strong>Acción Requerida:</strong> Revisa y procesa esta solicitud.
                    </div>
                </div>
                <div class="footer">
                    <p>SmartSOC - Jefatura Centro de Gestión © 2024</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        part = MIMEText(html, "html")
        message.attach(part)
        
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.sendmail(sender_email, receiver_emails, message.as_string())
        server.quit()
        
        print(f"✓ Correo enviado a {receiver_emails}")
        return True
        
    except Exception as e:
        print(f"✗ Error enviando correo: {str(e)}")
        return False


# ============================================
# ADMINISTRACIÓN DE SOLICITUDES
# ============================================

@app.route('/admin/solicitudes')
@login_requerido
@solo_admin
def admin_solicitudes():
    """Página de administración de solicitudes"""
    try:
        connection = cx_Oracle.connect(user=DB_PTM_USER, password=DB_PTM_PASSWORD, 
                                          dsn=DB_PTM_DSN, encoding='UTF-8')
        cursor = connection.cursor()
        
        query = """
            SELECT 
                ID_SOLICITUD, FECHA_SOLICITUD, NOMBRE, APELLIDO, CORREO,
                AREA, USUARIO_RED, TELEFONO, ESTADO, PERFIL_ASIGNADO,
                FECHA_PROCESADO, PROCESADO_POR
            FROM SMARTSOC_SOLICITUDES_USUARIO
            ORDER BY FECHA_SOLICITUD DESC
        """
        
        cursor.execute(query)
        solicitudes = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) FROM SMARTSOC_SOLICITUDES_USUARIO WHERE ESTADO = 'PENDIENTE'")
        solicitudes_pendientes = cursor.fetchone()[0]
        
        cursor.close()
        connection.close()
        
        return render_template('admin_solicitudes.html', 
                             solicitudes=solicitudes,
                             solicitudes_pendientes=solicitudes_pendientes)
    
    except cx_Oracle.DatabaseError as e:
        error, = e.args
        print(f"Error: {error.message}")
        flash('Error al cargar las solicitudes', 'error')
        return redirect(url_for('home'))


@app.route('/admin/procesar_solicitud', methods=['POST'])
@login_requerido
@solo_admin
def procesar_solicitud():
    """Procesa aprobación o rechazo de solicitud"""
    id_solicitud = request.form.get('id_solicitud')
    accion = request.form.get('accion')
    
    if not id_solicitud or not accion:
        flash('Datos incompletos', 'error')
        return redirect(url_for('admin_solicitudes'))
    
    try:
        connection = cx_Oracle.connect(user=DB_PTM_USER, password=DB_PTM_PASSWORD, 
                                          dsn=DB_PTM_DSN, encoding='UTF-8')
        cursor = connection.cursor()
        
        cursor.execute("""
            SELECT NOMBRE, APELLIDO, CORREO, AREA, USUARIO_RED, TELEFONO, PASSWORD_SOLICITADO
            FROM SMARTSOC_SOLICITUDES_USUARIO
            WHERE ID_SOLICITUD = :id AND ESTADO = 'PENDIENTE'
        """, {'id': id_solicitud})
        
        solicitud = cursor.fetchone()
        
        if not solicitud:
            flash('Solicitud no encontrada o ya procesada', 'error')
            cursor.close()
            connection.close()
            return redirect(url_for('admin_solicitudes'))
        
        nombre, apellido, correo, area, usuario_red, telefono, password = solicitud
        
        # 🔍 LOG: Imprimir datos que vamos a insertar
        print(f"\n{'='*60}")
        print(f"📋 DATOS DE LA SOLICITUD A PROCESAR:")
        print(f"{'='*60}")
        print(f"ID Solicitud: {id_solicitud}")
        print(f"Usuario Red: {usuario_red}")
        print(f"Correo: {correo}")
        print(f"Nombre: {nombre} {apellido}")
        print(f"Área: {area}")
        print(f"{'='*60}\n")
        
        if accion == 'aprobar':
            perfil = request.form.get('perfil')
            observaciones = request.form.get('observaciones', '')
            
            if not perfil:
                flash('Debe asignar un perfil', 'error')
                cursor.close()
                connection.close()
                return redirect(url_for('admin_solicitudes'))
            
            # 🔍 VERIFICAR: ¿Existe en SMARTSOC_USUARIOS?
            cursor.execute("""
                SELECT USUARIO, CORREO, ACTIVO
                FROM SMARTSOC_USUARIOS 
                WHERE USUARIO = :usuario OR CORREO = :correo
            """, {'usuario': usuario_red, 'correo': correo})
            
            usuarios_existentes = cursor.fetchall()
            
            if usuarios_existentes:
                print(f"\n❌ USUARIOS EXISTENTES ENCONTRADOS:")
                for u in usuarios_existentes:
                    print(f"   - Usuario: {u[0]}, Correo: {u[1]}, Activo: {u[2]}")
                
                flash(f'❌ Error: El usuario "{usuario_red}" o correo "{correo}" ya existe', 'error')
                cursor.close()
                connection.close()
                return redirect(url_for('admin_solicitudes'))
            else:
                print(f"✅ No hay conflictos. Procediendo a insertar...")
            
            try:
                # Hashear contraseña
                password_hasheada = hash_password(password)
                
                print(f"🔐 Contraseña hasheada: {password_hasheada[:20]}...")
                
                # 🔍 LOG: Intentando insertar
                print(f"\n📝 INSERTANDO NUEVO USUARIO...")
                
                cursor.execute("""
                    INSERT INTO SMARTSOC_USUARIOS (
                        ID_USUARIO, USUARIO, PASSWORD, NOMBRE, APELLIDO, CORREO,
                        AREA, TELEFONO, PERFIL, ACTIVO, CREADO_POR, ID_SOLICITUD_ORIGEN
                    ) VALUES (
                        SMARTSOC_SEQ_USUARIOS.NEXTVAL, :usuario, :password, :nombre, :apellido, :correo,
                        :area, :telefono, :perfil, 1, :creado_por, :id_solicitud
                    )
                """, {
                    'usuario': usuario_red,
                    'password': password_hasheada,
                    'nombre': nombre,
                    'apellido': apellido,
                    'correo': correo,
                    'area': area,
                    'telefono': telefono,
                    'perfil': perfil,
                    'creado_por': session['USUARIO'],
                    'id_solicitud': id_solicitud
                })
                
                print(f"✅ INSERT ejecutado correctamente")
                
                # Actualizar solicitud
                cursor.execute("""
                    UPDATE SMARTSOC_SOLICITUDES_USUARIO
                    SET ESTADO = 'APROBADO',
                        PERFIL_ASIGNADO = :perfil,
                        FECHA_PROCESADO = SYSDATE,
                        PROCESADO_POR = :procesado_por,
                        OBSERVACIONES = :observaciones
                    WHERE ID_SOLICITUD = :id
                """, {
                    'perfil': perfil,
                    'procesado_por': session['USUARIO'],
                    'observaciones': observaciones,
                    'id': id_solicitud
                })
                
                print(f"✅ UPDATE de solicitud ejecutado")
                
                connection.commit()
                print(f"✅ COMMIT exitoso\n")
                
                registrar_auditoria(session['USUARIO'], 'APROBAR_SOLICITUD', 
                                   f'Aprobó solicitud ID {id_solicitud} - Usuario: {usuario_red}')
                
                enviar_email_aprobacion(nombre, apellido, correo, usuario_red, password, perfil)
                
                flash(f'✅ Usuario {usuario_red} aprobado con perfil {perfil}', 'success')
                
            except cx_Oracle.IntegrityError as e:
                connection.rollback()
                error_obj, = e.args
                
                # 🔍 LOG: Error detallado
                print(f"\n❌ IntegrityError CAPTURADO:")
                print(f"   Código: {error_obj.code}")
                print(f"   Mensaje: {error_obj.message}")
                print(f"   Contexto: {error_obj.context}\n")
                
                # Identificar qué constraint falló
                if 'USUARIO' in str(error_obj.message).upper():
                    flash(f'❌ El usuario "{usuario_red}" ya existe en el sistema', 'error')
                elif 'CORREO' in str(error_obj.message).upper():
                    flash(f'❌ El correo "{correo}" ya existe en el sistema', 'error')
                else:
                    flash(f'❌ Error de integridad: {error_obj.message}', 'error')
            
            except Exception as e:
                connection.rollback()
                print(f"\n❌ OTRO ERROR:")
                print(f"   Tipo: {type(e).__name__}")
                print(f"   Mensaje: {str(e)}\n")
                flash(f'❌ Error al crear usuario: {str(e)}', 'error')
        
        elif accion == 'rechazar':
            motivo = request.form.get('motivo_rechazo', '').strip()
            
            if not motivo:
                flash('Debe especificar motivo del rechazo', 'error')
                cursor.close()
                connection.close()
                return redirect(url_for('admin_solicitudes'))
            
            cursor.execute("""
                UPDATE SMARTSOC_SOLICITUDES_USUARIO
                SET ESTADO = 'RECHAZADO',
                    FECHA_PROCESADO = SYSDATE,
                    PROCESADO_POR = :procesado_por,
                    MOTIVO_RECHAZO = :motivo
                WHERE ID_SOLICITUD = :id
            """, {
                'procesado_por': session['USUARIO'],
                'motivo': motivo,
                'id': id_solicitud
            })
            
            connection.commit()
            
            registrar_auditoria(session['USUARIO'], 'RECHAZAR_SOLICITUD', 
                               f'Rechazó solicitud ID {id_solicitud}')
            
            enviar_email_rechazo(nombre, apellido, correo, motivo)
            
            flash(f'❌ Solicitud de {nombre} {apellido} rechazada', 'success')
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"\n❌ ERROR GENERAL EN procesar_solicitud:")
        print(f"   Tipo: {type(e).__name__}")
        print(f"   Mensaje: {str(e)}\n")
        import traceback
        traceback.print_exc()
        flash(f'Error al procesar solicitud: {str(e)}', 'error')
    
    return redirect(url_for('admin_solicitudes'))

# ============================================
# GESTIÓN USUARIOS
# ============================================

@app.route('/gestion_usuarios')
@login_requerido
@solo_admin
def gestion_usuarios():
    """
    Página de gestión de usuarios - Solo para administradores
    """
    try:
        connection = cx_Oracle.connect(user=DB_PTM_USER, password=DB_PTM_PASSWORD,
                                       dsn=DB_PTM_DSN, encoding='UTF-8')
        cursor = connection.cursor()
 
        # ── 1. Usuarios con su último login ──────────────────────────────
        cursor.execute("""
            SELECT u.USUARIO, u.NOMBRE, u.APELLIDO, u.CORREO, u.AREA, u.TELEFONO,
                   u.PERFIL, u.ACTIVO, u.FECHA_CREACION, u.SESION_PERMANENTE,
                   (SELECT MAX(a.FECHA_ACCESO)
                    FROM SMARTSOC_AUDITORIA_ACCESOS a
                    WHERE a.USUARIO = u.USUARIO
                      AND a.ACCION  = 'LOGIN') AS ULTIMO_LOGIN
            FROM SMARTSOC_USUARIOS u
            ORDER BY u.FECHA_CREACION DESC
        """)
 
        usuarios = []
        for row in cursor:
            ultimo_login = row[10]
            usuarios.append({
                'usuario':          row[0],
                'nombre':           row[1],
                'apellido':         row[2],
                'correo':           row[3],
                'area':             row[4],
                'telefono':         row[5],
                'perfil':           row[6],
                'estado':           'ACTIVO' if row[7] == 1 else 'INACTIVO',
                'fecha_creacion':   row[8].strftime('%d/%m/%Y') if row[8] else '',
                'sesion_permanente': row[9] if row[9] is not None else 0,
                'ultimo_login':     ultimo_login.strftime('%d/%m/%Y %H:%M') if ultimo_login else None,
                # ISO para comparación en JS
                'ultimo_login_iso': ultimo_login.strftime('%Y-%m-%dT%H:%M:%S') if ultimo_login else '',
            })
 
        # ── 2. Usuarios actualmente conectados ───────────────────────────
        # Lógica: el último evento de LOGIN/LOGOUT del usuario es LOGIN
        # Y ese login ocurrió hace menos de 8 horas (margen generoso).
        cursor.execute("""
            SELECT DISTINCT a.USUARIO
            FROM SMARTSOC_AUDITORIA_ACCESOS a
            WHERE a.ACCION = 'LOGIN'
              AND a.FECHA_ACCESO >= SYSDATE - 1/3          -- últimas 8 horas
              AND a.FECHA_ACCESO = (
                    SELECT MAX(a2.FECHA_ACCESO)
                    FROM   SMARTSOC_AUDITORIA_ACCESOS a2
                    WHERE  a2.USUARIO = a.USUARIO
                      AND  a2.ACCION IN ('LOGIN', 'LOGOUT')
              )
        """)
        conectados_set = {row[0] for row in cursor.fetchall()}
 
        for u in usuarios:
            u['conectado'] = u['usuario'] in conectados_set
 
        usuarios_conectados = len(conectados_set)
 
        # ── 3. Histograma de logins por hora (últimos 30 días) ───────────
        cursor.execute("""
            SELECT TO_NUMBER(TO_CHAR(FECHA_ACCESO, 'HH24')) AS HORA,
                   COUNT(*) AS ACCESOS
            FROM   SMARTSOC_AUDITORIA_ACCESOS
            WHERE  ACCION      = 'LOGIN'
              AND  FECHA_ACCESO >= SYSDATE - 30
            GROUP BY TO_NUMBER(TO_CHAR(FECHA_ACCESO, 'HH24'))
            ORDER BY HORA
        """)
        horas_raw = cursor.fetchall()
        histo = {int(r[0]): int(r[1]) for r in horas_raw}
        histograma_horas = [histo.get(h, 0) for h in range(24)]
 
        cursor.close()
        connection.close()
 
        # ── 4. Estadísticas ───────────────────────────────────────────────
        total_usuarios    = len(usuarios)
        usuarios_activos  = sum(1 for u in usuarios if u['estado'] == 'ACTIVO')
        usuarios_inactivos = total_usuarios - usuarios_activos
 
        perfiles_count = {}
        for u in usuarios:
            perfiles_count[u['perfil']] = perfiles_count.get(u['perfil'], 0) + 1
 
        return render_template('gestion_usuarios.html',
                               usuarios=usuarios,
                               total_usuarios=total_usuarios,
                               usuarios_activos=usuarios_activos,
                               usuarios_inactivos=usuarios_inactivos,
                               perfiles_count=perfiles_count,
                               usuarios_conectados=usuarios_conectados,
                               histograma_horas=histograma_horas)
 
    except Exception as e:
        logging.error(f"Error en gestión de usuarios: {str(e)}")
        flash(f'Error al cargar usuarios: {str(e)}', 'error')
        return redirect(url_for('home'))
 

# ============================================
# RUTA: EDITAR USUARIO
# ============================================

@app.route('/editar_usuario', methods=['POST'])
@login_requerido
@solo_admin
def editar_usuario():
    """
    Edita un usuario: nombre, apellido, correo, área, perfil, estado y sesión.
    """
    try:
        usuario_red      = request.form.get('usuario_red', '').strip()
        nombre           = request.form.get('nombre', '').strip()
        apellido         = request.form.get('apellido', '').strip()
        correo           = request.form.get('correo', '').strip()
        area             = request.form.get('area', '').strip()
        perfil           = request.form.get('perfil', '').strip()
        estado           = 1 if request.form.get('estado') == 'ACTIVO' else 0
        sesion_permanente = 1 if request.form.get('sesion_permanente') == 'on' else 0
 
        if not usuario_red:
            flash('Usuario no especificado', 'error')
            return redirect(url_for('gestion_usuarios'))
 
        connection = cx_Oracle.connect(user=DB_PTM_USER, password=DB_PTM_PASSWORD,
                                       dsn=DB_PTM_DSN, encoding='UTF-8')
        cursor = connection.cursor()
 
        cursor.execute("""
            UPDATE SMARTSOC_USUARIOS
               SET NOMBRE            = :nombre,
                   APELLIDO          = :apellido,
                   CORREO            = :correo,
                   AREA              = :area,
                   PERFIL            = :perfil,
                   ACTIVO            = :estado,
                   SESION_PERMANENTE = :sesion_permanente
             WHERE USUARIO = :usuario
        """, {
            'nombre':            nombre,
            'apellido':          apellido,
            'correo':            correo,
            'area':              area,
            'perfil':            perfil,
            'estado':            estado,
            'sesion_permanente': sesion_permanente,
            'usuario':           usuario_red,
        })
 
        connection.commit()
        cursor.close()
        connection.close()
 
        tipo_sesion = "sin timeout" if sesion_permanente == 1 else "30 min"
        registrar_auditoria(
            session.get('USUARIO'),
            'MODIFICAR_USUARIO',
            (f'Editó {usuario_red}: nombre={nombre} {apellido}, '
             f'correo={correo}, área={area}, perfil={perfil}, '
             f'estado={"ACTIVO" if estado else "INACTIVO"}, sesión={tipo_sesion}')
        )
 
        flash(f'Usuario {usuario_red} actualizado correctamente', 'success')
 
    except Exception as e:
        logging.error(f"Error al editar usuario: {str(e)}")
        flash(f'Error al editar usuario: {str(e)}', 'error')
 
    return redirect(url_for('gestion_usuarios'))

# ============================================
# RUTA: CAMBIAR CONTRASEÑA
# ============================================

@app.route('/cambiar_password', methods=['POST'])
@login_requerido
@solo_admin
def cambiar_password():
    """
    Cambia la contraseña de un usuario
    """
    usuario_red = request.form.get('usuario_red', '')
    nueva_password = request.form.get('nueva_password', '')
    confirmar_password = request.form.get('confirmar_password', '')
    
    if not all([usuario_red, nueva_password, confirmar_password]):
        flash('Todos los campos son obligatorios', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    if nueva_password != confirmar_password:
        flash('Las contraseñas no coinciden', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    # Validar longitud mínima
    if len(nueva_password) < 8:
        flash('La contraseña debe tener al menos 8 caracteres', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    connection = obtener_conexion()
    if not connection:
        flash('Error de conexión a la base de datos', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    try:
        cursor = connection.cursor()
        
        # Hashear la nueva contraseña
        password_hash = hash_password(nueva_password)
        
        # Actualizar contraseña
        query = """
            UPDATE SMARTSOC_USUARIOS
            SET PASSWORD = :password,
                FECHA_ULTIMA_MODIFICACION = SYSDATE
            WHERE USUARIO = :usuario
        """
        
        cursor.execute(query, {
            'password': password_hash,
            'usuario': usuario_red
        })
        
        connection.commit()
        cursor.close()
        connection.close()
        
        flash(f'✓ Contraseña de {usuario_red} cambiada correctamente', 'success')
        
    except Exception as e:
        print(f"Error cambiando contraseña: {e}")
        flash(f'Error al cambiar contraseña: {str(e)}', 'error')
        if connection:
            connection.close()
    
    return redirect(url_for('gestion_usuarios'))

# ============================================
# RUTA: AGREGAR USUARIO
# ============================================

@app.route('/agregar_usuario', methods=['POST'])
@login_requerido
@solo_admin
def agregar_usuario():
    """
    Agrega un nuevo usuario al sistema
    """
    # Obtener datos del formulario
    nombre = request.form.get('nombre')
    apellido = request.form.get('apellido')
    usuario_red = request.form.get('usuario_red')
    correo = request.form.get('correo')
    area = request.form.get('area')
    telefono = request.form.get('telefono')
    perfil = request.form.get('perfil')
    password = request.form.get('password')
    
    # Validar campos obligatorios
    if not all([nombre, apellido, usuario_red, correo, area, perfil, password]):
        flash('Todos los campos obligatorios deben estar completos', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    connection = obtener_conexion()
    if not connection:
        flash('Error de conexión a la base de datos', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    try:
        cursor = connection.cursor()
        
        # Verificar si el usuario ya existe
        cursor.execute(
            "SELECT COUNT(*) FROM SMARTSOC_USUARIOS WHERE USUARIO = :usuario",
            {'usuario': usuario_red}
        )
        if cursor.fetchone()[0] > 0:
            flash(f'El usuario {usuario_red} ya existe en el sistema', 'error')
            cursor.close()
            connection.close()
            return redirect(url_for('gestion_usuarios'))
        
        # Verificar si el correo ya existe
        cursor.execute(
            "SELECT COUNT(*) FROM SMARTSOC_USUARIOS WHERE CORREO = :correo",
            {'correo': correo}
        )
        if cursor.fetchone()[0] > 0:
            flash(f'El correo {correo} ya está registrado', 'error')
            cursor.close()
            connection.close()
            return redirect(url_for('gestion_usuarios'))
        
        # Obtener el siguiente ID
        cursor.execute("SELECT NVL(MAX(ID_USUARIO), 0) + 1 FROM SMARTSOC_USUARIOS")
        next_id = cursor.fetchone()[0]
        
        # Hashear la contraseña
        password_hash = hash_password(password)
        
        # Obtener usuario que está creando
        creado_por = session.get('USUARIO', 'admin')
        
        # Insertar nuevo usuario
        query = """
            INSERT INTO SMARTSOC_USUARIOS (
                ID_USUARIO,
                USUARIO,
                NOMBRE,
                APELLIDO,
                CORREO,
                PASSWORD,
                PERFIL,
                AREA,
                TELEFONO,
                ACTIVO,
                FECHA_CREACION,
                CREADO_POR
            ) VALUES (
                :id_usuario,
                :usuario,
                :nombre,
                :apellido,
                :correo,
                :password,
                :perfil,
                :area,
                :telefono,
                1,
                SYSDATE,
                :creado_por
            )
        """
        
        cursor.execute(query, {
            'id_usuario': next_id,
            'usuario': usuario_red,
            'nombre': nombre,
            'apellido': apellido,
            'correo': correo,
            'password': password_hash,
            'perfil': perfil,
            'area': area,
            'telefono': telefono,
            'creado_por': creado_por
        })
        
        connection.commit()
        cursor.close()
        connection.close()
        
        flash(f'✓ Usuario {usuario_red} creado correctamente', 'success')
        
    except Exception as e:
        print(f"Error creando usuario: {e}")
        flash(f'Error al crear usuario: {str(e)}', 'error')
        if connection:
            connection.close()
    
    return redirect(url_for('gestion_usuarios'))

@app.route('/ping_session', methods=['POST'])
@login_requerido
def ping_session():
    """Endpoint para mantener la sesión activa"""
    session.modified = True
    return {'status': 'ok'}, 200


@app.route('/check_session', methods=['GET'])
def check_session():
    """Verifica si la sesión está activa"""
    if 'USUARIO' in session:
        return {'active': True, 'user': session.get('USUARIO')}, 200
    else:
        return {'active': False}, 401

# ============================================
# RUTA: ELIMINAR USUARIO
# ============================================

@app.route('/eliminar_usuario', methods=['POST'])
@login_requerido
@solo_admin
def eliminar_usuario():
    usuario_red = request.form.get('usuario_red')
    
    if not usuario_red:
        flash('Usuario no especificado', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    if usuario_red == session.get('USUARIO'):
        flash('No puedes eliminar tu propio usuario', 'error')
        return redirect(url_for('gestion_usuarios'))
    
    try:
        connection = cx_Oracle.connect(
            user=DB_PTM_USER,
            password=DB_PTM_PASSWORD,
            dsn=DB_PTM_DSN,
            encoding='UTF-8'
        )
        cursor = connection.cursor()
        
        print(f"🔍 DEBUG - Verificando restricciones que bloquean el DELETE")
        
        # 1. Buscar todas las tablas que referencian a SMARTSOC_USUARIOS
        cursor.execute("""
            SELECT c.table_name, c.constraint_name, c.column_name, c.r_constraint_name
            FROM all_constraints c
            JOIN all_cons_columns cc ON c.constraint_name = cc.constraint_name
            WHERE c.r_constraint_name IN (
                SELECT constraint_name 
                FROM all_constraints 
                WHERE table_name = 'SMARTSOC_USUARIOS' 
                AND constraint_type = 'P'
            )
        """)
        
        restricciones = cursor.fetchall()
        print(f"🔍 DEBUG - Restricciones encontradas: {restricciones}")
        
        # 2. Verificar si hay registros que referencian al usuario
        for restriccion in restricciones:
            tabla = restriccion[0]
            columna = restriccion[2]
            try:
                query_check = f"SELECT COUNT(*) FROM {tabla} WHERE {columna} = :usuario"
                cursor.execute(query_check, {'usuario': usuario_red})
                count = cursor.fetchone()[0]
                print(f"🔍 DEBUG - Tabla {tabla}.{columna}: {count} registros")
            except Exception as e:
                print(f"⚠️ DEBUG - Error verificando {tabla}: {e}")
        
        # 3. Verificar locks activos
        cursor.execute("""
            SELECT s.sid, s.serial#, s.username, o.object_name, l.locked_mode
            FROM v$locked_object l, all_objects o, v$session s
            WHERE l.object_id = o.object_id
            AND l.session_id = s.sid
            AND o.object_name = 'SMARTSOC_USUARIOS'
        """)
        
        locks = cursor.fetchall()
        print(f"🔍 DEBUG - Locks activos en SMARTSOC_USUARIOS: {locks}")
        
        # 4. Intentar un DELETE simple para ver el error exacto
        print(f"🔍 DEBUG - Intentando DELETE directo...")
        cursor.execute("""
            DELETE FROM SMARTSOC_USUARIOS
            WHERE USUARIO = :usuario
        """, {'usuario': usuario_red})
        
        print(f"🔍 DEBUG - DELETE exitoso, filas eliminadas: {cursor.rowcount}")
        
        connection.commit()
        flash(f'✓ Usuario {usuario_red} eliminado correctamente', 'success')
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"❌ ERROR EXACTO: {str(e)}")
        flash(f'Error: {str(e)}', 'error')
        try:
            connection.rollback()
            cursor.close()
            connection.close()
        except:
            pass
    
    return redirect(url_for('gestion_usuarios'))
# ============================================
# FUNCIÓN ADICIONAL: ACTUALIZAR ÚLTIMO ACCESO
# ============================================

def actualizar_ultimo_acceso(usuario):
    """
    Actualiza la fecha de último acceso del usuario
    Llamar esta función después del login exitoso
    """
    connection = obtener_conexion()
    if not connection:
        return
    
    try:
        cursor = connection.cursor()
        
        query = """
            UPDATE SMARTSOC_USUARIOS
            SET ULTIMO_ACCESO = SYSDATE
            WHERE USUARIO = :usuario
        """
        
        cursor.execute(query, {'usuario': usuario})
        connection.commit()
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"Error actualizando último acceso: {e}")
        if connection:
            connection.close()

# ============================================
# FUNCIÓN ADICIONAL: VERIFICAR ESTADO DE SESIÓN 
# ============================================
@app.route('/api/info_sesion')
@login_requerido
def info_sesion():
    """
    Retorna información sobre la sesión actual del usuario
    """
    sesion_permanente = session.get('SESION_PERMANENTE', 0)
    
    return jsonify({
        'usuario': session.get('USUARIO'),
        'perfil': session.get('PERFIL'),
        'sesion_permanente': sesion_permanente,
        'tipo_sesion': 'Sin timeout' if sesion_permanente == 1 else 'Con timeout (30 minutos)',
        'fecha_ingreso': session.get('FECHA_HORA_INGRESO')
    })
# ============================================
# RUTAS PARA RECUPERACIÓN DE CONTRASEÑA (DESDE LOGIN)
# ============================================

@app.route('/recuperar_password', methods=['GET', 'POST'])
def recuperar_password():
    """
    Página para recuperar contraseña (accesible sin login)
    """
    if request.method == 'POST':
        usuario = request.form['usuario'].strip()
        
        if not usuario:
            flash('Por favor ingresa tu nombre de usuario', 'error')
            return render_template('recuperar_password.html')
        
        try:
            # Buscar usuario en la base de datos
            connection = cx_Oracle.connect(user=DB_PTM_USER, password=DB_PTM_PASSWORD, 
                                          dsn=DB_PTM_DSN, encoding='UTF-8')
            cursor = connection.cursor()
            
            cursor.execute("""
                SELECT USUARIO, NOMBRE, APELLIDO, CORREO, ACTIVO
                FROM SMARTSOC_USUARIOS
                WHERE USUARIO = :usuario
            """, {'usuario': usuario})
            
            user_data = cursor.fetchone()
            cursor.close()
            connection.close()
            
            if user_data:
                if user_data[4] == 0:  # Usuario inactivo
                    flash('Tu usuario está inactivo. Contacta al administrador.', 'error')
                    return render_template('recuperar_password.html')
                
                # Usuario encontrado, redirigir a restablecer contraseña
                return render_template('restablecer_password.html', usuario=usuario)
            else:
                flash('Usuario no encontrado. Verifica e intenta nuevamente.', 'error')
                return render_template('recuperar_password.html')
                
        except Exception as e:
            print(f"Error buscando usuario: {str(e)}")
            flash('Error al buscar el usuario. Intenta nuevamente.', 'error')
            return render_template('recuperar_password.html')
    else:
        return render_template('recuperar_password.html')


@app.route('/restablecer_password', methods=['POST'])
def restablecer_password():
    """
    Procesa el restablecimiento de contraseña (sin login requerido)
    Nombre diferente para no conflictuar con cambiar_password existente
    """
    usuario = request.form.get('usuario', '').strip()
    nueva_password = request.form.get('nueva_password', '').strip()
    confirmar_password = request.form.get('confirmar_password', '').strip()
    
    # Validaciones
    if not usuario or not nueva_password or not confirmar_password:
        flash('Todos los campos son obligatorios', 'error')
        return render_template('restablecer_password.html', usuario=usuario)
    
    if nueva_password != confirmar_password:
        flash('Las contraseñas no coinciden', 'error')
        return render_template('restablecer_password.html', usuario=usuario)
    
    if len(nueva_password) < 6:
        flash('La contraseña debe tener al menos 6 caracteres', 'error')
        return render_template('restablecer_password.html', usuario=usuario)
    
    try:
        # Actualizar contraseña en la base de datos
        connection = cx_Oracle.connect(user=DB_PTM_USER, password=DB_PTM_PASSWORD, 
                                          dsn=DB_PTM_DSN, encoding='UTF-8')
        cursor = connection.cursor()
        
        # Primero obtener datos del usuario para el correo
        cursor.execute("""
            SELECT NOMBRE, APELLIDO, CORREO
            FROM SMARTSOC_USUARIOS
            WHERE USUARIO = :usuario
        """, {'usuario': usuario})
        
        user_data = cursor.fetchone()
        
        if not user_data:
            flash('Usuario no encontrado', 'error')
            return render_template('restablecer_password.html', usuario=usuario)
        
        nombre, apellido, correo = user_data
        
        # Hashear la nueva contraseña
        password_hasheada = hash_password(nueva_password)
        
        # Actualizar la contraseña
        cursor.execute("""
            UPDATE SMARTSOC_USUARIOS
            SET PASSWORD = :password,
                FECHA_MODIFICACION = SYSDATE
            WHERE USUARIO = :usuario
        """, {
            'password': password_hasheada,
            'usuario': usuario
        })
        
        connection.commit()
        cursor.close()
        connection.close()
        
        # Registrar en auditoría
        registrar_auditoria(usuario, 'RECUPERACION_PASSWORD', 
                          'Restablecimiento de contraseña desde login')
        
        # Enviar correo de confirmación
        enviar_email_recuperacion_password(nombre, apellido, correo, usuario, nueva_password)
        
        # Mostrar página de éxito
        return render_template('password_restablecida.html', 
                             usuario=usuario, 
                             nueva_password=nueva_password)
        
    except Exception as e:
        print(f"Error restableciendo contraseña: {str(e)}")
        flash('Error al restablecer la contraseña. Intenta nuevamente.', 'error')
        return render_template('restablecer_password.html', usuario=usuario)


def enviar_email_recuperacion_password(nombre, apellido, correo, usuario, nueva_password):
    """
    Envía correo informando sobre el restablecimiento de contraseña
    Función con nombre diferente para no conflictuar
    """
    smtp_server = "10.80.19.186"
    smtp_port = 25
    sender_email = "centro.gestion.co.automatizacion@telefonica.com"
    
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = "✅ Restablecimiento de Contraseña Exitoso - SmartSOC"
        message["From"] = sender_email
        message["To"] = correo
        message["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S")
        
        url_sistema = "http://192.68.44.46:5051/login"  # CAMBIAR A TU URL REAL
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #28a745; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9f9f9; padding: 25px; border: 1px solid #ddd; }}
                .success-icon {{ font-size: 50px; text-align: center; margin: 20px 0; }}
                .credentials {{ background-color: #e8f5e9; padding: 20px; border-left: 4px solid #28a745; margin: 20px 0; }}
                .credentials h3 {{ margin-top: 0; color: #28a745; }}
                .password-box {{ background-color: #fff; padding: 15px; border: 2px dashed #28a745; margin: 10px 0; text-align: center; }}
                .password-text {{ font-size: 20px; font-weight: bold; color: #333; letter-spacing: 2px; }}
                .footer {{ background-color: #f0f0f0; padding: 15px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 5px 5px; }}
                .btn {{ display: inline-block; padding: 12px 30px; background-color: #0166ff; color: white; text-decoration: none; border-radius: 5px; margin-top: 15px; }}
                .warning {{ background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 20px 0; }}
                .info-box {{ background-color: #e7f3ff; padding: 15px; border-left: 4px solid #0166ff; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>✅ Restablecimiento de Contraseña Exitoso</h1>
                </div>
                <div class="content">
                    <div class="success-icon">🎉</div>
                    
                    <p>Hola <strong>{nombre} {apellido}</strong>,</p>
                    
                    <p>Te confirmamos que tu contraseña para acceder al sistema <strong>SmartSOC</strong> ha sido restablecida exitosamente.</p>
                    
                    <div class="info-box">
                        <p><strong>📅 Fecha del cambio:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                        <p><strong>👤 Usuario:</strong> {usuario}</p>
                    </div>
                    
                    <div class="credentials">
                        <h3>🔑 Tu nueva contraseña es:</h3>
                        <div class="password-box">
                            <div class="password-text">{nueva_password}</div>
                        </div>
                        <p style="font-size: 12px; color: #666; margin-top: 10px;">
                            <em>Por favor guarda esta contraseña en un lugar seguro</em>
                        </p>
                    </div>
                    
                    <div class="warning">
                        <p><strong>⚠️ Recomendaciones de seguridad:</strong></p>
                        <ul>
                            <li>No compartas tu contraseña con nadie</li>
                            <li>Cierra sesión al terminar de usar el sistema</li>
                            <li>Si no solicitaste este cambio, contacta inmediatamente al administrador</li>
                        </ul>
                    </div>
                    
                    <p style="text-align: center;">
                        <a href="{url_sistema}" class="btn">Iniciar Sesión Ahora</a>
                    </p>
                    
                    <p style="margin-top: 25px; font-size: 13px; color: #666; border-top: 1px solid #ddd; padding-top: 15px;">
                        <strong>🔒 Nota de seguridad:</strong><br>
                        Si NO realizaste este cambio de contraseña, por favor contacta de inmediato al administrador del sistema.
                    </p>
                </div>
                <div class="footer">
                    <p>SmartSOC - Jefatura Centro de Gestión © 2024</p>
                    <p style="margin-top: 5px; font-size: 11px;">
                        Este es un correo automático, por favor no respondas a este mensaje
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        part = MIMEText(html, "html")
        message.attach(part)
        
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.sendmail(sender_email, correo, message.as_string())
        server.quit()
        
        print(f"✓ Correo de restablecimiento enviado a {correo}")
        return True
        
    except Exception as e:
        print(f"✗ Error enviando correo de restablecimiento: {str(e)}")
        return False

# ============================================
# FUNCIONES AUXILIARES LOGIN Y GESTION DE USUARIOS
# ============================================

def registrar_auditoria(usuario, accion, detalles=''):
    """Registra acciones en auditoría"""
    try:
        connection = cx_Oracle.connect(user=DB_PTM_USER, password=DB_PTM_PASSWORD, 
                                          dsn=DB_PTM_DSN, encoding='UTF-8')
        cursor = connection.cursor()
        
        cursor.execute("""
            INSERT INTO SMARTSOC_AUDITORIA_ACCESOS (
                ID_ACCESO, USUARIO, PAGINA, ACCION, IP_ADDRESS, DETALLES
            ) VALUES (
                SMARTSOC_SEQ_AUDITORIA.NEXTVAL, :usuario, :pagina, :accion, :ip, :detalles
            )
        """, {
            'usuario': usuario,
            'pagina': request.path,
            'accion': accion,
            'ip': request.remote_addr,
            'detalles': detalles
        })
        
        connection.commit()
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"Error registrando auditoría: {str(e)}")


def enviar_email_aprobacion(nombre, apellido, correo, usuario, password, perfil):
    """Envía correo de aprobación al usuario"""
    smtp_server = "10.80.19.186"
    smtp_port = 25
    sender_email = "centro.gestion.co.automatizacion@telefonica.com"
    
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = "¡Tu solicitud de acceso a SmartSOC ha sido aprobada!"
        message["From"] = sender_email
        message["To"] = correo
        message["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S")
        
        url_sistema = "http://192.168.44.46:5051/login"  # CAMBIAR A TU URL REAL
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #28a745; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9f9f9; padding: 20px; border: 1px solid #ddd; }}
                .credentials {{ background-color: #e8f5e9; padding: 15px; border-left: 4px solid #28a745; margin: 20px 0; }}
                .footer {{ background-color: #f0f0f0; padding: 15px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 5px 5px; }}
                .btn {{ display: inline-block; padding: 12px 30px; background-color: #0166ff; color: white; text-decoration: none; border-radius: 5px; margin-top: 15px; }}
                .warning {{ background-color: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; margin: 15px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>¡Solicitud Aprobada!</h1>
                </div>
                <div class="content">
                    <p>Hola <strong>{nombre} {apellido}</strong>,</p>
                    <p>¡Excelentes noticias! Tu solicitud de acceso al sistema <strong>SmartSOC</strong> ha sido <strong>APROBADA</strong>.</p>
                    
                    <div class="credentials">
                        <h3 style="margin-top: 0; color: #28a745;">📋 Tus credenciales de acceso:</h3>
                        <p><strong>Usuario:</strong> {usuario}</p>
                        <p><strong>Contraseña:</strong> {password}</p>
                        <p><strong>Perfil asignado:</strong> {perfil}</p>
                    </div>
                    
                    <div class="warning">
                        <p><strong>⚠️ Recomendaciones de seguridad:</strong></p>
                        <ul>
                            <li>No compartas tus credenciales con nadie</li>
                            <li>Cierra sesión al terminar de usar el sistema</li>
                            <li>Mantén tu contraseña segura</li>
                        </ul>
                    </div>
                    
                    <p style="text-align: center;">
                        <a href="{url_sistema}" class="btn">Iniciar Sesión Ahora</a>
                    </p>
                    
                    <p style="margin-top: 20px; font-size: 14px; color: #666;">
                        Si tienes alguna pregunta o problema para acceder, contacta al administrador.
                    </p>
                </div>
                <div class="footer">
                    <p>SmartSOC - Jefatura Centro de Gestión © 2024</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        part = MIMEText(html, "html")
        message.attach(part)
        
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.sendmail(sender_email, correo, message.as_string())
        server.quit()
        
        print(f"✓ Correo de aprobación enviado a {correo}")
        return True
        
    except Exception as e:
        print(f"✗ Error enviando correo de aprobación: {str(e)}")
        return False


def enviar_email_rechazo(nombre, apellido, correo, motivo):
    """Envía correo de rechazo al usuario"""
    smtp_server = "10.80.19.186"
    smtp_port = 25
    sender_email = "centro.gestion.co.automatizacion@telefonica.com"
    
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = "Actualización sobre tu solicitud de acceso a SmartSOC"
        message["From"] = sender_email
        message["To"] = correo
        message["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S")
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #dc3545; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9f9f9; padding: 20px; border: 1px solid #ddd; }}
                .motivo {{ background-color: #f8d7da; padding: 15px; border-left: 4px solid #dc3545; margin: 20px 0; }}
                .footer {{ background-color: #f0f0f0; padding: 15px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 5px 5px; }}
                .contact {{ background-color: #e7f3ff; padding: 10px; border-left: 4px solid #0166ff; margin: 15px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Actualización de Solicitud</h1>
                </div>
                <div class="content">
                    <p>Hola <strong>{nombre} {apellido}</strong>,</p>
                    <p>Lamentamos informarte que tu solicitud de acceso al sistema <strong>SmartSOC</strong> no ha sido aprobada.</p>
                    
                    <div class="motivo">
                        <h3 style="margin-top: 0; color: #dc3545;">📋 Motivo del rechazo:</h3>
                        <p>{motivo}</p>
                    </div>
                    
                    <div class="contact">
                        <p><strong>📞 ¿Tienes preguntas?</strong></p>
                        <p>Si deseas más información o crees que ha habido un error, contacta al administrador.</p>
                        <p><strong>Contacto:</strong> edgar.acevedo@telefonica.com</p>
                    </div>
                    
                    <p style="margin-top: 20px;">Gracias por tu interés en el sistema SmartSOC.</p>
                </div>
                <div class="footer">
                    <p>SmartSOC - Jefatura Centro de Gestión © 2024</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        part = MIMEText(html, "html")
        message.attach(part)
        
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.sendmail(sender_email, correo, message.as_string())
        server.quit()
        
        print(f"✓ Correo de rechazo enviado a {correo}")
        return True
        
    except Exception as e:
        print(f"✗ Error enviando correo de rechazo: {str(e)}")
        return False

def hash_password(password):
    """Hashea la contraseña usando SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def obtener_conexion():
    """Obtiene una conexión a la base de datos"""
    try:
        connection = cx_Oracle.connect(
            user=config.ORACLE_USER,
            password=config.ORACLE_PASSWORD,
            dsn=config.ORACLE_DSN
        )
        return connection
    except Exception as e:
        print(f"Error conectando a la base de datos: {e}")
        return None

# ============================================
# API: OBTENER FALLAS ACTIVAS (TU QUERY REAL)
# ============================================
@app.route('/api/fallas-activas')
@login_requerido
@permiso_requerido('servicio_al_cliente')
def api_fallas_activas():
    """
    Endpoint para obtener todas las fallas activas desde tu tabla real
    dsautom1.crc_api_anexo2_hist_h
    """
    connection = None
    cursor = None
    
    try:
        print("🔄 Iniciando consulta de fallas activas...")
        
        connection = cx_Oracle.connect(
            user=ORACLE_USER,
            password=ORACLE_PASSWORD,
            dsn=ORACLE_DSN,
            encoding='UTF-8',      # ⭐ AGREGAR
            nencoding='UTF-8'
        )
        cursor = connection.cursor()
        
        print("✅ Conexión a Oracle establecida")
        
        # Query actualizado con usuarios y tiempo de afectación
        query = """
            SELECT DISTINCT
                SUBSTR(API.TICKET, 1, 7) AS TICKET,
                API.ESTACIONBASE_MAXIMO,
                API.ESTADOEB,
                API.INICIOFALLA,
                API.TECNOLOGIA,
                API.MUNICIPIO,
                API.DEPARTAMENTO,
                SECTORES.LATITUD,
                SECTORES.LONGITUD,
                SECTORES.SIT_LOCATION,
                SECTORES.SIT_DESCRIPTION,
                API.FECHA_INSERT_HIST,
                COALESCE(USU.TOTAL_USUARIOS, 0) AS TOTAL_USUARIOS,
                ROUND((SYSDATE - API.INICIOFALLA) * 24, 2) AS TIEMPO_AFECT_HRS
            FROM
                dsautom1.crc_api_anexo2_hist_h API
            LEFT OUTER JOIN 
                dsautom1.sectores_maximo_v2 SECTORES
                ON API.ESTACIONBASE_MAXIMO = SECTORES.ESTACIONBASE
            LEFT OUTER JOIN (
                SELECT ESTACIONBASE, SUM(USUARIOS) AS TOTAL_USUARIOS
                FROM dsautom1.sectores_maximo_v2
                GROUP BY ESTACIONBASE
            ) USU ON API.ESTACIONBASE_MAXIMO = USU.ESTACIONBASE
            WHERE
                API.ESTADOEB = 'Indisponible'
                AND API.FECHA_INSERT_HIST = (
                    SELECT MAX(FECHA_INSERT_HIST)
                    FROM dsautom1.crc_api_anexo2_hist_h
                    WHERE ESTADOEB = 'Indisponible'
                )
                AND SECTORES.LATITUD IS NOT NULL
                AND SECTORES.LONGITUD IS NOT NULL
            ORDER BY API.INICIOFALLA DESC
        """
        
        print("🔍 Ejecutando query principal...")
        cursor.execute(query)
        
        print("📊 Obteniendo resultados...")
        resultados = cursor.fetchall()
        
        print(f"✅ Query completado. Registros encontrados: {len(resultados)}")
        
        # Calcular hora de última actualización (hora actual redondeada a :00)
        from datetime import datetime
        ahora = datetime.now()
        hora_actualizacion = ahora.replace(minute=0, second=0, microsecond=0)
        fecha_ultima_carga_str = hora_actualizacion.strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"📅 Hora de actualización (hora en punto): {fecha_ultima_carga_str}")
        
        # Formatear resultados
        fallas = []
        coords_invalidas = 0
        total_usuarios_afectados = 0
        
        for idx, row in enumerate(resultados):
            try:
                # Validar coordenadas
                latitud = float(row[7]) if row[7] else None
                longitud = float(row[8]) if row[8] else None
                
                if latitud and longitud:
                    # Validar rango Colombia: Lat: -4.5 a 13, Lon: -80 a -66
                    if -4.5 <= latitud <= 13.5 and -82 <= longitud <= -66:
                        usuarios = int(row[12]) if row[12] else 0
                        tiempo_afectacion = float(row[13]) if row[13] else 0
                        
                        total_usuarios_afectados += usuarios
                        
                        fallas.append({
                            'ticket': str(row[0]) if row[0] else 'N/A',
                            'estacion_base': str(row[1]) if row[1] else 'N/A',
                            'estado': str(row[2]) if row[2] else 'Indisponible',
                            'fecha_inicio': row[3].strftime('%Y-%m-%dT%H:%M:%S') if row[3] else None,
                            'tecnologia': str(row[4]) if row[4] else 'N/A',
                            'municipio': str(row[5]) if row[5] else 'N/A',
                            'departamento': str(row[6]) if row[6] else 'N/A',
                            'latitud': latitud,
                            'longitud': longitud,
                            'location': str(row[9]) if row[9] else '',
                            'description': str(row[10]) if row[10] else '',
                            'fecha_insert': row[11].strftime('%Y-%m-%dT%H:%M:%S') if row[11] else None,
                            'usuarios_afectados': usuarios,
                            'tiempo_afectacion_hrs': tiempo_afectacion
                        })
                    else:
                        coords_invalidas += 1
                        
            except Exception as e:
                print(f"⚠️ Error procesando fila {idx}: {e}")
                continue
        
        if cursor:
            cursor.close()
        if connection:
            connection.close()
        
        print(f"✅ Procesamiento completado:")
        print(f"   - Total registros: {len(resultados)}")
        print(f"   - Fallas válidas: {len(fallas)}")
        print(f"   - Coords inválidas: {coords_invalidas}")
        print(f"   - Usuarios afectados: {total_usuarios_afectados:,}")
        
        return jsonify({
            'success': True,
            'fallas': fallas,
            'total': len(fallas),
            'total_sin_filtrar': len(resultados),
            'fecha_ultima_carga': fecha_ultima_carga_str,
            'total_usuarios_afectados': total_usuarios_afectados
        })
        
    except Exception as e:
        print(f"❌ ERROR en api_fallas_activas:")
        print(f"   Tipo: {type(e).__name__}")
        print(f"   Mensaje: {str(e)}")
        
        import traceback
        print("📋 Traceback completo:")
        traceback.print_exc()
        
        # Cerrar conexiones si están abiertas
        try:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
        except:
            pass
        
        return jsonify({
            'success': False,
            'error': str(e),
            'fallas': [],
            'fecha_ultima_carga': None,
            'total_usuarios_afectados': 0
        }), 500


# ============================================
# API: OBTENER ESTADÍSTICAS DE FALLAS
# ============================================
@app.route('/api/estadisticas-fallas')
@login_requerido
@permiso_requerido('servicio_al_cliente')
def api_estadisticas_fallas():
    """
    Estadísticas generales de las fallas activas
    """
    try:
        connection = cx_Oracle.connect(
            user=ORACLE_USER,
            password=ORACLE_PASSWORD,
            dsn=ORACLE_DSN,
            encoding='UTF-8',      # ⭐ AGREGAR
            nencoding='UTF-8'
        )
        cursor = connection.cursor()
        
        # Total de fallas por tecnología
        cursor.execute("""
            SELECT 
                API.TECNOLOGIA, 
                COUNT(*) as TOTAL
            FROM dsautom1.crc_api_anexo2_hist_h API
            WHERE API.ESTADOEB = 'Indisponible'
            AND API.FECHA_INSERT_HIST = (
                SELECT MAX(FECHA_INSERT_HIST)
                FROM dsautom1.crc_api_anexo2_hist_h
                WHERE ESTADOEB = 'Indisponible'
            )
            GROUP BY API.TECNOLOGIA
            ORDER BY TOTAL DESC
        """)
        
        fallas_por_tecnologia = {}
        for row in cursor.fetchall():
            fallas_por_tecnologia[row[0]] = row[1]
        
        # Total de fallas por departamento
        cursor.execute("""
            SELECT 
                API.DEPARTAMENTO, 
                COUNT(*) as TOTAL
            FROM dsautom1.crc_api_anexo2_hist_h API
            WHERE API.ESTADOEB = 'Indisponible'
            AND API.FECHA_INSERT_HIST = (
                SELECT MAX(FECHA_INSERT_HIST)
                FROM dsautom1.crc_api_anexo2_hist_h
                WHERE ESTADOEB = 'Indisponible'
            )
            GROUP BY API.DEPARTAMENTO
            ORDER BY TOTAL DESC
        """)
        
        fallas_por_departamento = {}
        for row in cursor.fetchall():
            fallas_por_departamento[row[0]] = row[1]
        
        # Total general de fallas
        cursor.execute("""
            SELECT COUNT(*) 
            FROM dsautom1.crc_api_anexo2_hist_h API
            WHERE API.ESTADOEB = 'Indisponible'
            AND API.FECHA_INSERT_HIST = (
                SELECT MAX(FECHA_INSERT_HIST)
                FROM dsautom1.crc_api_anexo2_hist_h
                WHERE ESTADOEB = 'Indisponible'
            )
        """)
        
        total_fallas = cursor.fetchone()[0]
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'estadisticas': {
                'total_fallas': total_fallas,
                'fallas_por_tecnologia': fallas_por_tecnologia,
                'fallas_por_departamento': fallas_por_departamento
            }
        })
        
    except Exception as e:
        print(f"❌ Error obteniendo estadísticas: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# API: DETALLE DE FALLA POR TICKET
# ============================================
@app.route('/api/falla/<ticket>')
@login_requerido
@permiso_requerido('servicio_al_cliente')
def api_detalle_falla(ticket):
    """
    Obtener información detallada de una falla específica
    """
    try:
        connection = cx_Oracle.connect(
            user=ORACLE_USER,
            password=ORACLE_PASSWORD,
            dsn=ORACLE_DSN,
            encoding='UTF-8',      # ⭐ AGREGAR
            nencoding='UTF-8'
        )
        cursor = connection.cursor()
        
        query = """
            SELECT DISTINCT
                API.TICKET,
                API.ESTACIONBASE_MAXIMO,
                API.ESTADOEB,
                API.INICIOFALLA,
                API.TECNOLOGIA,
                API.MUNICIPIO,
                API.DEPARTAMENTO,
                SECTORES.LATITUD,
                SECTORES.LONGITUD,
                SECTORES.SIT_LOCATION,
                SECTORES.SIT_DESCRIPTION,
                API.FECHA_INSERT_HIST
            FROM
                dsautom1.crc_api_anexo2_hist_h API
            LEFT OUTER JOIN 
                dsautom1.sectores_maximo_v2 SECTORES
                ON API.ESTACIONBASE_MAXIMO = SECTORES.ESTACIONBASE
            WHERE
                API.TICKET = :ticket
                AND API.ESTADOEB = 'Indisponible'
                AND API.FECHA_INSERT_HIST = (
                    SELECT MAX(FECHA_INSERT_HIST)
                    FROM dsautom1.crc_api_anexo2_hist_h
                    WHERE ESTADOEB = 'Indisponible'
                )
        """
        
        cursor.execute(query, {'ticket': ticket})
        resultado = cursor.fetchone()
        
        if resultado:
            falla = {
                'ticket': str(resultado[0]),
                'estacion_base': str(resultado[1]),
                'estado': str(resultado[2]),
                'fecha_inicio': resultado[3].isoformat() if resultado[3] else None,
                'tecnologia': str(resultado[4]),
                'municipio': str(resultado[5]),
                'departamento': str(resultado[6]),
                'latitud': float(resultado[7]) if resultado[7] else None,
                'longitud': float(resultado[8]) if resultado[8] else None,
                'location': str(resultado[9]) if resultado[9] else '',
                'description': str(resultado[10]) if resultado[10] else '',
                'fecha_insert': resultado[11].isoformat() if resultado[11] else None
            }
            
            cursor.close()
            connection.close()
            
            return jsonify({
                'success': True,
                'falla': falla
            })
        else:
            cursor.close()
            connection.close()
            
            return jsonify({
                'success': False,
                'error': 'Falla no encontrada'
            }), 404
            
    except Exception as e:
        print(f"❌ Error obteniendo detalle de falla: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================
# API: OBTENER MANTENIMIENTOS ACTIVOS
# ============================================
@app.route('/api/mantenimientos-activos')
@login_requerido
@permiso_requerido('servicio_al_cliente')
def api_mantenimientos_activos():
    """
    Endpoint para obtener todos los mantenimientos activos (BTP)
    desde la base de datos Maximo
    """
    connection = None
    cursor = None
    
    try:
        print("📄 Iniciando consulta de mantenimientos activos...")
        connection = cx_Oracle.connect(user=DB_MAXIMO_USER, password=DB_MAXIMO_PASSWORD, dsn=DB_MAXIMO_DSN, encoding= 'UTF-8')
        cursor = connection.cursor()
        
        print("✅ Conexión a Oracle establecida")
        
        # Query de mantenimientos activos
        query = """
            WITH 
            -- 🔹 PASO 1: Obtener todas las incidencias (Query 1)
            INCIDENCIAS AS (
                SELECT
                    TO_CHAR(I.AFFECTEDSTART, 'YYYY') AÑO,
                    TO_CHAR(I.AFFECTEDSTART, 'MM') MES,
                    TO_CHAR(I.AFFECTEDSTART, 'DD') DIA,
                    I.TICKETID INCIDENTE,
                    I.DESCRIPTION RESUMEN,
                    TO_CHAR(I.AFFECTEDSTART,'DD/MM/YYYY HH24:MI:SS') AS FECHA_INICIO_AFECTACION,
                    TO_CHAR(I.AFFECTEDFINISH,'DD/MM/YYYY HH24:MI:SS') AS FECHA_FIN_AFECTACION,
                    I.STATUS ESTADO,
                    CI.CINUM NE_AFEC,
                    CASE 
                        WHEN CI.CLASSSTRUCTUREID IN ('1770','1409') THEN '3G'
                        WHEN CI.CLASSSTRUCTUREID IN ('3493','3494','3551','3549') THEN '4G'
                        WHEN CI.CLASSSTRUCTUREID IN ('6473','6474') THEN '5G'
                    END AS TECNOLOGIA_NE_AFEC,
                    CASE 
                        WHEN CI.CLASSSTRUCTUREID IN ('1770','3493','3551','6473') THEN 'SECTOR'
                        WHEN CI.CLASSSTRUCTUREID IN ('1409','3494','3549','6474') THEN 'ESTACION'
                    END AS TIPO_NE,
                    L.SIT_DESCRIPTION NOMBRE_NE_AFEC,
                    L.SIT_LOCATION COD_NE_AFEC,
                    L.LATITUD LATITUD,
                    L.LONGITUD LONGITUD,
                    L.DEPTO_DESCRIPTION DEPARTAMENTO,
                    L.MUN_DESCRIPTION MUNICIPIO,
                    SUBSTR(I.BLOCK, 6) BTP,
                    TO_CHAR(WO.SCHEDSTART,'DD/MM/YYYY HH24:MI') AS FECHA_INICIO_PROGRAMADO,
                    TO_CHAR(WO.SCHEDFINISH,'DD/MM/YYYY HH24:MI') FECHA_FIN_PROGRAMADO,
                    WO.OWNERGROUP AS GRUPO_EJECUTOR,
                    WO.DESCRIPTION AS DESCRIPTION_OT,
                    L.SIT_LOCATION || '_' ||
                    CASE 
                        WHEN CI.CLASSSTRUCTUREID IN ('1770','1409') THEN '3G'
                        WHEN CI.CLASSSTRUCTUREID IN ('3493','3494','3551','3549') THEN '4G'
                        WHEN CI.CLASSSTRUCTUREID IN ('6473','6474') THEN '5G'
                    END AS LLAVE_NE_AFEC,
                    I.AFFECTEDSTART
                FROM
                    MAXIMO.INCIDENT I
                LEFT OUTER JOIN MAXIMO.RELATEDRECORD RR 
                    ON RR.RELATEDRECKEY = I.TICKETID 
                   AND RR.RELATEDRECCLASS = 'INCIDENT'
                LEFT OUTER JOIN MAXIMO.WORKORDER W 
                    ON W.WONUM = RR.RECORDKEY 
                   AND W.STATUS NOT IN ('CAN','CANCEL')
                LEFT OUTER JOIN MAXIMO.MULTIASSETLOCCI AFE 
                    ON I.TICKETID = AFE.RECORDKEY 
                   AND AFE.ISPRIMARY <> '1' 
                   AND AFE.RECORDCLASS LIKE 'INCIDENT' 
                   AND AFE.CINUM IS NOT NULL
                LEFT OUTER JOIN MAXIMO.CI CI 
                    ON CI.CINUM = AFE.CINUM
                LEFT OUTER JOIN MAXIMO.LOCATION_VIEW L 
                    ON CI.CILOCATION = L.SIT_LOCATION
                LEFT OUTER JOIN MAXIMO.WOACTIVITY WO 
                    ON WO.WONUM = SUBSTR(I.BLOCK, 6)
                WHERE
                    I.EXTERNALSYSTEM IN ('ROSE')
                    AND I.DESCRIPTION_CLASS IN ('FALLAS \ ALARMA INTERNA')
                    AND I.STATUS = 'QUEUED'
                    AND I.DESCRIPTION LIKE 'Falla persistencia%'
                    AND WO.SCHEDSTART < SYSDATE
                    AND WO.SCHEDFINISH > SYSDATE
            ),
            
            -- 🔹 PASO 2: Obtener configuración de sectores por estación
            SECTORES AS (
                SELECT 
                    CI.CILOCATION AS UBICACION,
                    CASE 
                        WHEN CI.CLASSSTRUCTUREID = '1770' THEN '3G'
                        WHEN CI.CLASSSTRUCTUREID IN ('3493', '3551') THEN '4G'
                        WHEN CI.CLASSSTRUCTUREID = '6473' THEN '5G'
                    END AS TECNOLOGIA,
                    CI.CINUM,
                    CASE 
                        WHEN REGEXP_LIKE(CI_U.ALNVALUE, '^[0-9]+(\.[0-9]+)?$') 
                        THEN TO_NUMBER(CI_U.ALNVALUE)
                        ELSE 0
                    END AS USUARIOS
                FROM MAXIMO.CI CI
                LEFT JOIN MAXIMO.CISPEC CI_U 
                    ON CI_U.CINUM = CI.CINUM 
                   AND CI_U.ASSETATTRID = 'USUARIOS'
                WHERE CI.STATUS IN ('OPERATING', 'DEVELOPMENT')
                  AND CI.CLASSSTRUCTUREID IN ('1770', '3493', '3551', '6473')
            ),
            
            ESTACIONES_BASE AS (
                SELECT 
                    CILOCATION AS UBICACION,
                    CASE 
                        WHEN CLASSSTRUCTUREID = '1409' THEN '3G'
                        WHEN CLASSSTRUCTUREID IN ('3494','3549') THEN '4G'
                        WHEN CLASSSTRUCTUREID = '6474' THEN '5G'
                    END AS TECNOLOGIA,
                    MAX(CINUM) AS ESTACIONBASE
                FROM MAXIMO.CI
                WHERE STATUS IN ('OPERATING', 'DEVELOPMENT')
                  AND CLASSSTRUCTUREID IN ('1409','3494','3549','6474')
                GROUP BY CILOCATION,
                         CASE 
                            WHEN CLASSSTRUCTUREID = '1409' THEN '3G'
                            WHEN CLASSSTRUCTUREID IN ('3494','3549') THEN '4G'
                            WHEN CLASSSTRUCTUREID = '6474' THEN '5G'
                         END
            ),
            
            CONFIG_ESTACIONES AS (
                SELECT 
                    S.UBICACION,
                    S.TECNOLOGIA,
                    E.ESTACIONBASE,
                    L.SIT_DESCRIPTION as NOMBRE_ESTACION,
                    L.LATITUD,
                    L.LONGITUD,
                    L.DEPTO_DESCRIPTION as DEPARTAMENTO_ESTACION,
                    L.MUN_DESCRIPTION as MUNICIPIO_ESTACION,
                    COUNT(DISTINCT S.CINUM) AS TOTAL_SECTORES,
                    SUM(S.USUARIOS) AS TOTAL_USUARIOS,
                    S.UBICACION || '_' || S.TECNOLOGIA AS LLAVE
                FROM SECTORES S
                LEFT JOIN ESTACIONES_BASE E
                    ON S.UBICACION = E.UBICACION
                   AND S.TECNOLOGIA = E.TECNOLOGIA
                LEFT JOIN MAXIMO.LOCATION_VIEW L
                    ON S.UBICACION = L.SIT_LOCATION
                GROUP BY 
                    S.UBICACION, S.TECNOLOGIA, E.ESTACIONBASE,
                    L.SIT_DESCRIPTION, L.LATITUD, L.LONGITUD,
                    L.DEPTO_DESCRIPTION, L.MUN_DESCRIPTION
            ),
            
            -- 🔹 PASO 3: Contar sectores caídos por estación
            SECTORES_CAIDOS AS (
                SELECT 
                    COD_NE_AFEC,
                    TECNOLOGIA_NE_AFEC,
                    LLAVE_NE_AFEC,
                    COUNT(DISTINCT NE_AFEC) AS SECTORES_AFECTADOS
                FROM INCIDENCIAS
                WHERE TIPO_NE = 'SECTOR'
                GROUP BY COD_NE_AFEC, TECNOLOGIA_NE_AFEC, LLAVE_NE_AFEC
            ),
            
            -- 🔹 PASO 4: Validar estaciones completamente caídas
            ESTACIONES_COMPLETAS AS (
                SELECT 
                    SC.LLAVE_NE_AFEC,
                    CE.UBICACION,
                    CE.ESTACIONBASE,
                    CE.NOMBRE_ESTACION,
                    CE.LATITUD,
                    CE.LONGITUD,
                    CE.DEPARTAMENTO_ESTACION,
                    CE.MUNICIPIO_ESTACION,
                    CE.TOTAL_USUARIOS,
                    SC.SECTORES_AFECTADOS,
                    CE.TOTAL_SECTORES
                FROM SECTORES_CAIDOS SC
                INNER JOIN CONFIG_ESTACIONES CE
                    ON SC.LLAVE_NE_AFEC = CE.LLAVE
                WHERE SC.SECTORES_AFECTADOS = CE.TOTAL_SECTORES
            )
            
            -- 🔹 PASO 5: Resultado final consolidado
            SELECT DISTINCT
                I.INCIDENTE,
                I.BTP,
                CASE 
                    WHEN I.TIPO_NE = 'ESTACION' THEN I.NE_AFEC
                    ELSE EC.ESTACIONBASE
                END AS ESTACION_BASE,
                CASE 
                    WHEN I.TIPO_NE = 'ESTACION' THEN I.COD_NE_AFEC
                    ELSE EC.UBICACION
                END AS UBICACION,
                CASE 
                    WHEN I.TIPO_NE = 'ESTACION' THEN I.NOMBRE_NE_AFEC
                    ELSE EC.NOMBRE_ESTACION
                END AS NOMBRE_SITIO,
                I.FECHA_INICIO_AFECTACION,
                CASE 
                    WHEN I.TIPO_NE = 'ESTACION' THEN I.MUNICIPIO
                    ELSE EC.MUNICIPIO_ESTACION
                END AS MUNICIPIO,
                CASE 
                    WHEN I.TIPO_NE = 'ESTACION' THEN I.DEPARTAMENTO
                    ELSE EC.DEPARTAMENTO_ESTACION
                END AS DEPARTAMENTO,
                CASE 
                    WHEN I.TIPO_NE = 'ESTACION' THEN I.LATITUD
                    ELSE EC.LATITUD
                END AS LATITUD,
                CASE 
                    WHEN I.TIPO_NE = 'ESTACION' THEN I.LONGITUD
                    ELSE EC.LONGITUD
                END AS LONGITUD,
                I.TECNOLOGIA_NE_AFEC AS TECNOLOGIA,
                CASE 
                    WHEN I.TIPO_NE = 'ESTACION' THEN 0
                    ELSE NVL(EC.TOTAL_USUARIOS, 0)
                END AS USUARIOS_AFECTADOS,
                ROUND((SYSDATE - I.AFFECTEDSTART) * 24, 2) AS TIEMPO_AFECTACION_HORAS,
                I.FECHA_INICIO_PROGRAMADO,
                I.FECHA_FIN_PROGRAMADO,
                I.GRUPO_EJECUTOR,
                I.DESCRIPTION_OT,
                I.AFFECTEDSTART
            FROM INCIDENCIAS I
            LEFT JOIN ESTACIONES_COMPLETAS EC
                ON I.LLAVE_NE_AFEC = EC.LLAVE_NE_AFEC
                AND I.TIPO_NE = 'SECTOR'
            WHERE 
                I.TIPO_NE = 'ESTACION'
                OR
                (I.TIPO_NE = 'SECTOR' AND EC.LLAVE_NE_AFEC IS NOT NULL)
            ORDER BY I.INCIDENTE DESC
        """
        
        print("🔍 Ejecutando query de mantenimientos...")
        cursor.execute(query)
        
        print("📊 Obteniendo resultados...")
        resultados = cursor.fetchall()
        
        print(f"✅ Query completado. Registros encontrados: {len(resultados)}")
        
        # Hora de última actualización (hora actual redondeada)
        from datetime import datetime
        ahora = datetime.now()
        hora_actualizacion = ahora.replace(minute=0, second=0, microsecond=0)
        fecha_ultima_carga_str = hora_actualizacion.strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"📅 Hora de actualización: {fecha_ultima_carga_str}")
        
        # Formatear resultados
        mantenimientos = []
        coords_invalidas = 0
        total_usuarios_afectados = 0
        
        for idx, row in enumerate(resultados):
            try:
                # Validar coordenadas
                latitud = float(row[8]) if row[8] else None
                longitud = float(row[9]) if row[9] else None
                
                if latitud and longitud:
                    # Validar rango Colombia: Lat: -4.5 a 13, Lon: -80 a -66
                    if -4.5 <= latitud <= 13.5 and -82 <= longitud <= -66:
                        usuarios = int(row[11]) if row[11] else 0
                        tiempo_afectacion = float(row[12]) if row[12] else 0
                        
                        total_usuarios_afectados += usuarios
                        
                        # Parsear fechas
                        def parse_fecha(fecha_str):
                            if not fecha_str:
                                return None
                            try:
                                # Formato: DD/MM/YYYY HH24:MI:SS o DD/MM/YYYY HH24:MI
                                if len(fecha_str) == 19:  # con segundos
                                    return datetime.strptime(fecha_str, '%d/%m/%Y %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S')
                                elif len(fecha_str) == 16:  # sin segundos
                                    return datetime.strptime(fecha_str, '%d/%m/%Y %H:%M').strftime('%Y-%m-%dT%H:%M:%S')
                            except:
                                return fecha_str
                            return None
                        
                        mantenimientos.append({
                            'incidente': str(row[0]) if row[0] else 'N/A',
                            'ticket': str(row[1]) if row[1] else 'N/A',  # BTP
                            'estacion_base': str(row[2]) if row[2] else 'N/A',
                            'ubicacion': str(row[3]) if row[3] else 'N/A',
                            'nombre_sitio': str(row[4]) if row[4] else 'N/A',
                            'fecha_inicio': parse_fecha(str(row[5])) if row[5] else None,
                            'municipio': str(row[6]) if row[6] else 'N/A',
                            'departamento': str(row[7]) if row[7] else 'N/A',
                            'latitud': latitud,
                            'longitud': longitud,
                            'tecnologia': str(row[10]) if row[10] else 'N/A',
                            'usuarios_afectados': usuarios,
                            'tiempo_afectacion_hrs': tiempo_afectacion,
                            'fecha_inicio_programado': parse_fecha(str(row[13])) if row[13] else None,
                            'fecha_fin_programado': parse_fecha(str(row[14])) if row[14] else None,
                            'grupo_ejecutor': str(row[15]) if row[15] else 'N/A',
                            'description_ot': str(row[16]) if row[16] else 'N/A',
                            'estado': 'Programado'
                        })
                    else:
                        coords_invalidas += 1
                        
            except Exception as e:
                print(f"⚠️ Error procesando fila {idx}: {e}")
                continue
        
        if cursor:
            cursor.close()
        if connection:
            connection.close()
        
        print(f"✅ Procesamiento completado:")
        print(f"   - Total registros: {len(resultados)}")
        print(f"   - Mantenimientos válidos: {len(mantenimientos)}")
        print(f"   - Coords inválidas: {coords_invalidas}")
        print(f"   - Usuarios afectados: {total_usuarios_afectados:,}")
        
        return jsonify({
            'success': True,
            'mantenimientos': mantenimientos,
            'total': len(mantenimientos),
            'total_sin_filtrar': len(resultados),
            'fecha_ultima_carga': fecha_ultima_carga_str,
            'total_usuarios_afectados': total_usuarios_afectados
        })
        
    except Exception as e:
        print(f"❌ ERROR en api_mantenimientos_activos:")
        print(f"   Tipo: {type(e).__name__}")
        print(f"   Mensaje: {str(e)}")
        
        import traceback
        print("📋 Traceback completo:")
        traceback.print_exc()
        
        # Cerrar conexiones si están abiertas
        try:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
        except:
            pass
        
        return jsonify({
            'success': False,
            'error': str(e),
            'mantenimientos': [],
            'fecha_ultima_carga': None,
            'total_usuarios_afectados': 0
        }), 500

# ============================================
# API: OBTENER TOTALES DE USUARIOS POR TECNOLOGÃA/DEPARTAMENTO/MUNICIPIO
# ============================================
def obtener_totales_usuarios_con_cache():
    """
    Obtiene totales con caché. Si el caché tiene menos de 15 minutos, 
    retorna los datos en caché sin consultar la BD
    """
    ahora = time.time()
    
    # Verificar si el caché es válido
    with cache_totales['lock']:
        if cache_totales['datos'] and (ahora - cache_totales['timestamp'] < CACHE_EXPIRACION):
            print(f"✅ Retornando datos del caché (edad: {int(ahora - cache_totales['timestamp'])}s)")
            return cache_totales['datos']
    
    # Si no hay caché válido, consultar la BD
    print("🔄 Caché expirado o vacío. Consultando base de datos...")
    
    connection = None
    cursor = None
    
    try:
        #dsn = cx_Oracle.makedsn(DB_MAXIMO_HOST, DB_MAXIMO_PORT, service_name=DB_MAXIMO_SERVICE_NAME)
	    #connection=cx_Oracle.connect(DB_MAXIMO_USER, DB_MAXIMO_PASSWORD, dsn,encoding= 'UTF-8')
        connection = cx_Oracle.connect(user=DB_MAXIMO_USER, password=DB_MAXIMO_PASSWORD, dsn=DB_MAXIMO_DSN, encoding= 'UTF-8')
        cursor = connection.cursor()
        
        # Query OPTIMIZADA (sin CTEs innecesarios)
        query = """
            SELECT 
                CASE 
                    WHEN CI.CLASSSTRUCTUREID = '1770' THEN '3G'
                    WHEN CI.CLASSSTRUCTUREID IN ('3493', '3551') THEN '4G'
                    WHEN CI.CLASSSTRUCTUREID = '6473' THEN '5G'
                END AS TECNOLOGIA,
                L.DEPTO_DESCRIPTION AS DEPARTAMENTO,
                L.MUN_DESCRIPTION AS MUNICIPIO,
                SUM(
                    CASE 
                        WHEN REGEXP_LIKE(CI_U.ALNVALUE, '^[0-9]+(.[0-9]+)?$') 
                        THEN TO_NUMBER(CI_U.ALNVALUE)
                        ELSE 0
                    END
                ) AS TOTAL_USUARIOS
            FROM MAXIMO.CI CI
            LEFT JOIN MAXIMO.CISPEC CI_U 
                ON CI_U.CINUM = CI.CINUM 
                AND CI_U.ASSETATTRID = 'USUARIOS'
            LEFT JOIN MAXIMO.LOCATION_VIEW L
                ON CI.CILOCATION = L.SIT_LOCATION
            WHERE CI.STATUS IN ('OPERATING', 'DEVELOPMENT')
                AND CI.CLASSSTRUCTUREID IN ('1770', '3493', '3551', '6473')
                AND L.DEPTO_DESCRIPTION IS NOT NULL
                AND L.MUN_DESCRIPTION IS NOT NULL
            GROUP BY 
                CASE 
                    WHEN CI.CLASSSTRUCTUREID = '1770' THEN '3G'
                    WHEN CI.CLASSSTRUCTUREID IN ('3493', '3551') THEN '4G'
                    WHEN CI.CLASSSTRUCTUREID = '6473' THEN '5G'
                END,
                L.DEPTO_DESCRIPTION,
                L.MUN_DESCRIPTION
        """
        
        tiempo_inicio = time.time()
        cursor.execute(query)
        resultados = cursor.fetchall()
        tiempo_consulta = time.time() - tiempo_inicio
        
        print(f"⏱️  Consulta ejecutada en {tiempo_consulta:.2f} segundos")
        
        # Estructurar datos (mismo código que antes)
        totales = {
            'por_tecnologia': {},
            'por_departamento': {},
            'por_municipio': {},
            'total_general': 0
        }
        
        for row in resultados:
            tecnologia = row[0] or 'N/A'
            departamento = row[1] or 'N/A'
            municipio = row[2] or 'N/A'
            usuarios = int(row[3]) if row[3] else 0
            
            # Por tecnología
            if tecnologia not in totales['por_tecnologia']:
                totales['por_tecnologia'][tecnologia] = 0
            totales['por_tecnologia'][tecnologia] += usuarios
            
            # Por departamento
            if departamento not in totales['por_departamento']:
                totales['por_departamento'][departamento] = 0
            totales['por_departamento'][departamento] += usuarios
            
            # Por municipio
            clave_municipio = f"{departamento}|{municipio}"
            if clave_municipio not in totales['por_municipio']:
                totales['por_municipio'][clave_municipio] = 0
            totales['por_municipio'][clave_municipio] += usuarios
            
            totales['total_general'] += usuarios
        
        cursor.close()
        connection.close()
        
        # Actualizar caché
        with cache_totales['lock']:
            cache_totales['datos'] = totales
            cache_totales['timestamp'] = time.time()
        
        print(f"✅ Totales calculados y almacenados en caché")
        print(f"   - Total general: {totales['total_general']:,}")
        
        return totales
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        if cursor:
            cursor.close()
        if connection:
            connection.close()
        raise
    
@app.route('/api/totales-usuarios')
@login_requerido
@permiso_requerido('servicio_al_cliente')
def api_totales_usuarios():
    """
    Versión optimizada con caché
    Obtiene los totales de usuarios por tecnología, departamento y municipio
    """
    try:
        print("📊 Solicitando totales de usuarios...")
        totales = obtener_totales_usuarios_con_cache()
        
        return jsonify({
            'success': True,
            'totales': totales,
            'cache_usado': cache_totales['timestamp'] > 0
        })
        
    except Exception as e:
        print(f"❌ ERROR en api_totales_usuarios: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': str(e),
            'totales': {
                'por_tecnologia': {},
                'por_departamento': {},
                'por_municipio': {},
                'total_general': 0
            }
        }), 500

# ============================================
# API: REFRESH MANUAL DEL CACHÉ (OPCIONAL)
# ============================================
@app.route('/api/totales-usuarios/refresh', methods=['POST'])
@login_requerido
@permiso_requerido('servicio_al_cliente')
def api_refresh_totales():
    """
    Fuerza la actualización del caché de totales
    """
    try:
        print("🔄 Forzando actualización del caché...")
        # Invalidar caché
        with cache_totales['lock']:
            cache_totales['datos'] = None
            cache_totales['timestamp'] = 0
        
        # Obtener nuevos datos
        totales = obtener_totales_usuarios_con_cache()
        
        return jsonify({
            'success': True,
            'message': 'Caché actualizado correctamente',
            'totales': totales
        })
    except Exception as e:
        print(f"❌ ERROR en api_refresh_totales: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# RUTAS Y APIs PARA SEGUIMIENTO HL5
# ============================================


# ============================================
# API: OBTENER TODAS LAS OTs HL5
# ============================================

@app.route('/api/hl5/ots')
@login_requerido
@permiso_requerido('dashboard')
def api_hl5_ots():
    """
    API para obtener todas las OTs HL5 activas con su información completa
    """
    connection = None
    cursor = None
    
    try:
        logging.info('📡 API: Obteniendo OTs HL5...')
        
        connection = get_mysql_connection()
        if not connection:
            return jsonify({'error': 'Error de conexión a la base de datos'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Query para obtener todas las OTs HL5
        query = """
            SELECT
                HORA_INICIO,
                NODE,
                CINUM,
                CINAME,
                COD_UBICA,
                CIUDAD,
                DEPARTAMENTO,
                LATITUD,
                LONGITUD,
                MAXIMO,
                OT,
                ESTADO_OT,
                GRUPO_OT,
                FECHA_AVANCE,
                AVANCE,
                DIAS,
                HORAS,
                FALLA_FO,
                OT_FO
            FROM reportes.db_dash_rose_hl5_ots
            ORDER BY DIAS DESC, HORAS DESC
        """
        
        cursor.execute(query)
        resultados = cast(list[dict], cursor.fetchall())

        logging.info(f'✅ API: Se obtuvieron {len(resultados)} OTs HL5')
        
        # Convertir valores decimales a float para JSON
        for row in resultados:
            if row.get('LATITUD'):
                row['LATITUD'] = float(row['LATITUD'])
            if row.get('LONGITUD'):
                row['LONGITUD'] = float(row['LONGITUD'])
            if row.get('HORAS'):
                row['HORAS'] = float(row['HORAS'])
            if row.get('DIAS'):
                row['DIAS'] = int(row['DIAS'])
        
        return jsonify(resultados), 200
        
    except Exception as e:
        logging.error(f'❌ Error en API hl5_ots: {str(e)}')
        return jsonify({'error': 'Error interno del servidor'}), 500
        
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# ============================================
# API: MÉTRICAS POR GRUPO
# ============================================

@app.route('/api/hl5/metricas')
@login_requerido
@permiso_requerido('dashboard')
def api_hl5_metricas():
    """
    API para obtener las métricas de cantidad de OTs por grupo asignado
    """
    connection = None
    cursor = None
    
    try:
        logging.info('📡 API: Obteniendo métricas por grupo...')
        
        connection = get_mysql_connection()
        if not connection:
            return jsonify({'error': 'Error de conexión a la base de datos'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Query para obtener cantidad de OTs por grupo
        query = """
            SELECT
                SUM(CAMPO) AS CAMPO,
                SUM(UNIRED) AS UNIRED,
                SUM(BACKOFFICE) AS BACKOFFICE,
                SUM(TX) AS TX,
                SUM(FO) AS FO,
                SUM(DxINET) AS DxINET,
                SUM(CG) AS CG
            FROM (
                SELECT
                    OT,
                    MAX(CASE 
                        WHEN GRUPO_OT IN ('O_CAMBA', 'O_CAMSA', 'O_CAMBU', 'O_CAMSO', 'O_CAMND', 
                                         'O_CAMPE', 'O_CAMME', 'O_CAMCA', 'O_CAMCU', 'O_CAMBO')
                        THEN 1 ELSE 0 
                    END) AS CAMPO,
                    MAX(CASE 
                        WHEN GRUPO_OT = 'O_DXINT' THEN 1 ELSE 0 
                    END) AS DxINET,
                    MAX(CASE 
                        WHEN GRUPO_OT = 'O_UNIRED' THEN 1 ELSE 0 
                    END) AS UNIRED,
                    MAX(CASE 
                        WHEN GRUPO_OT = 'O_GESFO' THEN 1 ELSE 0 
                    END) AS FO,
                    MAX(CASE 
                        WHEN GRUPO_OT = 'O_GESTRA' THEN 1 ELSE 0 
                    END) AS TX,
                    MAX(CASE 
                        WHEN GRUPO_OT IN ('O_GESRED') THEN 1 ELSE 0 
                    END) AS CG,
                    MAX(CASE 
                        WHEN GRUPO_OT = 'BACKOFFICE_N1' THEN 1 ELSE 0 
                    END) AS BACKOFFICE
                FROM reportes.db_dash_rose_hl5_ots
                WHERE GRUPO_OT IS NOT NULL
                GROUP BY OT
            ) AS sub
        """
        
        cursor.execute(query)
        resultado = cast(dict, cursor.fetchone())

        # Si no hay resultados, devolver ceros
        if not resultado:
            resultado = {
                'CAMPO': 0,
                'UNIRED': 0,
                'BACKOFFICE': 0,
                'TX': 0,
                'FO': 0,
                'DxINET': 0,
                'CG': 0
            }
        else:
            # Convertir None a 0 para cada campo
            for key in resultado:
                if resultado[key] is None:
                    resultado[key] = 0
                else:
                    resultado[key] = int(resultado[key])
        
        logging.info(f'✅ API: Métricas obtenidas: {resultado}')
        
        return jsonify(resultado), 200
        
    except Exception as e:
        logging.error(f'❌ Error en API hl5_metricas: {str(e)}')
        return jsonify({'error': 'Error interno del servidor'}), 500
        
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# ============================================
# API: ESTADÍSTICAS ADICIONALES (OPCIONAL)
# ============================================

@app.route('/api/hl5/estadisticas')
@login_requerido
@permiso_requerido('dashboard')
def api_hl5_estadisticas():
    """
    API opcional para obtener estadísticas adicionales
    """
    connection = None
    cursor = None
    
    try:
        logging.info('📡 API: Obteniendo estadísticas adicionales...')
        
        connection = get_mysql_connection()
        if not connection:
            return jsonify({'error': 'Error de conexión a la base de datos'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Estadísticas de tiempo de afectación
        query_tiempo = """
            SELECT
                COUNT(CASE WHEN HORAS < 4 THEN 1 END) AS menor_4h,
                COUNT(CASE WHEN HORAS >= 8 AND HORAS < 24 THEN 1 END) AS mayor_8h,
                COUNT(CASE WHEN HORAS >= 24 AND HORAS < 72 THEN 1 END) AS mayor_24h,
                COUNT(CASE WHEN HORAS >= 72 AND HORAS < 168 THEN 1 END) AS mayor_72h,
                COUNT(CASE WHEN DIAS >= 7 AND DIAS < 15 THEN 1 END) AS mayor_7d,
                COUNT(CASE WHEN DIAS >= 15 THEN 1 END) AS mayor_15d,
                COUNT(CASE WHEN FALLA_FO = 'SI' OR OT_FO IS NOT NULL THEN 1 END) AS con_fo_previa
            FROM reportes.db_dash_rose_hl5_ots
        """
        
        cursor.execute(query_tiempo)
        estadisticas = cast(dict, cursor.fetchone())

        # Convertir None a 0
        for key in estadisticas:
            if estadisticas[key] is None:
                estadisticas[key] = 0
        
        logging.info(f'✅ API: Estadísticas adicionales obtenidas')
        
        return jsonify(estadisticas), 200
        
    except Exception as e:
        logging.error(f'❌ Error en API hl5_estadisticas: {str(e)}')
        return jsonify({'error': 'Error interno del servidor'}), 500
        
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# ============================================
# API: OBTENER APERTURAS DE ANILLOS Y CABECERAS
# ============================================

@app.route('/api/hl5/aperturas-anillos')
@login_requerido
@permiso_requerido('dashboard')
def api_aperturas_anillos():
    """
    API para obtener todas las aperturas de cabeceras y anillos HL5
    desde la tabla db_dash_seguimiento_anillos_fo
    """
    connection = None
    cursor = None
    
    try:
        logging.info('📡 API: Obteniendo aperturas de anillos y cabeceras...')
        
        connection = get_mysql_connection()
        if not connection:
            logging.error('❌ No se pudo establecer conexión a MySQL')
            return jsonify({
                'success': False,
                'error': 'Error de conexión a la base de datos MySQL'
            }), 500
        
        logging.info('✅ Conexión a MySQL establecida')
        
        cursor = connection.cursor(dictionary=True)
        
        # Query para obtener todas las aperturas
        query = """
            SELECT
                INCIDENTE,
                RESUMEN,
                HORA_INICIO,
                ESTADO,
                OT,
                ESTADO_OT,
                GRUPO_OT,
                TIPO_APERTURA,
                FECHA_AVANCE,
                AVANCE,
                IP_A,
                NODO_A,
                SIT_DESCRIPTION_A,
                DEPARTAMENTO_A,
                MUNICIPIO_A,
                LATITUD_A,
                LONGITUD_A,
                SIT_LOCATION_A,
                FABRICANTE_A,
                NODO_A_STATUS,
                IP_B,
                NODO_B,
                SIT_DESCRIPTION_B,
                DEPARTAMENTO_B,
                MUNICIPIO_B,
                LATITUD_B,
                LONGITUD_B,
                SIT_LOCATION_B,
                FABRICANTE_B,
                NODO_B_STATUS,
                HORAS,
                AFECTA,
                ANILLO
            FROM reportes.db_dash_seguimiento_anillos_fo
            ORDER BY HORAS ASC
        """
        
        logging.info(f'🔍 Ejecutando query...')
        cursor.execute(query)

        resultados = cast(list[dict], cursor.fetchall())

        logging.info(f'✅ Query ejecutado. Registros obtenidos: {len(resultados)}')
        
        # Si no hay resultados, intentar query más simple para debug
        if len(resultados) == 0:
            logging.warning('⚠️ No se encontraron registros. Probando query simple...')
            
            # Query simple para verificar si existe la tabla
            cursor.execute("SELECT COUNT(*) as total FROM reportes.db_dash_seguimiento_anillos_fo")
            count_result = cast(dict, cursor.fetchone())
            total_registros = count_result['total'] if count_result else 0
            
            logging.info(f'📊 Total de registros en la tabla: {total_registros}')
            
            # Verificar campos
            cursor.execute("DESCRIBE reportes.db_dash_seguimiento_anillos_fo")
            campos = cast(list[dict], cursor.fetchall())
            logging.info(f'📋 Campos de la tabla: {[c["Field"] for c in campos]}')
            
            return jsonify({
                'success': True,
                'aperturas': [],
                'total': 0,
                'debug': {
                    'total_registros_tabla': total_registros,
                    'campos_disponibles': [c['Field'] for c in campos],
                    'mensaje': 'No hay registros que cumplan los criterios'
                }
            }), 200
        
        # Convertir valores Decimal a float para JSON
        aperturas = []
        for row in resultados:
            apertura = {}
            for key, value in row.items():
                if value is not None:
                    # Convertir Decimal a float
                    if isinstance(value, Decimal):
                        apertura[key] = float(value)
                    # Convertir datetime a string
                    elif isinstance(value, datetime):
                        apertura[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        apertura[key] = value
                else:
                    apertura[key] = None
            
            aperturas.append(apertura)
        
        logging.info(f'✅ {len(aperturas)} aperturas procesadas correctamente')
        
        return jsonify({
            'success': True,
            'aperturas': aperturas,
            'total': len(aperturas)
        }), 200
        
    except mysql.connector.Error as e:
        logging.error(f'❌ Error de MySQL: {e.errno} - {e.msg}')
        return jsonify({
            'success': False,
            'error': f'Error de MySQL: {e.msg}',
            'error_code': e.errno
        }), 500
        
    except Exception as e:
        logging.error(f'❌ Error general en API aperturas_anillos: {str(e)}')
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': str(e),
            'aperturas': []
        }), 500
        
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
            logging.info('🔌 Conexión MySQL cerrada')


# ============================================
# ENDPOINT DE DEBUG (temporal)
# ============================================

@app.route('/api/hl5/aperturas-anillos/debug')
@login_requerido
@permiso_requerido('dashboard')
def api_aperturas_anillos_debug():
    """
    Endpoint de debug para verificar la estructura de la tabla
    """
    connection = None
    cursor = None
    
    try:
        connection = get_mysql_connection()
        if not connection:
            return jsonify({'error': 'No se pudo conectar a MySQL'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # 1. Verificar total de registros
        cursor.execute("SELECT COUNT(*) as total FROM reportes.db_dash_seguimiento_anillos_fo")
        total = cast(dict, cursor.fetchone())['total']

        # 2. Obtener estructura de la tabla
        cursor.execute("DESCRIBE reportes.db_dash_seguimiento_anillos_fo")
        estructura = cast(list[dict], cursor.fetchall())

        # 3. Obtener primeros 5 registros
        cursor.execute("SELECT * FROM reportes.db_dash_seguimiento_anillos_fo LIMIT 5")
        muestra = cast(list[dict], cursor.fetchall())
        
        # Convertir Decimals en la muestra
        muestra_limpia = []
        for row in muestra:
            row_limpia = {}
            for key, value in row.items():
                if isinstance(value, Decimal):
                    row_limpia[key] = float(value)
                elif isinstance(value, datetime):
                    row_limpia[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    row_limpia[key] = value
            muestra_limpia.append(row_limpia)
        
        return jsonify({
            'success': True,
            'total_registros': total,
            'estructura_tabla': [{'campo': c['Field'], 'tipo': c['Type']} for c in estructura],
            'muestra_datos': muestra_limpia
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
        
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()



# ============================================
# API: MONITOREO HL5 - VERSIÓN DEBUG
# ============================================
# Agregar estos endpoints DESPUÉS de la función get_mysql_connection()
# y ANTES del if __name__ == '__main__'

# IMPORTANTE: Estos endpoints NO tienen decoradores de login
# Son solo para testing. Una vez que funcionen, usa la versión completa.

@app.route('/api/hl5/test')
def api_hl5_test():
    """Endpoint de prueba simple"""
    return jsonify({
        'success': True,
        'message': 'API HL5 funcionando correctamente',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/hl5/metricas-debug')
def api_hl5_metricas_debug():
    """
    Obtiene las métricas generales de HL5 (versión debug sin login)
    """
    connection = None
    cursor = None
    
    try:
        print("📊 [DEBUG] Iniciando consulta de métricas HL5...")
        print(f"📊 [DEBUG] Host MySQL: 192.168.44.114")
        
        connection = get_mysql_connection()
        print("📊 [DEBUG] Conexión MySQL establecida")
        
        cursor = connection.cursor(dictionary=True)
        
        # Query para obtener métricas generales
        query = """
            SELECT
                COUNT(DISTINCT q1.NODE) AS HL5_AFECTADOS,
                COUNT(DISTINCT CASE WHEN q1.TECNOLOGIA = '3G' THEN q1.CINUM_RBS END) AS TOTAL_3G,
                COUNT(DISTINCT CASE WHEN q1.TECNOLOGIA = '4G' THEN q1.CINUM_RBS END) AS TOTAL_4G,
                COUNT(DISTINCT CASE WHEN q1.CINUM_RBS <> 'nan' THEN q1.CINUM_RBS END) AS TOTAL_RBS,
                COUNT(DISTINCT CASE WHEN q2.CLIENTE_B2B IS NOT NULL THEN q1.NODE END) AS TOTAL_B2B,
                MAX(q1.HORA_LECTURA) AS HORA_ULTIMA_ACTUALIZACION
            FROM reportes.db_dash_rose_hl5_inv q1
            LEFT JOIN reportes.db_dash_rose_hl5_inv_b2b q2 
                ON q1.NODE = q2.NODE
            WHERE q1.HORA_LECTURA = (
                SELECT MAX(HORA_LECTURA)
                FROM reportes.db_dash_rose_hl5_inv
            )
        """
        
        print("📊 [DEBUG] Ejecutando query de métricas...")
        cursor.execute(query)
        resultado = cursor.fetchone()
        print(f"📊 [DEBUG] Métricas obtenidas: {resultado}")
        
        # Formatear hora de última actualización sin ajuste de huso horario
        if resultado and resultado['HORA_ULTIMA_ACTUALIZACION']:
            hora = resultado['HORA_ULTIMA_ACTUALIZACION']
            resultado['HORA_ULTIMA_ACTUALIZACION'] = hora.strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.close()
        connection.close()
        print("📊 [DEBUG] Conexión cerrada correctamente")
        
        return jsonify({
            'success': True,
            'metricas': resultado
        })
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ [DEBUG] ERROR en api_hl5_metricas_debug: {error_msg}")
        import traceback
        traceback.print_exc()
        
        if cursor:
            cursor.close()
        if connection:
            connection.close()
        
        return jsonify({
            'success': False,
            'error': error_msg,
            'metricas': {
                'HL5_AFECTADOS': 0,
                'TOTAL_3G': 0,
                'TOTAL_4G': 0,
                'TOTAL_RBS': 0,
                'TOTAL_B2B': 0,
                'HORA_ULTIMA_ACTUALIZACION': None
            }
        }), 500

@app.route('/api/hl5/mapa-debug')
def api_hl5_mapa_debug():
    """
    Obtiene los datos para el mapa de HL5 (versión debug sin login)
    """
    connection = None
    cursor = None
    
    try:
        print("🗺️ [DEBUG] Iniciando consulta de datos para mapa HL5...")
        connection = get_mysql_connection()
        cursor = connection.cursor(dictionary=True)
        
        query = """
            SELECT DISTINCT
                HORA_INICIO,
                CINUM,
                CINUM_RBS,
                TECNOLOGIA,
                CINAME,
                LATITUD,
                LONGITUD,
                CIUDAD,
                DEPARTAMENTO
            FROM reportes.db_dash_rose_hl5_inv
            WHERE HORA_LECTURA = (
                SELECT MAX(HORA_LECTURA)
                FROM reportes.db_dash_rose_hl5_inv
            )
            ORDER BY HORA_INICIO DESC
        """
        
        print("🗺️ [DEBUG] Ejecutando query del mapa...")
        cursor.execute(query)
        resultados = cursor.fetchall()
        print(f"🗺️ [DEBUG] Datos de mapa obtenidos: {len(resultados)} registros")
        
        # Convertir datetime a string
        for row in resultados:
            if row['HORA_INICIO']:
                row['HORA_INICIO'] = row['HORA_INICIO'].strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'datos': resultados
        })
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ [DEBUG] ERROR en api_hl5_mapa_debug: {error_msg}")
        import traceback
        traceback.print_exc()
        
        if cursor:
            cursor.close()
        if connection:
            connection.close()
        
        return jsonify({
            'success': False,
            'error': error_msg,
            'datos': []
        }), 500

@app.route('/api/hl5/detalle-debug')
def api_hl5_detalle_debug():
    """
    Obtiene los datos para la tabla de detalle de HL5 (versión debug sin login)
    """
    connection = None
    cursor = None
    
    try:
        print("📋 [DEBUG] Iniciando consulta de detalle HL5...")
        connection = get_mysql_connection()
        cursor = connection.cursor(dictionary=True)
        
        query = """
            SELECT
                q1.HORA_INICIO,
                q1.NODE,
                q1.CINUM,
                q1.CINAME,
                q1.CIUDAD,
                q1.DEPARTAMENTO,
                
                COUNT(DISTINCT CASE WHEN q1.TECNOLOGIA = '3G' THEN q1.CINUM_RBS END) AS `3G`,
                COUNT(DISTINCT CASE WHEN q1.TECNOLOGIA = '4G' THEN q1.CINUM_RBS END) AS `4G`,
                (
                    COUNT(DISTINCT CASE WHEN q1.TECNOLOGIA = '3G' THEN q1.CINUM_RBS END) +
                    COUNT(DISTINCT CASE WHEN q1.TECNOLOGIA = '4G' THEN q1.CINUM_RBS END)
                ) AS TOTAL_RB,
                COUNT(DISTINCT CASE WHEN q2.CLIENTE_B2B IS NOT NULL THEN q2.CLIENTE_B2B END) AS B2B,
                CAST(
                    MAX(
                    CASE
                        WHEN q1.MAXIMO_HL5 IS NULL OR q1.MAXIMO_HL5 = '' OR LOWER(q1.MAXIMO_HL5) = 'nan' THEN NULL
                        ELSE CAST(TRIM(SUBSTRING_INDEX(q1.MAXIMO_HL5, ',', -1)) AS UNSIGNED)
                    END
                    ) AS CHAR
                ) AS INC_HL5,
                GROUP_CONCAT(DISTINCT q1.MAXIMO_MOVIL) AS INC_MOVIL,
                MAX(q3.centro_experiencia) AS CEXP

                FROM reportes.db_dash_rose_hl5_inv q1

                LEFT JOIN reportes.db_dash_rose_hl5_inv_b2b q2 ON q1.NODE = q2.NODE
                LEFT JOIN reportes.centros_experiencia q3 ON q1.CINUM = q3.cinum 

                WHERE q1.HORA_LECTURA = (
                SELECT MAX(HORA_LECTURA)
                FROM reportes.db_dash_rose_hl5_inv
                )

                GROUP BY
                q1.HORA_INICIO, q1.NODE, q1.CINUM, q1.CINAME, q1.CIUDAD, q1.DEPARTAMENTO

                ORDER BY
                q1.HORA_INICIO DESC
        """
        
        print("📋 [DEBUG] Ejecutando query de detalle...")
        cursor.execute(query)
        resultados = cursor.fetchall()
        print(f"📋 [DEBUG] Detalle HL5 obtenido: {len(resultados)} registros")
        
        # Convertir datetime a string
        for row in resultados:
            if row['HORA_INICIO']:
                row['HORA_INICIO'] = row['HORA_INICIO'].strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'datos': resultados
        })
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ [DEBUG] ERROR en api_hl5_detalle_debug: {error_msg}")
        import traceback
        traceback.print_exc()
        
        if cursor:
            cursor.close()
        if connection:
            connection.close()
        
        return jsonify({
            'success': False,
            'error': error_msg,
            'datos': []
        }), 500

# ============================================
# API: MONITOREO HL5 - HISTÓRICO (ÚLTIMO DÍA)
# ============================================
# Reemplaza el endpoint anterior con este

@app.route('/api/hl5/historico-debug')
def api_hl5_historico_debug():
    """
    Obtiene el histórico de afectación por tecnología (último día - 24 horas)
    """
    connection = None
    cursor = None
    
    try:
        print("📈 [DEBUG] Iniciando consulta de histórico HL5 (último día)...")
        connection = get_mysql_connection()
        cursor = connection.cursor(dictionary=True)
        
        query = """
            SELECT 
                HORA_LECTURA,
                COUNT(DISTINCT CINUM) AS HL5,
                COUNT(DISTINCT CASE WHEN TECNOLOGIA = '3G' THEN CINUM_RBS END) AS `3G`,
                COUNT(DISTINCT CASE WHEN TECNOLOGIA = '4G' THEN CINUM_RBS END) AS `4G`,
                COUNT(DISTINCT CASE WHEN CINUM_RBS <> 'nan' THEN CINUM_RBS END) as TOTAL_RBS
            FROM reportes.db_dash_rose_hl5_inv
            WHERE HORA_LECTURA >= NOW() - INTERVAL 1 DAY
            GROUP BY HORA_LECTURA
            ORDER BY HORA_LECTURA ASC
        """
        
        print("📈 [DEBUG] Ejecutando query de histórico...")
        cursor.execute(query)
        resultados = cursor.fetchall()
        print(f"📈 [DEBUG] Histórico obtenido: {len(resultados)} registros (último día)")
        
        # Convertir datetime a string
        for row in resultados:
            if row['HORA_LECTURA']:
                row['HORA_LECTURA'] = row['HORA_LECTURA'].strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'datos': resultados
        })
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ [DEBUG] ERROR en api_hl5_historico_debug: {error_msg}")
        import traceback
        traceback.print_exc()
        
        if cursor:
            cursor.close()
        if connection:
            connection.close()
        
        return jsonify({
            'success': False,
            'error': error_msg,
            'datos': []
        }), 500

# ==============================================================================
# ENDPOINT: Tiempo de Afectación HL5
# Descripción: Retorna el conteo de HL5 por rangos de tiempo de afectación
# ==============================================================================

cache_tiempo_afectacion = {
    'datos': None,
    'timestamp': None,
    'lock': Lock()
}

# Caché de 2 minutos (esta consulta es costosa)
CACHE_EXPIRACION_TIEMPO = 120  # segundos

def obtener_datos_cache_tiempo():
    """
    Obtiene datos del caché si están vigentes
    """
    with cache_tiempo_afectacion['lock']:
        if cache_tiempo_afectacion['timestamp']:
            edad_cache = (datetime.now() - cache_tiempo_afectacion['timestamp']).total_seconds()
            if edad_cache < CACHE_EXPIRACION_TIEMPO:
                print(f"📦 [CACHÉ HIT] Datos de tiempo de afectación ({edad_cache:.1f}s antiguos)")
                return cache_tiempo_afectacion['datos']
    return None

def guardar_datos_cache_tiempo(datos):
    """
    Guarda datos en el caché
    """
    with cache_tiempo_afectacion['lock']:
        cache_tiempo_afectacion['datos'] = datos
        cache_tiempo_afectacion['timestamp'] = datetime.now()
        print(f"💾 [CACHÉ] Datos de tiempo de afectación guardados")

# ============================================
# ENDPOINT OPTIMIZADO CON CACHÉ Y QUERY MEJORADA
# ============================================

@app.route('/api/hl5/tiempo-afectacion', methods=['GET'])
def api_hl5_tiempo_afectacion():
    """
    Endpoint ULTRA-OPTIMIZADO para obtener conteo de HL5 por tiempo de afectación
    
    OPTIMIZACIONES APLICADAS v2:
    - Sistema de caché de 2 minutos
    - Índices compuestos en MySQL
    - Query simplificada con menos TIMESTAMPDIFF
    - Timeout extendido a 60 segundos
    - Manejo robusto de errores
    
    Returns:
        JSON con conteos por cada rango de tiempo de afectación
    """
    try:
        # ✅ OPTIMIZACIÓN 1: Verificar caché primero
        datos_cache = obtener_datos_cache_tiempo()
        if datos_cache:
            return jsonify({
                'success': True,
                'datos': [datos_cache['resultado']],
                'ultima_hora': str(datos_cache['ultima_hora']),
                'tiempo_ejecucion': '0.00s (caché)',
                'cache_hit': True,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        
        inicio_tiempo = datetime.now()
        
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)
        
        # ⚡ OPTIMIZACIÓN 2: Timeout extendido (60 segundos)
        cursor.execute("SET SESSION MAX_EXECUTION_TIME=60000")
        
        # ⚡ OPTIMIZACIÓN 3: Obtener MAX(HORA_LECTURA) con caché reutilizable
        ultima_hora = obtener_ultima_hora_lectura(cursor)
        
        if not ultima_hora:
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'error': 'No se pudo determinar la última hora de lectura',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }), 500
        
        print(f"📅 Última hora de lectura: {ultima_hora}")
        
        # ⚡ OPTIMIZACIÓN 4: Query mejorada con pre-filtrado
        # Usamos una subconsulta para reducir el dataset antes de calcular TIMESTAMPDIFF
        query_optimizada = """
            SELECT
                COUNT(DISTINCT CASE WHEN horas_afectacion < 4 THEN NODE END) AS menor_4h,
                COUNT(DISTINCT CASE WHEN horas_afectacion >= 4 AND horas_afectacion < 8 THEN NODE END) AS menor_8h,
                COUNT(DISTINCT CASE WHEN horas_afectacion >= 8 AND horas_afectacion < 24 THEN NODE END) AS menor_24h,
                COUNT(DISTINCT CASE WHEN dias_afectacion >= 1 AND dias_afectacion < 2 THEN NODE END) AS mayor_1d,
                COUNT(DISTINCT CASE WHEN dias_afectacion >= 2 AND dias_afectacion < 3 THEN NODE END) AS mayor_2d,
                COUNT(DISTINCT CASE WHEN dias_afectacion >= 3 AND dias_afectacion < 4 THEN NODE END) AS mayor_3d,
                COUNT(DISTINCT CASE WHEN dias_afectacion >= 4 AND dias_afectacion < 5 THEN NODE END) AS mayor_4d,
                COUNT(DISTINCT CASE WHEN dias_afectacion >= 5 AND dias_afectacion < 6 THEN NODE END) AS mayor_5d,
                COUNT(DISTINCT CASE WHEN dias_afectacion >= 6 AND dias_afectacion < 7 THEN NODE END) AS mayor_6d,
                COUNT(DISTINCT CASE WHEN dias_afectacion >= 7 AND dias_afectacion < 15 THEN NODE END) AS mayor_7d,
                COUNT(DISTINCT CASE WHEN dias_afectacion >= 15 THEN NODE END) AS mayor_15d
            FROM (
                SELECT 
                    NODE,
                    TIMESTAMPDIFF(HOUR, HORA_INICIO, NOW()) AS horas_afectacion,
                    TIMESTAMPDIFF(DAY, HORA_INICIO, NOW()) AS dias_afectacion
                FROM reportes.db_dash_rose_hl5_inv
                WHERE HORA_LECTURA = %s
                AND HORA_INICIO IS NOT NULL
                AND NODE IS NOT NULL
            ) AS tiempos_calculados
        """
        
        cursor.execute(query_optimizada, (ultima_hora,))
        resultado = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        # Calcular tiempo de ejecución
        tiempo_total = (datetime.now() - inicio_tiempo).total_seconds()
        
        # ✅ OPTIMIZACIÓN 5: Guardar en caché
        datos_para_cache = {
            'resultado': resultado,
            'ultima_hora': ultima_hora
        }
        guardar_datos_cache_tiempo(datos_para_cache)
        
        # Log de auditoría
        print(f"✅ [API] Tiempo de afectación consultado en {tiempo_total:.2f}s")
        
        return jsonify({
            'success': True,
            'datos': [resultado] if resultado else [],
            'ultima_hora': str(ultima_hora),
            'tiempo_ejecucion': f"{tiempo_total:.2f}s",
            'cache_hit': False,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except mysql.connector.Error as db_error:
        error_msg = str(db_error)
        print(f"❌ [DB ERROR] Error de base de datos: {error_msg}")
        
        # Detectar si es timeout
        if '3024' in error_msg or 'execution time exceeded' in error_msg.lower():
            return jsonify({
                'success': False,
                'error': 'La consulta excedió el tiempo máximo de ejecución',
                'detail': 'Se requiere optimización de índices en la base de datos',
                'solucion': 'Ejecutar script 01_optimizacion_indices_mysql.sql',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }), 504  # Gateway Timeout
        
        return jsonify({
            'success': False,
            'error': 'Error de base de datos',
            'detail': error_msg,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500
        
    except Exception as e:
        print(f"❌ [API ERROR] Error en tiempo de afectación: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@app.route('/api/hl5/ubicacion', methods=['GET'])
def api_hl5_ubicacion():
    """
    Endpoint para obtener conteo de HL5 afectados por departamento y por ciudad (Top 10)
    
    Returns:
        JSON con dos arrays:
        - departamentos: Lista de departamentos con cantidad de HL5 afectados (ordenado DESC)
        - ciudades: Lista de Top 10 ciudades con cantidad de HL5 afectados (ordenado DESC)
    """
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Query para obtener HL5 por departamento
        query_departamentos = """
            SELECT
                DEPARTAMENTO,
                COUNT(DISTINCT CINUM) AS HL5
            FROM reportes.db_dash_rose_hl5_inv
            WHERE CINUM IS NOT NULL
            AND HORA_LECTURA = (
                SELECT MAX(HORA_LECTURA)
                FROM reportes.db_dash_rose_hl5_inv
            )
            GROUP BY DEPARTAMENTO
            ORDER BY HL5 DESC
        """
        
        cursor.execute(query_departamentos)
        departamentos = cursor.fetchall()
        
        # Query para obtener Top 10 ciudades
        query_ciudades = """
            SELECT
                CONCAT(CIUDAD, ' - ', DEPARTAMENTO) AS MUNICIPIO,
                COUNT(DISTINCT CINUM) AS HL5
            FROM reportes.db_dash_rose_hl5_inv
            WHERE CINUM IS NOT NULL
            AND HORA_LECTURA = (
                SELECT MAX(HORA_LECTURA)
                FROM reportes.db_dash_rose_hl5_inv
            )
            GROUP BY CIUDAD, DEPARTAMENTO
            ORDER BY HL5 DESC
            LIMIT 10
        """
        
        cursor.execute(query_ciudades)
        ciudades = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Log de auditoría
        print(f"✅ [API] Ubicación consultada - Departamentos: {len(departamentos)}, Ciudades: {len(ciudades)}")
        
        return jsonify({
            'success': True,
            'departamentos': departamentos,
            'ciudades': ciudades,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        print(f"❌ [API ERROR] Error en ubicación: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

# ============================================
# ENDPOINT PARA GRÁFICOS RBS
# ============================================
# Agregar este código ANTES de la línea: if __name__ == '__main__':

# Variable global para cachear la última hora de lectura
_ultima_hora_cache = {
    'timestamp': None,
    'valor': None
}
CACHE_DURACION_SEGUNDOS = 60  # Cache por 1 minuto

def obtener_ultima_hora_lectura(cursor):
    """
    Obtiene la última hora de lectura del sistema con caché
    """
    ahora = datetime.now()
    
    # Verificar si el cache es válido
    if (_ultima_hora_cache['timestamp'] and 
        (ahora - _ultima_hora_cache['timestamp']).total_seconds() < CACHE_DURACION_SEGUNDOS):
        return _ultima_hora_cache['valor']
    
    # Si no hay cache válido, consultar la base de datos
    query = """
        SELECT MAX(HORA_LECTURA) as max_hora
        FROM reportes.db_dash_rose_hl5_inv
        WHERE CINUM_RBS IS NOT NULL
    """
    cursor.execute(query)
    resultado = cursor.fetchone()
    
    if resultado and resultado['max_hora']:
        _ultima_hora_cache['timestamp'] = ahora
        _ultima_hora_cache['valor'] = resultado['max_hora']
        return resultado['max_hora']
    
    return None

@app.route('/api/hl5/rbs-ubicacion', methods=['GET'])
def api_hl5_rbs_ubicacion():
    """
    Endpoint OPTIMIZADO para obtener conteo de RBS afectadas por departamento y municipio
    con desglose por tecnología (3G y 4G)
    
    OPTIMIZACIONES:
    - Usa CTE para evitar subconsultas repetidas
    - Limita municipios a TOP 15 para mejor rendimiento
    - Implementa caché de última hora de lectura
    - Configura timeout en el cursor
    
    Returns:
        JSON con dos arrays:
        - departamentos: Lista de departamentos con RBS por tecnología (ordenado DESC)
        - municipios: Lista de TOP 15 municipios con RBS por tecnología (ordenado DESC)
    """
    try:
        inicio_tiempo = datetime.now()
        
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Configurar timeout del cursor (30 segundos)
        cursor.execute("SET SESSION MAX_EXECUTION_TIME=30000")
        
        # Obtener última hora de lectura con caché
        ultima_hora = obtener_ultima_hora_lectura(cursor)
        
        if not ultima_hora:
            return jsonify({
                'success': False,
                'error': 'No se pudo determinar la última hora de lectura',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }), 500
        
        print(f"📅 Última hora de lectura: {ultima_hora}")
        
        # ============================================
        # QUERY OPTIMIZADA PARA DEPARTAMENTOS
        # ============================================
        rango_consulta = 'ultima_hora'
        query_departamentos = """
            SELECT
                DEPARTAMENTO,
                COUNT(DISTINCT CINUM_RBS) AS TOTAL,
                COUNT(DISTINCT CASE WHEN TECNOLOGIA = '3G' THEN CINUM_RBS END) AS `3G`,
                COUNT(DISTINCT CASE WHEN TECNOLOGIA = '4G' THEN CINUM_RBS END) AS `4G`
            FROM reportes.db_dash_rose_hl5_inv
            WHERE CINUM_RBS IS NOT NULL
            AND HORA_LECTURA = %s
            GROUP BY DEPARTAMENTO
            ORDER BY TOTAL DESC
        """
        
        cursor.execute(query_departamentos, (ultima_hora,))
        departamentos = cursor.fetchall()
        
        # ============================================
        # QUERY OPTIMIZADA PARA MUNICIPIOS (TOP 15)
        # ============================================
        query_municipios = """
            SELECT
                CONCAT(CIUDAD, ' - ', DEPARTAMENTO) AS MUNICIPIO,
                COUNT(DISTINCT CINUM_RBS) AS TOTAL,
                COUNT(DISTINCT CASE WHEN TECNOLOGIA = '3G' THEN CINUM_RBS END) AS `3G`,
                COUNT(DISTINCT CASE WHEN TECNOLOGIA = '4G' THEN CINUM_RBS END) AS `4G`
            FROM reportes.db_dash_rose_hl5_inv
            WHERE CINUM_RBS IS NOT NULL
            AND HORA_LECTURA = %s
            GROUP BY CIUDAD, DEPARTAMENTO
            ORDER BY TOTAL DESC
            LIMIT 15
        """
        
        cursor.execute(query_municipios, (ultima_hora,))
        municipios = cursor.fetchall()
        
        # Respaldo: si no hay datos en la ¢ltima hora, usar ventana de 24h
        if (not departamentos) and (not municipios):
            rango_consulta = 'ventana_24h'
            inicio_ventana = (ultima_hora - timedelta(hours=24)) if ultima_hora else (datetime.now() - timedelta(hours=24))
            fin_ventana = ultima_hora if ultima_hora else datetime.now()
            
            print(f"⚠️ [API] Sin datos en la ¢ltima hora, usando ventana {inicio_ventana} -> {fin_ventana}")
            
            query_departamentos_ventana = """
                SELECT
                    DEPARTAMENTO,
                    COUNT(DISTINCT CINUM_RBS) AS TOTAL,
                    COUNT(DISTINCT CASE WHEN TECNOLOGIA = '3G' THEN CINUM_RBS END) AS `3G`,
                    COUNT(DISTINCT CASE WHEN TECNOLOGIA = '4G' THEN CINUM_RBS END) AS `4G`
                FROM reportes.db_dash_rose_hl5_inv
                WHERE CINUM_RBS IS NOT NULL
                AND HORA_LECTURA BETWEEN %s AND %s
                GROUP BY DEPARTAMENTO
                ORDER BY TOTAL DESC
            """
            
            query_municipios_ventana = """
                SELECT
                    CONCAT(CIUDAD, ' - ', DEPARTAMENTO) AS MUNICIPIO,
                    COUNT(DISTINCT CINUM_RBS) AS TOTAL,
                    COUNT(DISTINCT CASE WHEN TECNOLOGIA = '3G' THEN CINUM_RBS END) AS `3G`,
                    COUNT(DISTINCT CASE WHEN TECNOLOGIA = '4G' THEN CINUM_RBS END) AS `4G`
                FROM reportes.db_dash_rose_hl5_inv
                WHERE CINUM_RBS IS NOT NULL
                AND HORA_LECTURA BETWEEN %s AND %s
                GROUP BY CIUDAD, DEPARTAMENTO
                ORDER BY TOTAL DESC
                LIMIT 15
            """
            
            cursor.execute(query_departamentos_ventana, (inicio_ventana, fin_ventana))
            departamentos = cursor.fetchall()
            
            cursor.execute(query_municipios_ventana, (inicio_ventana, fin_ventana))
            municipios = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Calcular tiempo de ejecución
        tiempo_total = (datetime.now() - inicio_tiempo).total_seconds()
        
        # Log de auditoría
        print(f"✅ [API] RBS por ubicación consultada en {tiempo_total:.2f}s")
        print(f"   - Departamentos: {len(departamentos)}")
        print(f"   - Municipios: {len(municipios)}")
        
        return jsonify({
            'success': True,
            'departamentos': departamentos,
            'municipios': municipios,
            'ultima_hora': str(ultima_hora),
            'rango_consulta': rango_consulta,
            'tiempo_ejecucion': f"{tiempo_total:.2f}s",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except mysql.connector.Error as db_error:
        print(f"❌ [DB ERROR] Error de base de datos: {str(db_error)}")
        return jsonify({
            'success': False,
            'error': 'Error de base de datos',
            'detail': str(db_error),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500
        
    except Exception as e:
        print(f"❌ [API ERROR] Error en RBS por ubicación: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500


# ============================================
# API: GESTIONAR OT
# ============================================

@app.route('/api/hl5/gestionar-ot', methods=['POST'])
@login_requerido
@permiso_requerido('dashboard')
def api_gestionar_ot():
    """
    API para gestionar órdenes de trabajo HL5.
    Soporta tres acciones: AVANCE, CERRAR y ESCALAR
    
    IMPORTANTE: Siempre retorna {success: true/false} para el frontend
    """
    connection = None
    cursor = None
    
    try:
        # Obtener datos del request
        datos = request.get_json()
        
        if not datos:
            logging.error("❌ No se recibieron datos en la petición")
            return jsonify({
                'success': False,
                'error': 'No se recibieron datos'
            }), 400
        
        # Validar campos obligatorios
        ot = datos.get('ot')
        tipo_accion = datos.get('tipo_accion', '').upper()
        incidente = datos.get('incidente', '')
        
        logging.info(f"📡 Petición recibida - OT: {ot}, Acción: {tipo_accion}")
        
        if not ot:
            logging.error("❌ OT no proporcionada")
            return jsonify({
                'success': False,
                'error': 'El número de OT es obligatorio'
            }), 400
        
        if tipo_accion not in ['AVANCE', 'CERRAR', 'ESCALAR']:
            logging.error(f"❌ Tipo de acción inválido: {tipo_accion}")
            return jsonify({
                'success': False,
                'error': f'Tipo de acción inválido: {tipo_accion}'
            }), 400
        
        # Obtener usuario actual
        usuario = session.get('USUARIO', 'SMARTSOC')
        
        logging.info(
            f"📡 API Gestionar OT - "
            f"Usuario: {usuario} - "
            f"OT: {ot} - "
            f"Acción: {tipo_accion}"
        )
        
        # ==========================================
        # ACCIÓN: INSERTAR AVANCE
        # ==========================================
        if tipo_accion == 'AVANCE':
            comentario = datos.get('comentario')
            
            if not comentario:
                logging.error("❌ Comentario no proporcionado")
                return jsonify({
                    'success': False,
                    'error': 'El comentario es obligatorio para insertar avance'
                }), 400
            
            logging.info(f"📝 Insertando avance en OT {ot}...")
            
            # Insertar avance en Maximo
            resultado = job_insertar_avances_ots(ot, comentario, usuario)
            
            logging.info(f"📊 Resultado de Maximo: {resultado}")
            
            # Verificar resultado
            if resultado.get('success'):
                # Registrar en base de datos local
                try:
                    connection = get_mysql_connection()
                    cursor = connection.cursor()
                    
                    query_update = """
                        UPDATE reportes.db_dash_seguimiento_anillos_fo
                        SET FECHA_AVANCE = NOW(),
                            AVANCE = %s
                        WHERE OT = %s
                    """
                    cursor.execute(query_update, (comentario[:500], ot))
                    connection.commit()
                    
                    logging.info(f"✅ Avance registrado en BD local para OT {ot}")
                except Exception as e:
                    logging.error(f"⚠️ Error al actualizar BD local: {e}")
                    # No fallar si no se puede actualizar BD local
                
                # IMPORTANTE: Retornar formato exacto que espera el frontend
                response_data = {
                    'success': True,  # ← Campo OBLIGATORIO (boolean)
                    'message': 'Avance insertado correctamente',
                    'ot': ot
                }
                
                logging.info(f"✅ Respondiendo al frontend: {response_data}")
                return jsonify(response_data), 200
            
            else:
                # Error al insertar avance
                error_msg = resultado.get('message', 'Error desconocido')
                logging.error(f"❌ Error al insertar avance: {error_msg}")
                
                return jsonify({
                    'success': False,  # ← Campo OBLIGATORIO (boolean)
                    'error': error_msg,
                    'ot': ot
                }), 500
        
        # ==========================================
        # ACCIÓN: CERRAR OT
        # ==========================================
        elif tipo_accion == 'CERRAR':
            comentario = datos.get('comentario')
            estado = datos.get('estado', 'COMP')
            
            if not comentario:
                logging.error("❌ Comentario no proporcionado para cierre")
                return jsonify({
                    'success': False,
                    'error': 'El comentario es obligatorio para cerrar OT'
                }), 400
            
            logging.info(f"🔒 Cerrando OT {ot} con estado {estado}...")
            
            # Cerrar OT en Maximo
            resultado = job_cierre_ot(ot, comentario, usuario, estado)
            
            # Registrar en base de datos local
            try:
                connection = get_mysql_connection()
                cursor = connection.cursor()
                
                query_update = """
                    UPDATE reportes.db_dash_seguimiento_anillos_fo
                    SET ESTADO_OT = %s,
                        FECHA_AVANCE = NOW(),
                        AVANCE = %s
                    WHERE OT = %s
                """
                cursor.execute(query_update, (estado, comentario[:500], ot))
                connection.commit()
                
                logging.info(f"✅ Cierre registrado en BD local para OT {ot}")
            except Exception as e:
                logging.error(f"⚠️ Error al actualizar BD local: {e}")
            
            return jsonify({
                'success': True,
                'message': 'OT cerrada correctamente',
                'ot': ot,
                'estado': estado
            }), 200
        
        # ==========================================
        # ACCIÓN: ESCALAR OT (CAMBIAR GRUPO)
        # ==========================================
        elif tipo_accion == 'ESCALAR':
            area_destino = datos.get('area_destino')
            motivo = datos.get('motivo')
            
            if not area_destino:
                logging.error("❌ Área destino no proporcionada")
                return jsonify({
                    'success': False,
                    'error': 'El área destino es obligatoria para escalar OT'
                }), 400
            
            if not motivo:
                logging.error("❌ Motivo no proporcionado")
                return jsonify({
                    'success': False,
                    'error': 'El motivo es obligatorio para escalar OT'
                }), 400
            
            logging.info(f"🔄 Escalando OT {ot} a {area_destino}...")
            
            # Cambiar grupo de la OT en Maximo
            resultado = job_cambiar_grupo_ot(ot, area_destino, motivo)
            
            logging.info(f"📊 Resultado de escalamiento: {resultado}")
            
            if resultado.get('success'):
                # Registrar en base de datos local
                try:
                    connection = get_mysql_connection()
                    cursor = connection.cursor()
                    
                    query_update = """
                        UPDATE reportes.db_dash_seguimiento_anillos_fo
                        SET GRUPO_OT = %s,
                            FECHA_AVANCE = NOW(),
                            AVANCE = CONCAT('🔄 ESCALADO - ', %s)
                        WHERE OT = %s
                    """
                    cursor.execute(query_update, (area_destino, motivo[:500], ot))
                    connection.commit()
                    
                    logging.info(f"✅ Escalamiento registrado en BD local para OT {ot}")
                except Exception as e:
                    logging.error(f"⚠️ Error al actualizar BD local: {e}")
                
                return jsonify({
                    'success': True,
                    'message': 'OT escalada correctamente',
                    'ot': ot,
                    'grupo_anterior': resultado.get('grupo_anterior'),
                    'grupo_nuevo': resultado.get('grupo_nuevo')
                }), 200
            else:
                error_msg = resultado.get('message', 'Error al escalar OT')
                logging.error(f"❌ Error al escalar: {error_msg}")
                
                return jsonify({
                    'success': False,
                    'error': error_msg,
                    'ot': ot,
                    'detail': resultado.get('detail')
                }), 500
    
    except Exception as e:
        logging.error(f"❌ Error en API gestionar OT: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        
        return jsonify({
            'success': False,  # ← Siempre incluir este campo
            'error': f'Error interno del servidor: {str(e)}'
        }), 500
    
    finally:
        # Cerrar conexiones
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# ============================================
# API: ANILLOS COMPLETOS - TOPOLOGÍA
# ============================================

@app.route('/api/hl5/anillos-topologia', methods=['GET'])
@login_requerido
def obtener_anillos_topologia():
    """
    Obtiene la topología completa de todos los anillos con coordenadas.
    Implementa caché de 5 minutos para optimizar performance.
    """
    try:
        # Verificar si hay caché válido
        with cache_anillos['lock']:
            now = time.time()
            if (cache_anillos['datos'] is not None and 
                (now - cache_anillos['timestamp']) < cache_anillos['ttl']):
                logging.info("✅ Retornando anillos desde caché")
                return jsonify({
                    'success': True,
                    'anillos': cache_anillos['datos'],
                    'timestamp': datetime.now().isoformat(),
                    'cached': True
                })
        
        logging.info("🔄 Cargando anillos desde base de datos...")
        
        # Conectar a PostgreSQL
        conn = get_postgres_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query principal
        query = """
        WITH anillos_coordenadas AS (
            SELECT 
                a.id,
                a.origen,
                a.destino,
                a.ip_origen,
                a.puerto_origen,
                a.ip_destino,
                a.puerto_destino,
                
                -- Coordenadas origen
                io.LATITUD as lat_origen,
                io.LONGITUD as lon_origen,
                io.MUNICIPIO as municipio_origen,
                io.DEPARTAMENTO as departamento_origen,
                io.CINUM as cinum_origen,
                
                -- Coordenadas destino
                id.LATITUD as lat_destino,
                id.LONGITUD as lon_destino,
                id.MUNICIPIO as municipio_destino,
                id.DEPARTAMENTO as departamento_destino,
                id.CINUM as cinum_destino,
                
                -- Tipo de anillo (extraído del nombre)
                CASE 
                    -- Anillos H5XX y N5XX
                    WHEN a.origen LIKE '%H501%' OR a.destino LIKE '%H501%' THEN 'H501'
                    WHEN a.origen LIKE '%N501%' OR a.destino LIKE '%N501%' THEN 'N501'
                    
                    -- Anillos H4XX y N4XX
                    WHEN a.origen LIKE '%H401%' OR a.destino LIKE '%H401%' THEN 'H401'
                    WHEN a.origen LIKE '%H402%' OR a.destino LIKE '%H402%' THEN 'H402'
                    WHEN a.origen LIKE '%N401%' OR a.destino LIKE '%N401%' THEN 'N401'
                    WHEN a.origen LIKE '%N402%' OR a.destino LIKE '%N402%' THEN 'N402'
                    
                    -- Anillos H3XX y N3XX
                    WHEN a.origen LIKE '%H301%' OR a.destino LIKE '%H301%' THEN 'H301'
                    WHEN a.origen LIKE '%H302%' OR a.destino LIKE '%H302%' THEN 'H302'
                    WHEN a.origen LIKE '%N301%' OR a.destino LIKE '%N301%' THEN 'N301'
                    WHEN a.origen LIKE '%N302%' OR a.destino LIKE '%N302%' THEN 'N302'
                    
                    ELSE 'OTRO'
                END as tipo_anillo
                
            FROM smartsoc.enlaces a
            
            -- Join con inventario_hlx para origen
            -- NOTA: Ajustar este JOIN según tu estructura de datos
            LEFT JOIN smartsoc.inventario_hlx io ON (
                io.CINUM = SUBSTRING(a.origen FROM '[A-Z]{3}_[A-Z0-9]+_[A-Z]+')
            )
            
            -- Join con inventario_hlx para destino
            LEFT JOIN smartsoc.inventario_hlx id ON (
                id.CINUM = SUBSTRING(a.destino FROM '[A-Z]{3}_[A-Z0-9]+_[A-Z]+')
            )
            
            WHERE a.origen IS NOT NULL 
            AND a.destino IS NOT NULL
            AND io.LATITUD IS NOT NULL 
            AND id.LATITUD IS NOT NULL
        ),
        aperturas_activas AS (
            -- Obtener aperturas activas desde MySQL
            SELECT DISTINCT
                TRIM(NODO_A) as nodo_a,
                TRIM(NODO_B) as nodo_b,
                AFECTA,
                INCIDENTE,
                OT,
                HORA_INICIO,
                HORAS
            FROM reportes.db_dash_seguimiento_anillos_fo
            WHERE REPORTTIME_FIN IS NULL
        )
        SELECT 
            ac.id,
            ac.origen,
            ac.destino,
            ac.ip_origen,
            ac.puerto_origen,
            ac.ip_destino,
            ac.puerto_destino,
            ac.lat_origen,
            ac.lon_origen,
            ac.lat_destino,
            ac.lon_destino,
            ac.municipio_origen,
            ac.municipio_destino,
            ac.departamento_origen,
            ac.departamento_destino,
            ac.cinum_origen,
            ac.cinum_destino,
            ac.tipo_anillo,
            COALESCE(
                CASE 
                    WHEN aa.AFECTA = 'SI' THEN 'AFECTACION'
                    WHEN aa.OT IS NOT NULL THEN 'TICKET'
                    ELSE 'NORMAL'
                END,
                'NORMAL'
            ) as estado,
            aa.AFECTA,
            aa.INCIDENTE,
            aa.OT,
            aa.HORA_INICIO,
            aa.HORAS
        FROM anillos_coordenadas ac
        LEFT JOIN aperturas_activas aa ON (
            (ac.origen = aa.nodo_a AND ac.destino = aa.nodo_b) OR
            (ac.origen = aa.nodo_b AND ac.destino = aa.nodo_a)
        )
        WHERE ac.tipo_anillo != 'OTRO'
        ORDER BY ac.tipo_anillo, ac.origen, ac.destino
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        # Organizar resultados por tipo de anillo
        anillos = {
            'H501': [],
            'H401': [],
            'H302': [],
            'H301': [],
            'H402': [], 
            'N501': [], 
            'N401': [], 
            'N402': [], 
            'N301': [], 
            'N302': []
        }
        
        for row in results:
            tipo_anillo = row['tipo_anillo']
            
            # Determinar estado final e info adicional
            info_ticket = None
            info_afectacion = None
            
            if row['estado'] == 'AFECTACION':
                info_afectacion = {
                    'incidente': row['incidente'],
                    'ot': row['ot'],
                    'hora_inicio': row['hora_inicio'].isoformat() if row['hora_inicio'] else None,
                    'horas': float(row['horas']) if row['horas'] else 0
                }
            elif row['estado'] == 'TICKET':
                info_ticket = {
                    'ot': row['ot'],
                    'hora_inicio': row['hora_inicio'].isoformat() if row['hora_inicio'] else None,
                    'horas': float(row['horas']) if row['horas'] else 0
                }
            
            segmento = {
                'id': row['id'],
                'origen': row['origen'],
                'destino': row['destino'],
                'ip_origen': row['ip_origen'],
                'puerto_origen': row['puerto_origen'],
                'ip_destino': row['ip_destino'],
                'puerto_destino': row['puerto_destino'],
                'coord_origen': {
                    'lat': float(row['lat_origen']) if row['lat_origen'] else None,
                    'lon': float(row['lon_origen']) if row['lon_origen'] else None
                },
                'coord_destino': {
                    'lat': float(row['lat_destino']) if row['lat_destino'] else None,
                    'lon': float(row['lon_destino']) if row['lon_destino'] else None
                },
                'municipio_origen': row['municipio_origen'],
                'municipio_destino': row['municipio_destino'],
                'departamento_origen': row['departamento_origen'],
                'departamento_destino': row['departamento_destino'],
                'cinum_origen': row['cinum_origen'],
                'cinum_destino': row['cinum_destino'],
                'estado': row['estado'],
                'info_ticket': info_ticket,
                'info_afectacion': info_afectacion
            }
            
            anillos[tipo_anillo].append(segmento)
        
        cursor.close()
        conn.close()
        
        # Guardar en caché
        with cache_anillos['lock']:
            cache_anillos['datos'] = anillos
            cache_anillos['timestamp'] = time.time()
        
        logging.info(f"✅ Anillos cargados: {sum(len(v) for v in anillos.values())} segmentos")
        
        return jsonify({
            'success': True,
            'anillos': anillos,
            'timestamp': datetime.now().isoformat(),
            'total_segmentos': sum(len(v) for v in anillos.values()),
            'cached': False
        })
        
    except Exception as e:
        logging.error(f"❌ Error en obtener_anillos_topologia: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/hl5/anillo/<tipo_anillo>', methods=['GET'])
@login_requerido
def obtener_anillo_especifico(tipo_anillo):
    """
    Obtiene la topología de un anillo específico (H501, H401, H302, H301).
    """
    try:
        # Validar tipo de anillo
        tipos_validos = [
            'H501', 'H401', 'H402', 'H301', 'H302',  # Tipo H
            'N501', 'N401', 'N402', 'N301', 'N302'   # Tipo N
        ]
        if tipo_anillo.upper() not in tipos_validos:
            return jsonify({
                'success': False,
                'error': f'Tipo de anillo no válido. Use: {", ".join(tipos_validos)}'
            }), 400
        
        # Obtener todos los anillos (con caché)
        response = obtener_anillos_topologia()
        data = response.get_json()
        
        if data['success']:
            anillo_data = data['anillos'].get(tipo_anillo.upper(), [])
            return jsonify({
                'success': True,
                'tipo_anillo': tipo_anillo.upper(),
                'segmentos': anillo_data,
                'total_segmentos': len(anillo_data),
                'timestamp': datetime.now().isoformat()
            })
        else:
            return response
            
    except Exception as e:
        logging.error(f"❌ Error en obtener_anillo_especifico: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/hl5/anillos-cache-refresh', methods=['POST'])
@login_requerido
def refrescar_cache_anillos():
    """
    Refresca manualmente el caché de anillos.
    """
    try:
        with cache_anillos['lock']:
            cache_anillos['datos'] = None
            cache_anillos['timestamp'] = 0
        
        logging.info("🔄 Caché de anillos limpiado")
        
        # Forzar recarga
        response = obtener_anillos_topologia()
        
        return jsonify({
            'success': True,
            'message': 'Caché refrescado exitosamente',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logging.error(f"❌ Error refrescando caché: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================
# CÓDIGO PARA AGREGAR AL FINAL DE app.py
# (Antes de la línea: if __name__ == '__main__':)
# ============================================

@app.route('/api/hl5/afectados-con-brazos', methods=['GET'])
@login_requerido
def api_hl5_afectados_con_brazos():
    """
    Obtiene los HL5 con tickets activos y sus brazos alarmados.
    
    ACTUALIZADO: Incluye COD_UBICA e IP
    """
    
    mysql_conn = None
    pg_conn = None
    
    try:
        # Conectar a MySQL
        mysql_conn = get_mysql_connection()
        mysql_cursor = mysql_conn.cursor(dictionary=True)
        
        # Conectar a PostgreSQL
        pg_conn = get_postgres_connection()
        pg_cursor = pg_conn.cursor()
        
        # 1. Obtener HL5 con tickets activos de MySQL
        # IMPORTANTE: Incluir COD_UBICA e IP si existen
        query_hl5_tickets = """
        SELECT
            HORA_INICIO,
            NODE,
            CINUM,
            CINAME,
            COD_UBICA,
            CIUDAD,
            DEPARTAMENTO,
            LATITUD,
            LONGITUD,
            MAXIMO,
            OT,
            ESTADO_OT,
            GRUPO_OT,
            FECHA_AVANCE,
            AVANCE,
            DIAS,
            HORAS,
            FALLA_FO,
            OT_FO,
            ANILLO
        FROM reportes.db_dash_rose_hl5_ots
        WHERE ESTADO_OT NOT IN ('COMP', 'CLOSE', 'CANCEL')
          AND CINUM IS NOT NULL
        ORDER BY HORAS DESC
        """
        
        mysql_cursor.execute(query_hl5_tickets)
        hl5_con_tickets = mysql_cursor.fetchall()
        
        logging.info(f"📊 HL5 con tickets activos encontrados: {len(hl5_con_tickets)}")
        
        # Lista para almacenar todos los HL5 afectados
        hl5_afectados = []
        
        # 2. Para cada HL5 con ticket
        for idx, hl5 in enumerate(hl5_con_tickets):
            cinum_alarmado = hl5['CINUM']
            
            logging.info(f"🔍 [{idx+1}/{len(hl5_con_tickets)}] Procesando CINUM: {cinum_alarmado}")
            
            # Buscar brazos para este CINUM
            query_brazos = """
            SELECT 
                a.origen,
                a.sitio_org,
                a.ip_origen,
                a.puerto_origen,
                a.destino,
                a.sitio_dest,
                a.ip_destino,
                a.puerto_destino
            FROM smartsoc.enlaces a
            WHERE a.origen = %s OR a.destino = %s
            """
            
            pg_cursor.execute(query_brazos, (cinum_alarmado, cinum_alarmado))
            brazos = pg_cursor.fetchall()
            
            # Lista para almacenar brazos con coordenadas
            brazos_con_coordenadas = []
            
            if brazos:
                logging.info(f"   ✅ Encontrados {len(brazos)} brazos para CINUM: {cinum_alarmado}")
                
                # 3. Para cada brazo, obtener coordenadas
                for brazo_idx, brazo in enumerate(brazos):
                    cinum_origen = brazo[0]
                    sitio_origen = brazo[1]  # NUEVO
                    ip_origen = brazo[2]
                    puerto_origen = brazo[3]
                    cinum_destino = brazo[4]
                    sitio_destino = brazo[5]  # NUEVO
                    ip_destino = brazo[6]
                    puerto_destino = brazo[7]
                    
                    logging.info(f"   🔗 Brazo {brazo_idx+1}: {cinum_origen} â†' {cinum_destino}")
                    
                    # Obtener coordenadas del origen (NOMBRES EN MAYÃšSCULAS)
                    query_coords_origen = """
                    SELECT "LATITUD", "LONGITUD", "CINUM", "DESCRIPTION"
                    FROM smartsoc.inventario_hlx
                    WHERE "CINUM" = %s
                    LIMIT 1
                    """
                    pg_cursor.execute(query_coords_origen, (cinum_origen,))
                    coords_origen = pg_cursor.fetchone()
                    
                    # Obtener coordenadas del destino (NOMBRES EN MAYÃšSCULAS)
                    query_coords_destino = """
                    SELECT "LATITUD", "LONGITUD", "CINUM", "DESCRIPTION"
                    FROM smartsoc.inventario_hlx
                    WHERE "CINUM" = %s
                    LIMIT 1
                    """
                    pg_cursor.execute(query_coords_destino, (cinum_destino,))
                    coords_destino = pg_cursor.fetchone()
                    
                    # Validar coordenadas
                    if not coords_origen or not coords_origen[0] or not coords_origen[1]:
                        logging.warning(f"      ⚠️  Sin coordenadas vÃ¡lidas para origen: {cinum_origen}")
                        continue
                        
                    if not coords_destino or not coords_destino[0] or not coords_destino[1]:
                        logging.warning(f"      ⚠️  Sin coordenadas vÃ¡lidas para destino: {cinum_destino}")
                        continue
                    
                    logging.info(f"      ✅ Coordenadas OK para ambos nodos")
                    
                    # Estrategia: 
                    # 1. Verificar primero en db_dash_rose_hl5_ots (si está ahí → DOWN con ticket activo)
                    # 2. Si no está, verificar en db_dash_seguimiento_anillos_fo
                    # 3. Si no está en ninguna → UP (por defecto)
                    
                    estado_origen = {'status': 'UP', 'ot': None, 'fuente': 'default'}
                    
                    # PASO 1: Verificar en tabla de tickets activos HL5
                    query_hl5_ots_origen = """
                    SELECT CINUM, OT, ESTADO_OT, HORAS, DIAS
                    FROM reportes.db_dash_rose_hl5_ots
                    WHERE TRIM(CINUM) = %s
                      AND ESTADO_OT NOT IN ('COMP', 'CLOSE', 'CANCEL')
                    LIMIT 1
                    """
                    try:
                        mysql_cursor.execute(query_hl5_ots_origen, (cinum_origen,))
                        ticket_origen = mysql_cursor.fetchone()
                        if ticket_origen:
                            # Si está en HL5_OTS → tiene ticket activo → DOWN
                            estado_origen['status'] = 'DOWN'
                            estado_origen['ot'] = ticket_origen['OT']
                            estado_origen['fuente'] = 'hl5_ots'
                            logging.info(f"      ✅ [HL5_OTS] Estado origen {cinum_origen}: DOWN (OT: {ticket_origen['OT']})")
                        else:
                            # PASO 2: Si no está en HL5_OTS, verificar en tabla de seguimiento
                            query_seguimiento_origen = """
                            SELECT NODO_A_STATUS, NODO_B_STATUS, OT, NODO_A, NODO_B
                            FROM reportes.db_dash_seguimiento_anillos_fo
                            WHERE (TRIM(NODO_A) = %s OR TRIM(NODO_B) = %s)
                            LIMIT 1
                            """
                            mysql_cursor.execute(query_seguimiento_origen, (cinum_origen, cinum_origen))
                            resultado_origen = mysql_cursor.fetchone()
                            if resultado_origen:
                                # Determinar si es NODO_A o NODO_B
                                if resultado_origen['NODO_A'] and resultado_origen['NODO_A'].strip() == cinum_origen:
                                    estado_origen['status'] = resultado_origen['NODO_A_STATUS'] or 'UP'
                                elif resultado_origen['NODO_B'] and resultado_origen['NODO_B'].strip() == cinum_origen:
                                    estado_origen['status'] = resultado_origen['NODO_B_STATUS'] or 'UP'
                                estado_origen['ot'] = resultado_origen['OT']
                                estado_origen['fuente'] = 'seguimiento_fo'
                                logging.info(f"      ✅ [SEGUIMIENTO] Estado origen {cinum_origen}: {estado_origen['status']}")
                            else:
                                # No está en ninguna tabla → UP por defecto
                                estado_origen['status'] = 'UP'
                                logging.info(f"      ✅ Estado origen {cinum_origen}: UP (no encontrado en tablas)")
                    except Exception as e:
                        logging.warning(f"      ❌ Error al verificar estado origen: {str(e)}")
                        estado_origen['status'] = 'UNKNOWN'
                    
                    # VALIDACIÓN DE ESTADO PARA DESTINO
                    estado_destino = {'status': 'UP', 'ot': None, 'fuente': 'default'}
                    
                    # PASO 1: Verificar en tabla de tickets activos HL5
                    query_hl5_ots_destino = """
                    SELECT CINUM, OT, ESTADO_OT, HORAS, DIAS
                    FROM reportes.db_dash_rose_hl5_ots
                    WHERE TRIM(CINUM) = %s
                      AND ESTADO_OT NOT IN ('COMP', 'CLOSE', 'CANCEL')
                    LIMIT 1
                    """
                    try:
                        mysql_cursor.execute(query_hl5_ots_destino, (cinum_destino,))
                        ticket_destino = mysql_cursor.fetchone()
                        if ticket_destino:
                            # Si está en HL5_OTS → tiene ticket activo → DOWN
                            estado_destino['status'] = 'DOWN'
                            estado_destino['ot'] = ticket_destino['OT']
                            estado_destino['fuente'] = 'hl5_ots'
                            logging.info(f"      ✅ [HL5_OTS] Estado destino {cinum_destino}: DOWN (OT: {ticket_destino['OT']})")
                        else:
                            # PASO 2: Si no está en HL5_OTS, verificar en tabla de seguimiento
                            query_seguimiento_destino = """
                            SELECT NODO_A_STATUS, NODO_B_STATUS, OT, NODO_A, NODO_B
                            FROM reportes.db_dash_seguimiento_anillos_fo
                            WHERE (TRIM(NODO_A) = %s OR TRIM(NODO_B) = %s)
                            LIMIT 1
                            """
                            mysql_cursor.execute(query_seguimiento_destino, (cinum_destino, cinum_destino))
                            resultado_destino = mysql_cursor.fetchone()
                            if resultado_destino:
                                # Determinar si es NODO_A o NODO_B
                                if resultado_destino['NODO_A'] and resultado_destino['NODO_A'].strip() == cinum_destino:
                                    estado_destino['status'] = resultado_destino['NODO_A_STATUS'] or 'UP'
                                elif resultado_destino['NODO_B'] and resultado_destino['NODO_B'].strip() == cinum_destino:
                                    estado_destino['status'] = resultado_destino['NODO_B_STATUS'] or 'UP'
                                estado_destino['ot'] = resultado_destino['OT']
                                estado_destino['fuente'] = 'seguimiento_fo'
                                logging.info(f"      ✅ [SEGUIMIENTO] Estado destino {cinum_destino}: {estado_destino['status']}")
                            else:
                                # No está en ninguna tabla → UP por defecto
                                estado_destino['status'] = 'UP'
                                logging.info(f"      ⚠️ Estado destino {cinum_destino}: UP (no encontrado en tablas)")
                    except Exception as e:
                        logging.warning(f"      ❌ Error al verificar estado destino: {str(e)}")
                        estado_destino['status'] = 'UNKNOWN'
                    
                    # Agregar brazo con coordenadas y estado
                    brazos_con_coordenadas.append({
                        'origen': cinum_origen,
                        'origen_sitio': sitio_origen if sitio_origen else cinum_origen,  # NUEVO
                        'origen_description': coords_origen[3] if coords_origen[3] else cinum_origen,
                        'origen_status': estado_origen['status'],  # NUEVO
                        'origen_ot': estado_origen['ot'],  # NUEVO
                        'ip_origen': ip_origen,
                        'puerto_origen': puerto_origen,
                        'lat_origen': float(coords_origen[0]),
                        'lon_origen': float(coords_origen[1]),
                        'destino': cinum_destino,
                        'destino_sitio': sitio_destino if sitio_destino else cinum_destino,  # NUEVO
                        'destino_description': coords_destino[3] if coords_destino[3] else cinum_destino,
                        'destino_status': estado_destino['status'],  # NUEVO
                        'destino_ot': estado_destino['ot'],  # NUEVO
                        'ip_destino': ip_destino,
                        'puerto_destino': puerto_destino,
                        'lat_destino': float(coords_destino[0]),
                        'lon_destino': float(coords_destino[1]),
                        'es_alarmado_origen': (cinum_origen == cinum_alarmado)
                    })

            else:
                logging.warning(f"   ⚠️ No se encontraron brazos para CINUM: {cinum_alarmado}")
            
            # IMPORTANTE: Agregar el HL5 SIEMPRE, con o sin brazos
            if hl5['LATITUD'] and hl5['LONGITUD']:
                # Intentar obtener IP desde PostgreSQL si no viene en MySQL
                ip_hl5 = None
                
                # Si el HL5 no tiene IP en MySQL, buscar en inventario_hlx
                if not ip_hl5:
                    query_ip_hlx = """
                    SELECT "IP"
                    FROM smartsoc.inventario_hlx
                    WHERE "CINUM" = %s
                    LIMIT 1
                    """
                    try:
                        pg_cursor.execute(query_ip_hlx, (cinum_alarmado,))
                        ip_result = pg_cursor.fetchone()
                        if ip_result and ip_result[0]:
                            ip_hl5 = ip_result[0]
                    except Exception as e:
                        logging.warning(f"   ⚠️ No se pudo obtener IP de inventario_hlx: {str(e)}")
                
                hl5_afectados.append({
                    'nodo_alarmado': hl5['NODE'],
                    'cinum': cinum_alarmado,
                    'ciname': hl5['CINAME'],
                    'cod_ubica': hl5['COD_UBICA'],  # â† NUEVO
                    'ip': ip_hl5,  # â† NUEVO (puede ser None si no existe)
                    'hora_inicio': hl5['HORA_INICIO'].isoformat() if hl5['HORA_INICIO'] else None,
                    'ciudad': hl5['CIUDAD'],
                    'departamento': hl5['DEPARTAMENTO'],
                    'latitud': float(hl5['LATITUD']),
                    'longitud': float(hl5['LONGITUD']),
                    'ot': hl5['OT'],
                    'estado_ot': hl5['ESTADO_OT'],
                    'grupo_ot': hl5['GRUPO_OT'],
                    'avance': hl5['AVANCE'],
                    'horas': float(hl5['HORAS']) if hl5['HORAS'] else 0,
                    'dias': int(hl5['DIAS']) if hl5['DIAS'] else 0,
                    'falla_fo': hl5['FALLA_FO'],
                    'ot_fo': hl5['OT_FO'],
                    'anillo': (hl5.get('ANILLO') or '').strip().strip('[]').strip(),
                    'brazos': brazos_con_coordenadas
                })
                
                if brazos_con_coordenadas:
                    logging.info(f"   ✅ HL5 agregado con {len(brazos_con_coordenadas)} brazos")
                else:
                    logging.info(f"   ✅ HL5 agregado SIN brazos (solo punto)")
            else:
                logging.warning(f"   ❌ HL5 sin coordenadas en MySQL, no se puede pintar")
        
        logging.info(f"✅ Total HL5 afectados procesados: {len(hl5_afectados)}")
        
        return jsonify({
            'success': True,
            'hl5_afectados': hl5_afectados,
            'total': len(hl5_afectados),
            'total_tickets': len(hl5_con_tickets),
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        logging.error(f"❌ Error en api_hl5_afectados_con_brazos: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e),
            'hl5_afectados': [],
            'total': 0
        }), 500
    
    finally:
        if mysql_conn:
            mysql_cursor.close()
            mysql_conn.close()
        if pg_conn:
            pg_cursor.close()
            pg_conn.close()

# ============================================
# RUTA: TRABAJOS PROGRAMADOS
# ============================================
@app.route('/trabajos_programados', methods=['GET', 'POST'])
@login_requerido
@permiso_requerido('trabajos_programados')
def route_trabajos_programados():
    """Ruta para la página de Trabajos Programados"""
    from routes_trabajos_programados import trabajos_programados  # ← Import aquí dentro
    return trabajos_programados()

# ============================================
# RUTAS N1 - Monitoreo N1 | SmartSOC
# Agregar en app.py
# ============================================

# ---- Página N1 ----
@app.route('/n1')
@login_requerido
@permiso_requerido('n1')   # ← Descomenta si agregas permiso en config_permisos.py
def n1():
    return render_template('n1.html')


# ---- API: Retención HL5 ----
@app.route('/api/n1/retencion_hl5')
@login_requerido
def api_n1_retencion_hl5():
    """
    Retorna los casos activos de Retención de HL5.
    Fuente: PostgreSQL → esquema public → tabla gestion_ot_hl5
    """
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_POSTGRES_114_HOST,
            database=DB_POSTGRES_114_DB_CG,
            user=DB_POSTGRES_114_USER,
            password=DB_POSTGRES_114_PASSWORD,
            port=5432
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT
                ticketid_hl5        AS "INCIDENTE",
                cinum_hl5       AS "NODO",
                ip_hl5          AS "IP",
                cilocation_hl5  AS "UBICACION",
                resumen_hl5     AS "RESUMEN",
                fecha_inicio_falla_hl5  AS "FECHA_INICIO",
                ot_hl5          AS "OT",
                ot_estado_hl5   AS "ESTADO_OT",
                gestion_ot      AS "TIPO_RETENCION"
            FROM public.gestion_ot_hl5
            where 
            ticketid_hl5 not in (select ticketid_hl5 from gestion_ot_hl5 where gestion_ot in ('Ot closed-Inc resolve- responde Ping','Ot closed - responde Ping','Escalado a Campo','Escalado a campo'))
            order by fecha_inicio_falla_hl5 DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        datos = []
        for row in rows:
            d = {}
            for col, val in row.items():
                # Convertir tipos no serializables a str/float
                if val is None:
                    d[col] = None
                elif hasattr(val, 'isoformat'):
                    d[col] = val.strftime('%d/%m/%Y %H:%M:%S') if hasattr(val, 'strftime') else str(val)
                else:
                    d[col] = val
            datos.append(d)

        return jsonify({'success': True, 'datos': datos, 'total': len(datos)})

    except Exception as e:
        logging.error(f"Error api_n1_retencion_hl5: {e}")
        return jsonify({'success': False, 'error': str(e), 'datos': []})
    finally:
        if conn:
            conn.close()

# ---- API: Stats Retención HL5 ----
@app.route('/api/n1/stats_retencion_hl5')
@login_requerido
def api_n1_stats_retencion_hl5():
    """
    Retorna conteos de gestion_ot_hl5:
      - cerradas   : OTs con gestion_ot en (closed)
      - escaladas  : OTs con gestion_ot = Escalado a Campo
      - retencion  : OTs activas en seguimiento/retencion
    """
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_POSTGRES_114_HOST,
            database=DB_POSTGRES_114_DB_CG,
            user=DB_POSTGRES_114_USER,
            password=DB_POSTGRES_114_PASSWORD,
            port=5432
        )
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(DISTINCT ticketid_hl5)
            FROM gestion_ot_hl5
            WHERE gestion_ot IN (
                'Ot closed-Inc resolve- responde Ping',
                'Ot closed - responde Ping'
            )
        """)
        cerradas = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(DISTINCT ticketid_hl5)
            FROM gestion_ot_hl5
            WHERE gestion_ot = 'Escalado a Campo'
        """)
        escaladas = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(DISTINCT ticketid_hl5)
            FROM gestion_ot_hl5
            WHERE ticketid_hl5 NOT IN (
                SELECT ticketid_hl5 FROM gestion_ot_hl5
                WHERE gestion_ot IN (
                    'Ot closed-Inc resolve- responde Ping',
                    'Ot closed - responde Ping',
                    'Escalado a Campo'
                )
            )
            AND gestion_ot IN (
                'retencion-ping',
                'retencion-ot movil',
                'seguimiento- sin inc relacionado',
                'seguimiento - escalar a campo'
            )
        """)
        retencion = cursor.fetchone()[0] or 0

        return jsonify({
            'success': True,
            'cerradas':  int(cerradas),
            'escaladas': int(escaladas),
            'retencion': int(retencion)
        })

    except Exception as e:
        logging.error(f"Error api_n1_stats_retencion_hl5: {e}")
        return jsonify({'success': False, 'error': str(e),
                        'cerradas': 0, 'escaladas': 0, 'retencion': 0})
    finally:
        if conn:
            conn.close()


# ---- API: Performance Red Fusión ----
@app.route('/api/n1/performance_fusion')
@login_requerido
def api_n1_performance_fusion():
    """
    Retorna los casos activos de Performance de la Red Fusión.
    """
    conn = None
    try:
        #dsn = cx_Oracle.makedsn(DB_MAXIMO_HOST, DB_MAXIMO_PORT, service_name=DB_MAXIMO_SERVICE_NAME)
	    #conn=cx_Oracle.connect(DB_MAXIMO_USER, DB_MAXIMO_PASSWORD, dsn,encoding= 'UTF-8')
        conn = cx_Oracle.connect(
            user=DB_MAXIMO_USER,
            password=DB_MAXIMO_PASSWORD,
            dsn=DB_MAXIMO_DSN,
            encoding='UTF-8'
        )
        cursor = conn.cursor()

        query = """
            SELECT
                I.TICKETID                                          AS INCIDENTE,
                MAX(I.DESCRIPTION)                                      AS RESUMEN,
                TO_CHAR(MAX(I.AFFECTEDSTART), 'DD/MM/YYYY HH24:MI:SS')  AS FECHA_INICIO,
                MAX(I.STATUS)                                            AS ESTADO,
                MAX(W.WONUM)                                             AS OT,
                MAX(W.STATUS)                                           AS ESTADO_OT,
                MAX(W.OWNERGROUP)                                       AS GRUPO_OT
            FROM MAXIMO.INCIDENT I
            LEFT JOIN MAXIMO.RELATEDRECORD RR
                ON RR.RELATEDRECKEY = I.TICKETID
               AND RR.RELATEDRECCLASS = 'INCIDENT'
            LEFT JOIN MAXIMO.WORKORDER W
                ON W.WONUM = RR.RECORDKEY
               AND W.STATUS NOT IN ('CAN','CANCEL')
            LEFT JOIN MAXIMO.LONGDESCRIPTION TEXTID
                ON TEXTID.LDKEY = I.TICKETUID
            WHERE
                I.EXTERNALSYSTEM       IN ('CENTROGESTION_FX')
                AND I.DESCRIPTION_CLASS IN ('FALLAS \\ PERFORMANCE')
                AND I.STATUS            IN ('ESCALADE')
                -- AND I.AFFECTEDSTART     >= TRUNC(SYSDATE)
                AND I.IDBLOCK           IN ('MASIVO')
                AND I.BLOCK              = 'ACCESO_FIJO_PLATAFORMA_E2E_HUAWEI'
                AND W.STATUS             = 'INPRG'
                AND W.OWNERGROUP = 'BACKOFFICE_N1'
            GROUP BY I.TICKETID
            ORDER BY INCIDENTE DESC
        """

        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

        datos = []
        for row in rows:
            d = {}
            for i, col in enumerate(columns):
                val = row[i]
                if hasattr(val, '__float__'):
                    val = float(val)
                elif val is None:
                    val = None
                d[col] = val
            datos.append(d)

        return jsonify({'success': True, 'datos': datos, 'total': len(datos)})

    except Exception as e:
        logging.error(f"Error api_n1_performance_fusion: {e}")
        return jsonify({'success': False, 'error': str(e), 'datos': []})
    finally:
        if conn:
            conn.close()

# ---- API: IPTV Calicux ----
@app.route('/api/n1/iptv_calicux')
@login_requerido
def api_n1_iptv_calicux():
    """
    Retorna los casos activos de IPTV Calicux.
    """
    conn = None
    try:
        #dsn = cx_Oracle.makedsn(DB_MAXIMO_HOST, DB_MAXIMO_PORT, service_name=DB_MAXIMO_SERVICE_NAME)
	    #conn=cx_Oracle.connect(DB_MAXIMO_USER, DB_MAXIMO_PASSWORD, dsn,encoding= 'UTF-8')
        conn = cx_Oracle.connect(
            user=DB_MAXIMO_USER,
            password=DB_MAXIMO_PASSWORD,
            dsn=DB_MAXIMO_DSN,
            encoding='UTF-8'
        )
        cursor = conn.cursor()

        query = """
            SELECT
                I.TICKETID                                          AS INCIDENTE,
                MAX(I.DESCRIPTION)                                  AS RESUMEN,
                TO_CHAR(MAX(I.AFFECTEDSTART), 'DD/MM/YYYY HH24:MI:SS') AS FECHA_INICIO,
                MAX(I.STATUS)                                       AS ESTADO,
                MAX(W.WONUM)                                        AS OT,
                MAX(W.STATUS)                                       AS ESTADO_OT,
                MAX(W.OWNERGROUP)                                   AS GRUPO_OT
            FROM MAXIMO.INCIDENT I
            JOIN MAXIMO.RELATEDRECORD RR
                ON RR.RELATEDRECKEY = I.TICKETID
               AND RR.RELATEDRECCLASS = 'INCIDENT'
            JOIN MAXIMO.WORKORDER W
                ON W.WONUM = RR.RECORDKEY
               AND W.STATUS NOT IN ('CAN', 'CANCEL')
            WHERE
                I.EXTERNALSYSTEM       IN ('CENTROGESTION_FX')
                AND I.DESCRIPTION_CLASS IN ('FALLAS \\ PERFORMANCE')
                AND I.STATUS            IN ('ESCALADE')
                -- AND I.AFFECTEDSTART     >= TRUNC(SYSDATE)
                AND I.IDBLOCK           IN ('GRAFANA_SOC_persistencia')
                AND I.BLOCK              = 'ACCESO_FIJO_PLATAFORMA_E2E_HUAWEI'
                AND W.OWNERGROUP         = 'BACKOFFICE_N1'
                AND W.STATUS             = 'INPRG'
            GROUP BY I.TICKETID
            ORDER BY INCIDENTE DESC
        """

        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

        datos = []
        for row in rows:
            d = {}
            for i, col in enumerate(columns):
                val = row[i]
                if hasattr(val, '__float__'):
                    val = float(val)
                elif val is None:
                    val = None
                d[col] = val
            datos.append(d)

        return jsonify({'success': True, 'datos': datos, 'total': len(datos)})

    except Exception as e:
        logging.error(f"Error api_n1_iptv_calicux: {e}")
        return jsonify({'success': False, 'error': str(e), 'datos': []})
    finally:
        if conn:
            conn.close()

# ---- API: Bandeja Backoffice ----
@app.route('/api/n1/bandeja_backoffice')
@login_requerido
def api_n1_bandeja_backoffice():
    """
    Retorna todas las OT's en bandeja de Backoffice N1.
    La categorización por IDBLOCK se hace en el frontend.
    """
    conn = None
    try:
        #dsn = cx_Oracle.makedsn(DB_MAXIMO_HOST, DB_MAXIMO_PORT, service_name=DB_MAXIMO_SERVICE_NAME)
	    #conn=cx_Oracle.connect(DB_MAXIMO_USER, DB_MAXIMO_PASSWORD, dsn,encoding= 'UTF-8')
        conn = cx_Oracle.connect(
            user=DB_MAXIMO_USER,
            password=DB_MAXIMO_PASSWORD,
            dsn=DB_MAXIMO_DSN,
            encoding='UTF-8'
        )
        cursor = conn.cursor()

        query = """
            SELECT
                I.TICKETID                                              AS INCIDENTE,
                MAX(I.DESCRIPTION)                                      AS RESUMEN,
                TO_CHAR(MAX(I.AFFECTEDSTART), 'DD/MM/YYYY HH24:MI:SS') AS FECHA_INICIO,
                MAX(I.STATUS)                                           AS ESTADO,
                MAX(W.WONUM)                                            AS OT,
                MAX(W.STATUS)                                           AS ESTADO_OT,
                MAX(W.OWNERGROUP)                                       AS GRUPO_OT,
                MAX(I.IDBLOCK)                                          AS IDBLOCK
            FROM MAXIMO.INCIDENT I
            JOIN MAXIMO.RELATEDRECORD RR
                ON RR.RELATEDRECKEY = I.TICKETID
               AND RR.RELATEDRECCLASS = 'INCIDENT'
            JOIN MAXIMO.WORKORDER W
                ON W.WONUM = RR.RECORDKEY
               AND W.STATUS NOT IN ('CAN', 'CANCEL')
            WHERE
                I.EXTERNALSYSTEM       IN ('CENTROGESTION_FX')
                AND I.DESCRIPTION_CLASS IN ('FALLAS \\ PERFORMANCE')
                AND I.STATUS            IN ('ESCALADE')
                AND W.OWNERGROUP         = 'BACKOFFICE_N1'
                AND W.STATUS             = 'INPRG'
            GROUP BY I.TICKETID
            ORDER BY INCIDENTE DESC
        """

        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

        datos = []
        for row in rows:
            d = {}
            for i, col in enumerate(columns):
                val = row[i]
                if hasattr(val, '__float__'):
                    val = float(val)
                elif val is None:
                    val = None
                d[col] = val
            datos.append(d)

        return jsonify({'success': True, 'datos': datos, 'total': len(datos)})

    except Exception as e:
        logging.error(f"Error api_n1_bandeja_backoffice: {e}")
        return jsonify({'success': False, 'error': str(e), 'datos': []})
    finally:
        if conn:
            conn.close()


# ============================================
# ---- API: Panel Anillos Afectados ----
@app.route('/api/hl5/anillos-panel', methods=['GET'])
@login_requerido
def api_hl5_anillos_panel():
    """
    Panel lateral: anillos afectados con su topología marcada.
    Combina aperturas (MySQL) + HL5 OTS (MySQL) + topología (PostgreSQL).
    """
    mysql_conn = None
    pg_conn = None
    try:
        mysql_conn = get_mysql_connection()
        mysql_cursor = mysql_conn.cursor(dictionary=True)
        pg_conn = get_postgres_connection()
        pg_cursor = pg_conn.cursor(cursor_factory=RealDictCursor)

        # 1. Brazos afectados (cabecera/anillo)
        mysql_cursor.execute("""
            SELECT NODO_A, NODO_B, TIPO_APERTURA, ANILLO,
                   OT, HORAS, ESTADO_OT, NODO_A_STATUS, NODO_B_STATUS
            FROM reportes.db_dash_seguimiento_anillos_fo
            WHERE ESTADO_OT NOT IN ('COMP', 'CLOSE', 'CANCEL')
              AND ANILLO IS NOT NULL AND TRIM(ANILLO) != ''
        """)
        aperturas = mysql_cursor.fetchall()

        # 2. Nodos HL5 afectados
        mysql_cursor.execute("""
            SELECT CINUM, NODE, ANILLO, OT, HORAS, ESTADO_OT, CINAME
            FROM reportes.db_dash_rose_hl5_ots
            WHERE ESTADO_OT NOT IN ('COMP', 'CLOSE', 'CANCEL')
              AND CINUM IS NOT NULL
              AND ANILLO IS NOT NULL AND TRIM(ANILLO) != ''
        """)
        hl5_lista = mysql_cursor.fetchall()

        def limpiar_anillo(raw):
            return (raw or '').strip().strip('[]').strip()

        # 3. Agrupar por anillo
        anillos_map = {}

        for ap in aperturas:
            nombre = limpiar_anillo(ap['ANILLO'])
            if not nombre:
                continue
            if nombre not in anillos_map:
                anillos_map[nombre] = {'tipos': set(), 'aperturas': [], 'hl5': []}
            anillos_map[nombre]['tipos'].add(ap['TIPO_APERTURA'])
            anillos_map[nombre]['aperturas'].append({
                'nodo_a': (ap['NODO_A'] or '').strip(),
                'nodo_b': (ap['NODO_B'] or '').strip(),
                'tipo': ap['TIPO_APERTURA'],
                'ot': ap['OT'],
                'horas': float(ap['HORAS']) if ap['HORAS'] else 0,
                'estado_ot': ap['ESTADO_OT'],
                'status_a': ap['NODO_A_STATUS'],
                'status_b': ap['NODO_B_STATUS'],
            })

        for hl5 in hl5_lista:
            nombre = limpiar_anillo(hl5['ANILLO'])
            if not nombre:
                continue
            if nombre not in anillos_map:
                anillos_map[nombre] = {'tipos': set(), 'aperturas': [], 'hl5': []}
            anillos_map[nombre]['tipos'].add('HL5')
            anillos_map[nombre]['hl5'].append({
                'cinum': (hl5['CINUM'] or '').strip(),
                'node': hl5['NODE'],
                'ciname': hl5['CINAME'],
                'ot': hl5['OT'],
                'horas': float(hl5['HORAS']) if hl5['HORAS'] else 0,
                'estado_ot': hl5['ESTADO_OT'],
            })

        # 4. Topología desde PostgreSQL + marcar afectados
        resultado = []
        for nombre_anillo, datos in anillos_map.items():
            pg_cursor.execute("""
                SELECT id, interface, device_origen, device_destino,
                       speed_bps, ip_origen, ip_destino,
                       depto_origen, mun_origen, sit_description_origen,
                       depto_destino, mun_destino, sit_description_destino
                FROM smartsoc.inventario_anillo_bh_fusion
                WHERE anillo = %s
                ORDER BY id
            """, (nombre_anillo,))
            topo_rows = pg_cursor.fetchall()

            topologia = []
            for row in topo_rows:
                link = dict(row)
                orig = (link['device_origen'] or '').strip()
                dest = (link['device_destino'] or '').strip()
                link['afectado'] = False
                link['tipo_afectacion'] = None
                link['ot_afectacion'] = None
                link['horas_afectacion'] = None
                link['nodo_hl5_afectado'] = None

                # Verificar brazo afectado
                for ap in datos['aperturas']:
                    na, nb = ap['nodo_a'], ap['nodo_b']
                    if (orig == na and dest == nb) or (orig == nb and dest == na):
                        link['afectado'] = True
                        link['tipo_afectacion'] = ap['tipo']
                        link['ot_afectacion'] = ap['ot']
                        link['horas_afectacion'] = ap['horas']
                        break

                # Verificar HL5 en nodos del enlace
                for hl5 in datos['hl5']:
                    cinum = hl5['cinum']
                    if orig == cinum or dest == cinum:
                        link['afectado'] = True
                        link['nodo_hl5_afectado'] = cinum
                        if not link['tipo_afectacion']:
                            link['tipo_afectacion'] = 'HL5'
                        link['ot_afectacion'] = link['ot_afectacion'] or hl5['ot']
                        link['horas_afectacion'] = link['horas_afectacion'] or hl5['horas']
                        break

                # Convertir Decimal a float para JSON
                if link.get('horas_afectacion') and hasattr(link['horas_afectacion'], '__float__'):
                    link['horas_afectacion'] = float(link['horas_afectacion'])

                topologia.append(link)

            resultado.append({
                'anillo': nombre_anillo,
                'tipos_afectacion': list(datos['tipos']),
                'total_aperturas': len(datos['aperturas']),
                'total_hl5': len(datos['hl5']),
                'aperturas': datos['aperturas'],
                'hl5': datos['hl5'],
                'topologia': topologia,
                'tiene_topologia': len(topologia) > 0
            })

        resultado.sort(key=lambda x: (
            len(x['tipos_afectacion']),
            x['total_aperturas'] + x['total_hl5']
        ), reverse=True)

        return jsonify({
            'success': True,
            'anillos_afectados': resultado,
            'total': len(resultado)
        })

    except Exception as e:
        logging.error(f"Error api_hl5_anillos_panel: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e),
            'anillos_afectados': []
        }), 500
    finally:
        if mysql_conn:
            mysql_conn.close()
        if pg_conn:
            pg_conn.close()

# ================================================================
# Grafica historico hl5 por departamento
# ================================================================

@app.route('/api/hl5/historico-departamento-debug')
def api_hl5_historico_departamento_debug():
    """
    Histórico de afectación HL5 agrupado por departamento.

    Parámetros de query-string:
      horas        -> 12 (default) | 24
      departamento -> nombre exacto del departamento (opcional)

    Respuesta cuando SIN departamento:
      {
        success: true,
        datos: [{HORA_LECTURA, DEPARTAMENTO, HL5}, ...],
        departamentos: ['ANTIOQUIA', 'CUNDINAMARCA', ...]   ← lista para el <select>
      }

    Respuesta cuando CON departamento:
      {
        success: true,
        datos: [{HORA_LECTURA, HL5}, ...],
        departamentos: []
      }
    """
    connection = None
    cursor = None

    try:
        # ── Parámetros ──────────────────────────────────────────────
        horas = request.args.get('horas', 12, type=int)
        if horas not in (12, 24):
            horas = 12

        departamento = request.args.get('departamento', '').strip()

        print(f"📊 [HIST-DEPTO] horas={horas}  departamento='{departamento}'")

        connection = get_mysql_connection()
        cursor = connection.cursor(dictionary=True)

        # ── Con filtro de un departamento específico ─────────────────
        if departamento:
            query = """
                SELECT
                    HORA_LECTURA,
                    COUNT(DISTINCT CINUM) AS HL5
                FROM reportes.db_dash_rose_hl5_inv
                WHERE HORA_LECTURA >= NOW() - INTERVAL %s HOUR
                  AND DEPARTAMENTO   = %s
                  AND DEPARTAMENTO IS NOT NULL
                GROUP BY HORA_LECTURA
                ORDER BY HORA_LECTURA ASC
            """
            cursor.execute(query, (horas, departamento))
            resultados = cursor.fetchall()

            for row in resultados:
                if row['HORA_LECTURA']:
                    row['HORA_LECTURA'] = row['HORA_LECTURA'].strftime('%Y-%m-%d %H:%M:%S')

            print(f"📊 [HIST-DEPTO] Registros para '{departamento}': {len(resultados)}")

            cursor.close()
            connection.close()

            return jsonify({
                'success': True,
                'datos': resultados,
                'departamentos': []
            })

        # ── Sin filtro → todos los departamentos ────────────────────
        # 1. Lista de departamentos para poblar el <select>
        cursor.execute("""
            SELECT DISTINCT DEPARTAMENTO
            FROM reportes.db_dash_rose_hl5_inv
            WHERE HORA_LECTURA  >= NOW() - INTERVAL %s HOUR
              AND DEPARTAMENTO  IS NOT NULL
              AND DEPARTAMENTO  <> ''
            ORDER BY DEPARTAMENTO ASC
        """, (horas,))
        departamentos = [row['DEPARTAMENTO'] for row in cursor.fetchall()]

        # 2. Datos para el gráfico (una fila por hora×departamento)
        query = """
            SELECT
                HORA_LECTURA,
                DEPARTAMENTO,
                COUNT(DISTINCT CINUM) AS HL5
            FROM reportes.db_dash_rose_hl5_inv
            WHERE HORA_LECTURA  >= NOW() - INTERVAL %s HOUR
              AND DEPARTAMENTO  IS NOT NULL
              AND DEPARTAMENTO  <> ''
            GROUP BY HORA_LECTURA, DEPARTAMENTO
            ORDER BY HORA_LECTURA ASC, DEPARTAMENTO ASC
        """
        cursor.execute(query, (horas,))
        resultados = cursor.fetchall()

        for row in resultados:
            if row['HORA_LECTURA']:
                row['HORA_LECTURA'] = row['HORA_LECTURA'].strftime('%Y-%m-%d %H:%M:%S')

        print(f"📊 [HIST-DEPTO] Registros todos deptos: {len(resultados)} "
              f"| Departamentos: {len(departamentos)}")

        cursor.close()
        connection.close()

        return jsonify({
            'success': True,
            'datos': resultados,
            'departamentos': departamentos
        })

    except Exception as e:
        import traceback
        print(f"❌ [HIST-DEPTO] Error: {e}")
        traceback.print_exc()
        if cursor:
            cursor.close()
        if connection:
            connection.close()
        return jsonify({
            'success': False,
            'error': str(e),
            'datos': [],
            'departamentos': []
        }), 500

# ================================================================
# grafica historico afectacion hl5 por ciudad
# ================================================================

@app.route('/api/hl5/historico-ciudad-debug')
def api_hl5_historico_ciudad_debug():
    """
    Histórico de afectación HL5 agrupado por ciudad.

    Parámetros de query-string:
      horas   -> 12 (default) | 24
      ciudad  -> nombre exacto de la ciudad (opcional)

    Respuesta sin filtro de ciudad:
      {
        success: true,
        datos: [{HORA_LECTURA, CIUDAD, HL5}, ...],
        ciudades: ['BOGOTA', 'MEDELLIN', ...]   ← lista para el <select>
      }

    Respuesta con ciudad:
      {
        success: true,
        datos: [{HORA_LECTURA, HL5}, ...],
        ciudades: []
      }
    """
    connection = None
    cursor = None

    try:
        horas = request.args.get('horas', 12, type=int)
        if horas not in (12, 24):
            horas = 12

        ciudad = request.args.get('ciudad', '').strip()

        print(f"🏙️ [HIST-CIUDAD] horas={horas}  ciudad='{ciudad}'")

        connection = get_mysql_connection()
        cursor = connection.cursor(dictionary=True)

        # ── Con filtro de una ciudad específica ──────────────────────
        if ciudad:
            query = """
                SELECT
                    HORA_LECTURA,
                    COUNT(DISTINCT CINUM) AS HL5
                FROM reportes.db_dash_rose_hl5_inv
                WHERE HORA_LECTURA >= NOW() - INTERVAL %s HOUR
                  AND CIUDAD       = %s
                  AND CIUDAD IS NOT NULL
                GROUP BY HORA_LECTURA
                ORDER BY HORA_LECTURA ASC
            """
            cursor.execute(query, (horas, ciudad))
            resultados = cursor.fetchall()

            for row in resultados:
                if row['HORA_LECTURA']:
                    row['HORA_LECTURA'] = row['HORA_LECTURA'].strftime('%Y-%m-%d %H:%M:%S')

            print(f"🏙️ [HIST-CIUDAD] Registros para '{ciudad}': {len(resultados)}")

            cursor.close()
            connection.close()

            return jsonify({
                'success': True,
                'datos': resultados,
                'ciudades': []
            })

        # ── Sin filtro → todas las ciudades ─────────────────────────
        # 1. Lista para el <select>
        cursor.execute("""
            SELECT DISTINCT CIUDAD
            FROM reportes.db_dash_rose_hl5_inv
            WHERE HORA_LECTURA >= NOW() - INTERVAL %s HOUR
              AND CIUDAD IS NOT NULL
              AND CIUDAD <> ''
            ORDER BY CIUDAD ASC
        """, (horas,))
        ciudades = [row['CIUDAD'] for row in cursor.fetchall()]

        # 2. Datos para el gráfico
        query = """
            SELECT
                HORA_LECTURA,
                CIUDAD,
                COUNT(DISTINCT CINUM) AS HL5
            FROM reportes.db_dash_rose_hl5_inv
            WHERE HORA_LECTURA >= NOW() - INTERVAL %s HOUR
              AND CIUDAD IS NOT NULL
              AND CIUDAD <> ''
            GROUP BY HORA_LECTURA, CIUDAD
            ORDER BY HORA_LECTURA ASC, CIUDAD ASC
        """
        cursor.execute(query, (horas,))
        resultados = cursor.fetchall()

        for row in resultados:
            if row['HORA_LECTURA']:
                row['HORA_LECTURA'] = row['HORA_LECTURA'].strftime('%Y-%m-%d %H:%M:%S')

        print(f"🏙️ [HIST-CIUDAD] Registros todas ciudades: {len(resultados)} "
              f"| Ciudades: {len(ciudades)}")

        cursor.close()
        connection.close()

        return jsonify({
            'success': True,
            'datos': resultados,
            'ciudades': ciudades
        })

    except Exception as e:
        import traceback
        print(f"❌ [HIST-CIUDAD] Error: {e}")
        traceback.print_exc()
        if cursor:
            cursor.close()
        if connection:
            connection.close()
        return jsonify({
            'success': False,
            'error': str(e),
            'datos': [],
            'ciudades': []
        }), 500

# ============================================
# API ONMS — Incidentes activos
# ============================================
@app.route('/api/onms/incidentes')
@login_requerido
@permiso_requerido('onms')
def api_onms_incidentes():
    try:
        conn   = get_postgres_connection()
        cursor = conn.cursor()

        SQL = """
            WITH ultimo_log AS (
                -- Un solo log por OT: el más reciente
                SELECT DISTINCT ON (wonum)
                    wonum,
                    createdate,
                    description,
                    description_long
                FROM onms.worklogs
                ORDER BY wonum, createdate DESC
            ),
            primer_log AS (
                -- Un solo log por OT: el primero registrado
                SELECT DISTINCT ON (wonum)
                    wonum,
                    description_long
                FROM onms.worklogs
                ORDER BY wonum, createdate ASC
            ),
            work_orders_base AS (
                -- Deduplicar OTs antes del JOIN con inventario
                SELECT DISTINCT ON (wo.wonum)
                    wo.wonum,
                    wo.outage_asociado,
                    wo.description,
                    wo.actual_start,
                    wo.tipo_tramo,
                    wo.eecc_cuadrilla_fo,
                    wo.operador_fo,
                    wo.location,
                    wo.activa
                FROM onms.work_orders wo
                WHERE wo.actual_start >= CURRENT_DATE - INTERVAL '30 days'
                ORDER BY wo.wonum, wo.actual_start DESC
            )
            SELECT
                wo.wonum AS ot,
                CASE
                    WHEN wo.outage_asociado IS NOT NULL
                         AND wo.outage_asociado <> ''
                        THEN 'SI'
                    ELSE 'NO'
                END AS afectacion,
                trim(split_part(
                    replace(wo.description, 'Falla FiOp, ', ''),
                    '-',
                    1
                )) AS nodo_a,

                trim(split_part(
                    replace(wo.description, 'Falla FiOp, ', ''),
                    '-',
                    2
                )) AS nodo_b,
                wo.actual_start                    AS inicio,
                COALESCE(wo.tipo_tramo, '')        AS tipo_tramo,
                COALESCE(wo.eecc_cuadrilla_fo, '') AS eecc,
                COALESCE(wo.operador_fo, '')       AS operador_fo,
                ul.createdate                      AS fecha_ultimo_avance,
                COALESCE(ul.description, '')       AS titulo_avance,
                COALESCE(ul.description_long, '')  AS avance,
                COALESCE(pl.description_long, '')  AS primer_avance,
                CASE
                    WHEN wo.location = inv.sit_location_origen
                        THEN inv.mun_origen || ', ' || inv.depto_origen
                    WHEN wo.location = inv.sit_location_destino
                        THEN inv.mun_destino || ', ' || inv.depto_destino
                    ELSE NULL
                END AS ubicacion
            FROM work_orders_base wo
            LEFT JOIN ultimo_log ul ON wo.wonum = ul.wonum
            LEFT JOIN primer_log  pl ON wo.wonum = pl.wonum
            LEFT JOIN smartsoc.inventario_anillo_bh_fusion inv
                ON wo.location = inv.sit_location_origen
                OR wo.location = inv.sit_location_destino
            WHERE wo.actual_start >= CURRENT_DATE - INTERVAL '30 days'
            and wo.activa = True 
            ORDER BY wo.actual_start DESC
        """

        cursor.execute(SQL)
        rows    = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        from datetime import datetime
        import re

        def limpiar_html(texto):
            """Elimina etiquetas HTML, comentarios y espacios redundantes."""
            if not texto:
                return ''
            texto = re.sub(r'<!--.*?-->', '', texto, flags=re.DOTALL)
            texto = re.sub(r'<[^>]+>', ' ', texto)
            texto = re.sub(r'\s+', ' ', texto).strip()
            return texto

        ahora = datetime.now()

        incidentes = []
        vistos     = set()

        for row in rows:
            fila = dict(zip(columns, row))
            ot   = str(fila['ot'])

            # Segunda barrera de deduplicación a nivel Python
            if ot in vistos:
                continue
            vistos.add(ot)

            fecha_ult = fila.get('fecha_ultimo_avance')
            if fecha_ult:
                if hasattr(fecha_ult, 'tzinfo') and fecha_ult.tzinfo is not None:
                    fecha_ult = fecha_ult.astimezone().replace(tzinfo=None)
                min_sin_avance = max(0, int((ahora - fecha_ult).total_seconds() / 60))
            else:
                min_sin_avance = 0

            inicio_fmt = fila['inicio'].strftime('%d/%m %H:%M:%S') if fila.get('inicio') else '—'
            ult_av_fmt = fecha_ult.strftime('%d/%m %H:%M:%S')      if fecha_ult          else '—'

            # Afectación: viene del outage_asociado; si el primer avance
            # menciona "con afectaci" (cubre tildes y sin tilde), se fuerza a 'SI'
            afectacion      = fila['afectacion']
            primer_avance   = limpiar_html(fila.get('primer_avance', '') or '')
            if afectacion == 'NO' and re.search(r'con afectaci', primer_avance, re.IGNORECASE):
                afectacion = 'SI'
            
            # Excluir filas cuyo título de último avance indique cierre/normalización
            TITULOS_EXCLUIDOS = ('resumen falla', 'resumen ot', 'fin', 'normaliz', 'resumen de falla', 'resumen')
            titulo_avance = (fila.get('titulo_avance', '') or '').lower().strip()
            if any(titulo_avance.startswith(k) or k in titulo_avance for k in TITULOS_EXCLUIDOS):
                continue

            incidentes.append({
                'ot':                  ot,
                'afectacion':          afectacion,
                'nodoA':               fila.get('nodo_a', '')          or '',
                'nodoB':               fila.get('nodo_b', '')          or '',
                'municipio':           fila.get('ubicacion', '')       or '',
                'inicio':              inicio_fmt,
                'tipoTramo':           fila.get('tipo_tramo', '')      or '',
                'eecc':                fila.get('eecc', '')            or '',
                'operadorFo':          fila.get('operador_fo', '')     or '',
                'etapa':               'Por Asignar',
                'cuadrilla':           '',
                'contratista':         '',
                'tramoAfectado':       '',
                'ultAvance':           ult_av_fmt,
                'ultAvanceTitulo':     fila.get('titulo_avance', '')   or '',
                'ultAvanceComentario': limpiar_html(fila.get('avance', '') or ''),
                'primerAvance':        primer_avance,
                'minSinAvance':        min_sin_avance,
            })

        cursor.close()
        conn.close()

        return jsonify({'ok': True, 'data': incidentes})

    except Exception as e:
        logging.error(f'[ONMS] Error cargando incidentes: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500

# ============================================================
# API ONMS — Historial de OTs
# Agregar en app.py antes del bloque: if __name__ == '__main__'
# ============================================================
 
@app.route('/api/onms/historial/registrar', methods=['POST'])
@login_requerido
@permiso_requerido('onms')
def api_onms_historial_registrar():
    """
    Recibe un lote de OTs desde el tablero y las inserta en
    onms.historial_ots_atendidas usando INSERT ... ON CONFLICT DO NOTHING,
    garantizando que cada OT aparezca una sola vez por día.
 
    Body JSON esperado:
    {
        "ots": [
            {
                "ot": "10650713",
                "afectacion": "NO",
                "nodoA": "Mov. La Merced Norte",
                "nodoB": "Mov. Chapinero",
                "inicio": "05/05 08:20:00",
                "tipoTramo": "RBHFO",
                "operadorFo": "Infraco",
                "eecc": "Comfica",
                "cuadrilla": ""
            },
            ...
        ]
    }
    """
    conn   = None
    cursor = None
    try:
        datos = request.get_json()
        if not datos or 'ots' not in datos:
            return jsonify({'ok': False, 'error': 'Payload inválido'}), 400
 
        ots = datos['ots']
        if not isinstance(ots, list) or len(ots) == 0:
            return jsonify({'ok': True, 'insertadas': 0, 'mensaje': 'Lista vacía'})
 
        conn   = get_postgres_connection()
        cursor = conn.cursor()
 
        SQL_INSERT = """
            INSERT INTO onms.historial_ots_atendidas
                (fecha, ot, afectacion, nodo_a, nodo_b,
                 hora_inicio, tipo_tramo, operador_fo, eecc, cuadrilla)
            VALUES
                (CURRENT_DATE, %s, %s, %s, %s,
                 NOW(), %s, %s, %s, %s)
            ON CONFLICT (fecha, ot) DO NOTHING
        """
 
        insertadas = 0
        for item in ots:
            ot = str(item.get('ot', '')).strip()
            if not ot:
                continue
 
            cursor.execute(SQL_INSERT, (
                ot,
                item.get('afectacion', 'NO'),
                (item.get('nodoA') or item.get('nodo_a', ''))[:150],
                (item.get('nodoB') or item.get('nodo_b', ''))[:150],
                (item.get('tipoTramo') or item.get('tipo_tramo', ''))[:30],
                (item.get('operadorFo') or item.get('operador_fo', ''))[:120],
                (item.get('eecc', ''))[:120],
                (item.get('cuadrilla', ''))[:120],
            ))
            if cursor.rowcount > 0:
                insertadas += 1
 
        conn.commit()
        logging.info(f'[ONMS historial] {insertadas} OTs nuevas registradas de {len(ots)} recibidas')
 
        return jsonify({'ok': True, 'insertadas': insertadas, 'total': len(ots)})
 
    except Exception as e:
        if conn:
            conn.rollback()
        logging.error(f'[ONMS historial] Error al registrar: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500
 
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
 
 
@app.route('/api/onms/historial')
@login_requerido
@permiso_requerido('onms')
def api_onms_historial():
    """
    Retorna el historial de OTs para una fecha dada.
 
    Query-string:
        fecha  -> 'YYYY-MM-DD'  (default: hoy)
 
    Respuesta:
    {
        "ok": true,
        "fecha": "2026-05-05",
        "total": 34,
        "ots": [ {...}, ... ]
    }
    """
    conn   = None
    cursor = None
    try:
        from datetime import date
        fecha_param = request.args.get('fecha', '')
        try:
            fecha = date.fromisoformat(fecha_param) if fecha_param else date.today()
        except ValueError:
            fecha = date.today()
 
        conn   = get_postgres_connection()
        cursor = conn.cursor()
 
        cursor.execute("""
            SELECT
                ot,
                afectacion,
                nodo_a,
                nodo_b,
                hora_inicio,
                tipo_tramo,
                operador_fo,
                eecc,
                cuadrilla,
                registrado_en
            FROM onms.historial_ots_atendidas
            WHERE fecha = %s
            ORDER BY registrado_en ASC
        """, (fecha,))
 
        columns = [desc[0] for desc in cursor.description]
        filas   = []
        for row in cursor.fetchall():
            d = dict(zip(columns, row))
            # Serializar timestamps
            for col in ('hora_inicio', 'registrado_en'):
                if d.get(col) and hasattr(d[col], 'strftime'):
                    d[col] = d[col].strftime('%d/%m/%Y %H:%M:%S')
            filas.append(d)
 
        return jsonify({
            'ok':    True,
            'fecha': str(fecha),
            'total': len(filas),
            'ots':   filas
        })
 
    except Exception as e:
        logging.error(f'[ONMS historial] Error al consultar: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500
 
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ═══════════════════════════════════════════════════════════════
# MODULO ONMS — Creacion de OTs RBHFO
# ═══════════════════════════════════════════════════════════════
from onms.routes_crear_ot import onms_crear_ot_get, onms_crear_ot_post
app.route('/onms/crear_ot', methods=['GET'])(onms_crear_ot_get)
app.route('/onms/crear_ot', methods=['POST'])(onms_crear_ot_post)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5052, debug=True)