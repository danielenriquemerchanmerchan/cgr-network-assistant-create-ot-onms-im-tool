// ============================================
// JAVASCRIPT PARA MENÚ HÍBRIDO - SmartSOC
// Funciona con HOVER (CSS) y CLIC (JS)
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    
    // ============================================
    // 1. TOGGLE CON CLIC (Fijar menú abierto)
    // ============================================
    
    const hasSubmenuItems = document.querySelectorAll('.navegacion li.has-submenu');
    const isMobile = window.innerWidth <= 768;
    
    hasSubmenuItems.forEach(item => {
        const link = item.querySelector('> a');
        
        link.addEventListener('click', function(e) {
            const submenu = item.querySelector('.submenu');
            
            // Si tiene submenú
            if (submenu) {
                // En desktop: prevenir navegación solo si NO está ya activo
                // Esto permite que el clic "fije" el menú abierto
                if (!isMobile) {
                    e.preventDefault();
                }
                
                // En móvil: siempre prevenir navegación
                if (isMobile) {
                    e.preventDefault();
                }
                
                // Toggle clase active (esto "fija" el menú abierto)
                item.classList.toggle('active');
                
                // Opcional: Cerrar hermanos del mismo nivel
                // (Descomenta si quieres que solo uno esté abierto a la vez)
                /*
                const siblings = Array.from(item.parentElement.children);
                siblings.forEach(sibling => {
                    if (sibling !== item && sibling.classList.contains('has-submenu')) {
                        sibling.classList.remove('active');
                    }
                });
                */
            }
        });
    });
    
    // ============================================
    // 2. RESALTAR PÁGINA ACTIVA
    // ============================================
    
    function highlightActivePage() {
        const currentPath = window.location.pathname;
        const navLinks = document.querySelectorAll('.navegacion a');
        
        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            
            // Remover clase active-page de todos
            link.classList.remove('active-page');
            
            // Añadir clase active-page al link actual
            if (href && currentPath.includes(href) && href !== '/' && href !== '#') {
                link.classList.add('active-page');
                
                // Si está dentro de un submenú, expandir el padre automáticamente
                const parentSubmenu = link.closest('.submenu');
                if (parentSubmenu) {
                    const parentItem = parentSubmenu.closest('li.has-submenu');
                    if (parentItem) {
                        parentItem.classList.add('active');
                        
                        // Si hay un segundo nivel, expandir también
                        const grandParentSubmenu = parentItem.closest('.submenu');
                        if (grandParentSubmenu) {
                            const grandParentItem = grandParentSubmenu.closest('li.has-submenu');
                            if (grandParentItem) {
                                grandParentItem.classList.add('active');
                            }
                        }
                    }
                }
            }
        });
    }
    
    highlightActivePage();
    
    // ============================================
    // 3. CERRAR AL HACER CLIC FUERA (Opcional)
    // ============================================
    
    // Solo cerrar los que tienen clase active (los "fijados")
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.navegacion')) {
            hasSubmenuItems.forEach(item => {
                // Cerrar solo si está "fijado" con active
                if (item.classList.contains('active')) {
                    item.classList.remove('active');
                }
            });
        }
    });
    
    // ============================================
    // 4. ACCESIBILIDAD - TECLADO
    // ============================================
    
    hasSubmenuItems.forEach(item => {
        const link = item.querySelector('> a');
        
        link.addEventListener('keydown', function(e) {
            const submenu = item.querySelector('.submenu');
            
            if (submenu) {
                // Enter o Espacio para toggle
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    item.classList.toggle('active');
                }
                
                // Escape para cerrar
                if (e.key === 'Escape') {
                    item.classList.remove('active');
                    link.focus();
                }
                
                // Flecha abajo para abrir y enfocar primer item
                if (e.key === 'ArrowDown' && !item.classList.contains('active')) {
                    e.preventDefault();
                    item.classList.add('active');
                    const firstLink = submenu.querySelector('a');
                    if (firstLink) firstLink.focus();
                }
            }
        });
    });
    
    // ============================================
    // 5. AJUSTE AL MINIMIZAR BARRA LATERAL
    // ============================================
    
    const barraLateral = document.querySelector('.barra-lateral');
    
    if (barraLateral) {
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.attributeName === 'class') {
                    const isMini = barraLateral.classList.contains('mini-barra-lateral');
                    
                    // Cerrar todos los submenús cuando se minimiza
                    if (isMini) {
                        hasSubmenuItems.forEach(item => {
                            item.classList.remove('active');
                        });
                    }
                }
            });
        });
        
        observer.observe(barraLateral, { attributes: true });
    }
    
    // ============================================
    // 6. GESTIÓN DE REDIMENSIONAMIENTO
    // ============================================
    
    let resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() {
            // Si cambia de móvil a desktop, limpiar estados
            const currentlyMobile = window.innerWidth <= 768;
            if (currentlyMobile !== isMobile) {
                location.reload(); // Recargar para aplicar estilos correctos
            }
        }, 250);
    });
    
    // ============================================
    // 7. INDICADOR VISUAL DE HOVER (Opcional)
    // ============================================
    
    // Añadir clase temporal durante hover para efectos adicionales
    if (!isMobile) {
        hasSubmenuItems.forEach(item => {
            item.addEventListener('mouseenter', function() {
                this.classList.add('hovering');
            });
            
            item.addEventListener('mouseleave', function() {
                this.classList.remove('hovering');
            });
        });
    }
    
});

// ============================================
// CONSOLA DE INFORMACIÓN
// ============================================

console.log('✅ Menú híbrido inicializado');
console.log('📱 Modo:', window.innerWidth <= 768 ? 'Móvil (solo clic)' : 'Desktop (hover + clic)');
console.log('💡 Desktop: Hover para vista rápida, Clic para fijar abierto');