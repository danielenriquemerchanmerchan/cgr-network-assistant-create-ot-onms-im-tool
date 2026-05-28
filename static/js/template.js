const iconoLogo = document.getElementById("icon-logo");
const barraLateral = document.querySelector(".barra-lateral")
const logo = document.querySelector(".logo")
const spans = document.querySelectorAll("span")
const menu = document.querySelector(".menu");
const main = document.querySelector("main");

menu.addEventListener("click",()=>{
    barraLateral.classList.toggle("max-barra-lateral");
    if (barraLateral.classList.contains("max-barra-lateral")){
        menu.children[0].style.display = "none";
        menu.children[1].style.display = "block";
    }
    else{
        menu.children[0].style.display = "block";
        menu.children[1].style.display = "none";
    }
    if (window.innerWidth<=320){
        barraLateral.classList.add("mini-barra-lateral");
        main.classList.toggle("min-main");
        spans.forEach((span) =>{
            span.classList.toggle("oculto");
    })
    }
});

iconoLogo.addEventListener("click", ()=>{
    barraLateral.classList.toggle("mini-barra-lateral");
    logo.classList.toggle("oculto");
    main.classList.toggle("min-main");
    spans.forEach((span) =>{
        span.classList.toggle("oculto");
    });
})

//Funciones para el logout
document.getElementById('logoutBtn').addEventListener('click', function() {
    // Eliminar la información de la sesión (esto depende de cómo gestiones el login)
    localStorage.removeItem('usuario'); // o sessionStorage.removeItem('usuario');
    
    // O si usas cookies:
    // document.cookie = 'usuario=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
  
    // Redirigir a la página de login
    window.location.href = '/login.html';
  });

