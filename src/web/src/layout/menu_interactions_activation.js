// Reused from astro-huge-doc src/layout/menu_interactions_activation.js with
// one change: a disabled toggle (plan D4 — page with no outline sections)
// forces its nav closed and gets no click handler.
const root = document.querySelector(':root');
// Read tokens live so resize-handle colors follow the active light/dark theme
// instead of being frozen to whatever was active at page load.
function cssVar(name){
    return getComputedStyle(root).getPropertyValue(name).trim();
}
function header_bg_color(){ return cssVar('--header-bg-color'); }
function content_bg_color(){ return cssVar('--content-bg-color'); }

// Open/close is driven by the app-bar toggle buttons. The button is the
// single authority; it reflects state via aria-expanded so the icon styling
// and the persisted preference stay in sync.
function configure_toggle(btn, nav_el, storageKey){
    if(!btn || !nav_el){ return; }
    const scopedStorageKey = `${nav_el.getAttribute("data-state-key") || "even-viewer:default"}:${storageKey}:open`;

    function notify_visibility(open){
        nav_el.dispatchEvent(new CustomEvent("microwebstacks:nav-visibility", {
            detail: {open}
        }));
    }

    function apply(open){
        if(open){
            nav_el.classList.add("open");
            nav_el.classList.remove("closed");
            nav_el.style.width = nav_el.getAttribute("data-width");
        }else{
            nav_el.classList.add("closed");
            nav_el.classList.remove("open");
            nav_el.style.width = "0px";
        }
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        notify_visibility(open);
    }

    // Disabled control: the page has no outline. Force closed, no handler,
    // and leave the persisted preference untouched so pages that do have an
    // outline keep the user's last choice.
    if(btn.disabled){
        apply(false);
        return;
    }

    // Restore the last choice; default to whatever the server rendered.
    const saved = localStorage.getItem(scopedStorageKey);
    if(saved === "true" || saved === "false"){
        apply(saved === "true");
    }else{
        apply(nav_el.classList.contains("open"));
    }

    btn.addEventListener("click",(e)=>{
        const open = !nav_el.classList.contains("open");
        apply(open);
        localStorage.setItem(scopedStorageKey, open ? "true" : "false");
        e.preventDefault();
    });
}

// The thin handles between nav and content keep only the drag-to-resize role.
function configure_resize(resize_el,nav_el,left_to_right){
    if(!resize_el || !nav_el){ return; }
    if(!resize_el.classList.contains("active")){ return; }
    var global_resize_state = false
    var x_down
    var start_width

    function finish_mouse(){
        global_resize_state = false
        nav_el.style.transition = "none"
        if(nav_el.clientWidth < 20){
            nav_el.classList.add("closed")
            nav_el.classList.remove("open")
            nav_el.setAttribute("data-width","20vw")
        }else{
            nav_el.classList.add("open")
            nav_el.classList.remove("closed")
        }
        resize_el.style.backgroundColor = content_bg_color()
        nav_el.dispatchEvent(new CustomEvent("microwebstacks:nav-visibility", {
            detail: {open: nav_el.classList.contains("open")}
        }));
    }

    resize_el.addEventListener("mouseenter",(e)=>{
        resize_el.style.backgroundColor = header_bg_color()
    })
    resize_el.addEventListener("mouseleave",(e)=>{
        resize_el.style.backgroundColor = content_bg_color()
    })
    resize_el.addEventListener("mousedown",(e)=>{
        global_resize_state = true
        x_down = e.x
        start_width = nav_el.clientWidth
        nav_el.style.transition = "none"
    })
    resize_el.addEventListener("mouseup",(e)=>{
        finish_mouse()
    })
    document.addEventListener("mouseup",(e)=>{
        if(global_resize_state == true){
            finish_mouse()
        }
    })
    document.addEventListener("mousemove",(e)=>{
        if(global_resize_state == true){
            const new_width = left_to_right?(start_width + e.x - x_down):(start_width - e.x + x_down)
            if(new_width <= 60){//snap effect
                nav_el.style.width = "0px"
                nav_el.setAttribute("data-width","0px")
                resize_el.style.backgroundColor = header_bg_color
            }else if(new_width < 160){
                //do nothing here
            }else if(new_width < (document.documentElement.clientWidth)*0.4){
                nav_el.style.width = new_width+"px"
                nav_el.setAttribute("data-width",new_width+"px")
                resize_el.style.backgroundColor = header_bg_color
            }else{
                resize_el.style.backgroundColor = "red"
            }
            e.preventDefault()
        }
    })
}

function menu_interactions_activation(){
    const pages_nav = document.querySelector("#wide-nav nav.pages_menu")
    const toc_nav   = document.querySelector("#toc-nav-div nav.toc_menu")

    configure_toggle(document.getElementById("nav-toggle-left"),  pages_nav, "left_open")
    configure_toggle(document.getElementById("nav-toggle-right"), toc_nav,   "right_open")

    configure_resize(document.getElementById("resize-left"),  pages_nav, true)
    configure_resize(document.getElementById("resize-right"), toc_nav,   false)
}

document.addEventListener('DOMContentLoaded', menu_interactions_activation, false);
