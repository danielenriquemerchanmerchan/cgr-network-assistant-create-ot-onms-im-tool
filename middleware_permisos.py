# middleware_permisos.py
"""
Decoradores y middleware para control de permisos en Flask
"""

from functools import wraps
from flask import session, redirect, url_for, flash
import config_permisos


def login_requerido(f):
    """
    Decorador que verifica que el usuario esté autenticado
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'USUARIO' not in session:
            flash('Debe iniciar sesión para acceder', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def permiso_requerido(seccion):
    """
    Decorador que verifica que el usuario tenga permiso para acceder a una sección
    
    Args:
        seccion: Nombre de la sección a validar
    
    Ejemplo de uso:
        @app.route('/callcenter')
        @login_requerido
        @permiso_requerido('callcenter')
        def callcenter():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Verificar autenticación
            if 'USUARIO' not in session:
                flash('Debe iniciar sesión para acceder', 'error')
                return redirect(url_for('login'))
            
            # Verificar permisos
            perfil = session.get('PERFIL')
            usuario = session.get('USUARIO')
            
            # Administradores tienen acceso a todo
            if config_permisos.es_administrador(usuario=usuario, perfil=perfil):
                return f(*args, **kwargs)
            
            # Verificar permiso específico
            if not config_permisos.tiene_permiso(perfil, seccion):
                flash(f'No tiene permisos para acceder a esta sección', 'error')
                return redirect(url_for('home'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def solo_admin(f):
    """
    Decorador que permite acceso solo a administradores
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'USUARIO' not in session:
            flash('Debe iniciar sesión para acceder', 'error')
            return redirect(url_for('login'))
        
        perfil = session.get('PERFIL')
        usuario = session.get('USUARIO')
        
        if not config_permisos.es_administrador(usuario=usuario, perfil=perfil):
            flash('No tiene permisos de administrador', 'error')
            return redirect(url_for('home'))
        
        return f(*args, **kwargs)
    return decorated_function


def inyectar_permisos():
    """
    Función para inyectar permisos en el contexto de las plantillas
    Agregar en app.py:
    
    @app.context_processor
    def utility_processor():
        return inyectar_permisos()
    """
    perfil = session.get('PERFIL')
    usuario = session.get('USUARIO')
    
    menu = config_permisos.obtener_menu_usuario(perfil, usuario)
    es_admin = config_permisos.es_administrador(usuario=usuario, perfil=perfil)
    
    return {
        'menu_permisos': menu,
        'es_admin': es_admin,
        'perfil_usuario': perfil
    }