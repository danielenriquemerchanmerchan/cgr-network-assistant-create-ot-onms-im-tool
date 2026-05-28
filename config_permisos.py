# config_permisos.py
"""
Sistema de permisos y control de acceso para SmartSOC
"""

# ============================================
# DEFINICIÓN DE PERFILES Y SUS PERMISOS
# ============================================

PERMISOS_POR_PERFIL = {
    'CG': {
        'nombre': 'Centro de Gestión',
        'home': True,
        'callcenter': True,
        'callcenter_abonados': True,
        'dashboard': True,
        'dash_fija': True,
        'dash_movil': True,
        'dash_backhaul': True,
        'monitoreo_hl5': True,
        'seguimiento_hl5': True,
        'aperturas_anillos': True,
        'servicio_al_cliente': True,
        'admin_solicitudes': False,
        'gestion_usuarios': False,
        'gobernanza': True,
        'trabajos_programados': True,
        'n1': True, 
        'onms': True, 
        'descripcion': 'Acceso completo excepto administración de usuarios'
    },
    
    'Servicio al Cliente': {
        'nombre': 'Servicio al Cliente',
        'home': True,
        'callcenter': False,
        'callcenter_abonados': False,
        'dashboard': False,
        'dash_fija': False,
        'dash_movil': False,
        'dash_backhaul': False,
        'monitoreo_hl5': False,
        'seguimiento_hl5': False,
        'aperturas_anillos': False,
        'servicio_al_cliente': True,
        'admin_solicitudes': False,
        'gestion_usuarios': False,
        'gobernanza': False,
        'trabajos_programados': True,
        'n1': False,
        'onms': False, 
        'descripcion': 'Acceso solo a Servicio al Cliente'
    },
    
    'Dashboards - Servicio al Cliente': {
        'nombre': 'Dashboards y Servicio al Cliente',
        'home': True,
        'callcenter': False,
        'callcenter_abonados': False,
        'dashboard': True,
        'dash_fija': True,
        'dash_movil': True,
        'dash_backhaul': True,
        'monitoreo_hl5': True,
        'seguimiento_hl5': True,
        'aperturas_anillos': True,
        'servicio_al_cliente': True,
        'admin_solicitudes': False,
        'gestion_usuarios': False,
        'gobernanza': False,
        'trabajos_programados': True,
        'n1': False,
        'onms': True, 
        'descripcion': 'Acceso a Dashboards y Servicio al Cliente'
    },

    'Callcenter': {
        'nombre': 'Callcenter',
        'home': True,
        'callcenter': True,
        'callcenter_abonados': True,
        'dashboard': False,
        'dash_fija': False,
        'dash_movil': False,
        'dash_backhaul': False,
        'monitoreo_hl5': False,
        'seguimiento_hl5': False,
        'aperturas_anillos': False,
        'servicio_al_cliente': False,
        'admin_solicitudes': False,
        'gestion_usuarios': False,
        'gobernanza': False,
        'trabajos_programados': True,
        'n1': False,
        'onms': False, 
        'descripcion': 'Acceso solo a Callcenter y Abonados'
    },
    
    'Dashboards': {
        'nombre': 'Solo Dashboards',
        'home': True,
        'callcenter': False,
        'callcenter_abonados': False,
        'dashboard': True,
        'dash_fija': True,
        'dash_movil': True,
        'dash_backhaul': True,
        'monitoreo_hl5': True,
        'seguimiento_hl5': True,
        'aperturas_anillos': True,
        'servicio_al_cliente': False,
        'admin_solicitudes': False,
        'gestion_usuarios': False,
        'gobernanza': False,
        'trabajos_programados': True,
        'n1': False,
        'onms': True, 
        'descripcion': 'Acceso solo a Dashboards'
    },
    
    # ⭐ NUEVO PERFIL: EXTERNOS
    'Externos': {
        'nombre': 'Externos',
        'home': True,
        'callcenter': False,
        'callcenter_abonados': False,
        'dashboard': True,
        'dash_fija': False,
        'dash_movil': False,
        'dash_backhaul': True,        # ✅ SÍ tiene acceso
        'monitoreo_hl5': True,          # ✅ SÍ tiene acceso
        'seguimiento_hl5': True,        # ✅ SÍ tiene acceso
        'aperturas_anillos': True,      # ✅ SÍ tiene acceso
        'servicio_al_cliente': False,
        'admin_solicitudes': False,
        'gestion_usuarios': False,      # ❌ NO tiene acceso
        'gobernanza': False,
        'n1': False,
        'onms': False, 
        'descripcion': 'Acceso limitado: Backhaul, Monitoreo HL5, Seguimiento HL5 y Aperturas de Anillos'
    },
    
    'ADMIN': {
        'nombre': 'Administrador',
        'home': True,
        'callcenter': True,
        'callcenter_abonados': True,
        'dashboard': True,
        'dash_fija': True,
        'dash_movil': True,
        'dash_backhaul': True,
        'monitoreo_hl5': True,
        'seguimiento_hl5': True,
        'aperturas_anillos': True,
        'servicio_al_cliente': True,
        'admin_solicitudes': True,
        'gestion_usuarios': True,
        'gobernanza': True,
        'trabajos_programados': True,
        'n1': True, 
        'onms': True, 
        'descripcion': 'Acceso total al sistema'
    }
}


# ============================================
# USUARIOS ADMINISTRADORES (Fallback)
# ============================================
USUARIOS_ADMIN = [
    'eoacevedoso',
    'dfcamachova',
    'admin'
]


# ============================================
# FUNCIONES DE VALIDACIÓN DE PERMISOS
# ============================================

def obtener_permisos(perfil):
    """
    Obtiene los permisos de un perfil específico
    
    Args:
        perfil: Nombre del perfil del usuario
        
    Returns:
        dict: Diccionario con los permisos del perfil
    """
    return PERMISOS_POR_PERFIL.get(perfil, {})


def tiene_permiso(perfil, seccion):
    """
    Verifica si un perfil tiene permiso para acceder a una sección
    
    Args:
        perfil: Perfil del usuario
        seccion: Nombre de la sección a verificar
        
    Returns:
        bool: True si tiene permiso, False en caso contrario
    """
    permisos = obtener_permisos(perfil)
    return permisos.get(seccion, False)


def es_administrador(usuario=None, perfil=None):
    """
    Verifica si un usuario es administrador
    
    Args:
        usuario: Nombre de usuario
        perfil: Perfil del usuario
        
    Returns:
        bool: True si es administrador
    """
    # Verificar por perfil
    if perfil and perfil in ['ADMIN', 'ADMINISTRADOR']:
        return True
    
    # Verificar por lista de usuarios admin
    if usuario and usuario in USUARIOS_ADMIN:
        return True
    
    return False


def validar_acceso_seccion(session_data, seccion):
    """
    Valida si el usuario en sesión tiene acceso a una sección
    
    Args:
        session_data: Datos de la sesión del usuario
        seccion: Sección a validar
        
    Returns:
        bool: True si tiene acceso
    """
    perfil = session_data.get('PERFIL')
    usuario = session_data.get('USUARIO')
    
    # Administradores tienen acceso a todo
    if es_administrador(usuario=usuario, perfil=perfil):
        return True
    
    # Verificar permiso específico del perfil
    return tiene_permiso(perfil, seccion)


def obtener_menu_usuario(perfil, usuario=None):
    """
    Genera el menú disponible para un usuario según su perfil
    
    Args:
        perfil: Perfil del usuario
        usuario: Nombre de usuario (opcional)
        
    Returns:
        dict: Diccionario con las opciones de menú disponibles
    """
    # Si es admin, devolver todo
    if es_administrador(usuario=usuario, perfil=perfil):
        return {
            'home': True,
            'callcenter': True,
            'callcenter_abonados': True,
            'dashboard': True,
            'dash_backhaul': True,
            'monitoreo_hl5': True,
            'seguimiento_hl5': True,
            'aperturas_anillos': True,
            'servicio_al_cliente': True,
            'admin_solicitudes': True,
            'gobernanza': True,
            'gestion_usuarios': True,
            'trabajos_programados': True,
            'n1': True,
            'onms': True 
        }
    
    # Obtener permisos del perfil
    permisos = obtener_permisos(perfil)
    
    # Construir menú basado en permisos
    menu = {
        'home': permisos.get('home', False),
        'callcenter': permisos.get('callcenter', False),
        'callcenter_abonados': permisos.get('callcenter_abonados', False),
        'dashboard': permisos.get('dashboard', False),
        'dash_backhaul': permisos.get('dash_backhaul', False),
        'monitoreo_hl5': permisos.get('monitoreo_hl5', False),
        'seguimiento_hl5': permisos.get('seguimiento_hl5', False),
        'aperturas_anillos': permisos.get('aperturas_anillos', False),
        'servicio_al_cliente': permisos.get('servicio_al_cliente', False),
        'admin_solicitudes': permisos.get('admin_solicitudes', False),
        'gobernanza': permisos.get('gobernanza', False),
        'gestion_usuarios': permisos.get('gestion_usuarios', False),
        'trabajos_programados': permisos.get('trabajos_programados', False),
        'n1': permisos.get('n1', False),
        'onms': permisos.get('onms', False) 
    }
    
    return menu


def obtener_perfiles_disponibles():
    """
    Obtiene la lista de perfiles disponibles en el sistema
    
    Returns:
        list: Lista de nombres de perfiles
    """
    return list(PERMISOS_POR_PERFIL.keys())


def obtener_info_perfil(perfil):
    """
    Obtiene información detallada de un perfil
    
    Args:
        perfil: Nombre del perfil
        
    Returns:
        dict: Información del perfil
    """
    return PERMISOS_POR_PERFIL.get(perfil, {})