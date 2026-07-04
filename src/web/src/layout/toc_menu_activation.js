const STORAGE_PREFIX = 'microwebstacks.menuControls.v1';
const AUTO_FIT_MARGIN = 1.2;
const PAGES_AUTO_MAX_DEPTH = 2;
const REVEAL_SYNC_DELAY_MS = 550;

function escape_href(href){
    return `#${CSS.escape(href.replace('#',''))}`;
}

function getMaxLevel(nav){
    const fromAttr = parseInt(nav.getAttribute('data-max-level') || '1',10);
    return Number.isFinite(fromAttr) && fromAttr>0?fromAttr:1;
}

function getDefaultLevel(nav){
    const fromAttr = parseInt(nav.getAttribute('data-default-level') || '1',10);
    return Number.isFinite(fromAttr) && fromAttr>0?Math.min(fromAttr, getMaxLevel(nav)):1;
}

function isToc(nav){
    return nav.classList.contains('toc_menu');
}

function isVisibleNav(nav){
    if(!nav || !nav.isConnected){
        return false;
    }
    const style = getComputedStyle(nav);
    return style.display !== 'none' && nav.clientHeight > 0;
}

function canMeasureNav(nav){
    return isVisibleNav(nav) && nav.clientWidth > 24;
}

function storageKey(nav){
    const key = nav.getAttribute('data-state-key') || (isToc(nav) ? 'toc_menu' : 'pages_menu');
    return `${STORAGE_PREFIX}:${key}`;
}

function safeReadState(nav){
    try {
        const raw = localStorage.getItem(storageKey(nav));
        if(!raw){ return null; }
        const parsed = JSON.parse(raw);
        if(!parsed || typeof parsed !== 'object'){ return null; }
        return parsed;
    } catch {
        return null;
    }
}

function safeWriteState(nav){
    const state = getState(nav);
    try {
        localStorage.setItem(storageKey(nav), JSON.stringify({
            mode: state.mode,
            manualKind: state.manualKind,
            depth: state.depth,
            manualDepth: state.manualDepth,
            expandedKeys: state.expandedKeys,
            scrollTop: state.scrollTop ?? nav.scrollTop ?? 0
        }));
    } catch {
        /* storage can be unavailable in restricted contexts */
    }
}

//---------------   Expand / collapse helpers   ---------------
function childListForEntry(entry){
    return entry?.closest('li')?.querySelector(':scope > ul') ?? null;
}

function setParentExpanded(ul, expanded){
    const parentDiv = ul.previousElementSibling;
    if(parentDiv?.classList?.contains('entry_container')){
        parentDiv.classList.toggle('expanded', expanded);
    }
}

function setEntryExpanded(entry, expanded){
    const childList = childListForEntry(entry);
    if(!entry || !childList){
        return;
    }
    entry.classList.toggle('expanded', expanded);
    childList.classList.toggle('hidden', !expanded);
}

function entryNodeKey(entry){
    return entry?.getAttribute('data-node-key') || '';
}

function collectExpandedKeys(nav){
    const expanded = [];
    nav.querySelectorAll('.entry_container.parent[data-node-key]').forEach((entry)=>{
        const childList = childListForEntry(entry);
        if(childList && !childList.classList.contains('hidden')){
            const key = entryNodeKey(entry);
            if(key){
                expanded.push(key);
            }
        }
    });
    return expanded;
}

function expandChain(nav, el, includeSelf){
    if(includeSelf){
        const entry = el.closest?.('.entry_container');
        if(entry){
            entry.classList.add('expanded');
            const li = entry.closest('li');
            li?.querySelector(':scope > ul')?.classList.remove('hidden');
        }
    }
    let node = el;
    while(node && node !== nav){
        if(node.tagName === 'UL'){
            node.classList.remove('hidden');
            setParentExpanded(node, true);
        }
        if(node.classList?.contains('entry_container')){
            node.classList.add('expanded');
        }
        node = node.parentElement;
    }
}

function activeMenuElement(nav){
    return nav.querySelector('.entry_container.active') || nav.querySelector('a.toc_href.active');
}

function scrollElementIntoViewIfNeeded(nav, el){
    if(!el){ return; }
    const navRect = nav.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    const controlsHeight = nav.querySelector('.depth-controls')?.getBoundingClientRect().height || 0;
    const topLimit = navRect.top + controlsHeight;
    if(elRect.top < topLimit){
        nav.scrollTop -= (topLimit - elRect.top) + 8;
    }else if(elRect.bottom > navRect.bottom){
        nav.scrollTop += (elRect.bottom - navRect.bottom) + 8;
    }
}

function ensureActiveVisible(nav, options = {}){
    const active = activeMenuElement(nav);
    if(!active){return;}
    expandChain(nav, active, false);
    if(options.scroll !== false){
        scrollElementIntoViewIfNeeded(nav, active);
        requestAnimationFrame(()=>scrollElementIntoViewIfNeeded(nav, active));
        window.setTimeout(()=>scrollElementIntoViewIfNeeded(nav, active), REVEAL_SYNC_DELAY_MS);
    }
}

function collapseAll(nav){
    nav.querySelectorAll('ul[data-level]').forEach((ul)=>{
        const level = parseInt(ul.getAttribute('data-level')||'1',10);
        if(level > 1){
            ul.classList.add('hidden');
            setParentExpanded(ul, false);
        }
    });
}

function applyExpandedKeyState(nav, expandedKeys, options = {}){
    const expanded = new Set((expandedKeys ?? []).filter(Boolean));
    collapseAll(nav);
    nav.querySelectorAll('.entry_container.parent[data-node-key]').forEach((entry)=>{
        const key = entryNodeKey(entry);
        setEntryExpanded(entry, expanded.has(key));
    });
    if(options.keepActive !== false){
        ensureActiveVisible(nav, {scroll: options.scroll !== false});
    }
}

function applyDepth(nav, depth, options = {}){
    const max = getMaxLevel(nav);
    const target = Math.min(Math.max(1,depth),max);
    nav.querySelectorAll('ul[data-level]').forEach((ul)=>{
        const level = parseInt(ul.getAttribute('data-level')||'1',10);
        if(level <= target){
            ul.classList.remove('hidden');
            setParentExpanded(ul, true);
        }else{
            ul.classList.add('hidden');
            setParentExpanded(ul, false);
        }
    });
    if(options.keepActive !== false){
        ensureActiveVisible(nav, {scroll: options.scroll !== false});
    }
}

function currentVisibleDepth(nav){
    let depth = 1;
    nav.querySelectorAll('ul[data-level]').forEach((ul)=>{
        if(!ul.classList.contains('hidden')){
            const level = parseInt(ul.getAttribute('data-level')||'1',10);
            if(Number.isFinite(level)){
                depth = Math.max(depth, level);
            }
        }
    });
    return depth;
}

function renderedContentFits(nav){
    return nav.scrollHeight <= (nav.clientHeight * AUTO_FIT_MARGIN);
}

function estimateDefaultDepth(nav){
    const max = isToc(nav)
        ? getMaxLevel(nav)
        : Math.min(getMaxLevel(nav), PAGES_AUTO_MAX_DEPTH);
    if(max <= 1){ return 1; }

    const previousScroll = nav.scrollTop;
    nav.classList.add('measuring');
    let chosen = 1;
    for(let depth=1; depth<=max; depth++){
        applyDepth(nav, depth, {keepActive:true, scroll:false});
        if(renderedContentFits(nav)){
            chosen = depth;
        }else{
            break;
        }
    }
    applyDepth(nav, chosen, {keepActive:true, scroll:false});
    nav.scrollTop = previousScroll;
    nav.classList.remove('measuring');
    return chosen;
}

//---------------   Per-nav mode state   ---------------
const navState = new WeakMap();
function getState(nav){
    let state = navState.get(nav);
    if(!state){
        const saved = safeReadState(nav) ?? {};
        const max = getMaxLevel(nav);
        const defaultMode = isToc(nav) ? 'auto' : 'manual';
        const savedMode = saved.mode === 'manual' || saved.mode === 'auto' ? saved.mode : defaultMode;
        const savedManualKind = saved.manualKind === 'custom' ? 'custom' : 'depth';
        const savedManualDepth = Number.isFinite(saved.manualDepth)
            ? saved.manualDepth
            : (Number.isFinite(saved.depth) ? saved.depth : getDefaultLevel(nav));
        const manualDepth = Math.min(Math.max(1, savedManualDepth), max);
        state = {
            mode: savedMode,
            manualKind: savedManualKind,
            depth: manualDepth,
            manualDepth,
            expandedKeys: Array.isArray(saved.expandedKeys) ? saved.expandedKeys.filter((key)=> typeof key === 'string' && key.length > 0) : [],
            scrollTop: Number.isFinite(saved.scrollTop) ? Math.max(0, saved.scrollTop) : 0
        };
        navState.set(nav, state);
    }
    return state;
}

function setCenterModeIcon(nav){
    const state = getState(nav);
    const btn = nav.querySelector('.depth-controls [data-action="auto"]');
    if(!btn){ return; }
    const autoIcon = btn.querySelector('.mode-icon-auto');
    const manualIcon = btn.querySelector('.mode-icon-manual');
    const depthLabel = btn.querySelector('[data-depth-label]');
    const isAuto = state.mode === 'auto';
    const showDepthLabel = isAuto ? !isToc(nav) : state.manualKind !== 'custom';
    btn.setAttribute('data-mode', isAuto ? 'auto' : 'manual');
    if(autoIcon && manualIcon){
        autoIcon.classList.toggle('is-hidden', !isAuto);
        manualIcon.classList.toggle('is-hidden', isAuto);
        autoIcon.setAttribute('aria-hidden', isAuto ? 'false' : 'true');
        manualIcon.setAttribute('aria-hidden', isAuto ? 'true' : 'false');
    }
    if(depthLabel){
        depthLabel.textContent = String(state.depth);
        depthLabel.classList.toggle('is-hidden', !showDepthLabel);
        depthLabel.setAttribute('aria-hidden', showDepthLabel ? 'false' : 'true');
    }
    btn.classList.toggle('manual', !isAuto);
    const baseTitle = isToc(nav) ? 'Auto - follow scroll' : 'Auto - fit height';
    const title = isAuto
        ? (isToc(nav) ? baseTitle : `${baseTitle} (level ${state.depth})`)
        : (state.manualKind === 'custom'
            ? `Manual - custom branches; click for ${baseTitle.toLowerCase()}`
            : `Manual - level ${state.depth}; click for ${baseTitle.toLowerCase()}`);
    btn.setAttribute('title', title);
    btn.setAttribute('aria-label', title);
}

function updateButtons(nav){
    const state = getState(nav);
    const max = getMaxLevel(nav);
    nav.querySelectorAll('.depth-controls [data-action]').forEach((btn)=>{
        const action = btn.getAttribute('data-action');
        let on = false;
        if(state.mode === 'auto'){
            on = (action === 'auto');
        }else if(state.manualKind !== 'custom' && action === 'min'){
            on = state.depth <= 1;
        }else if(state.manualKind !== 'custom' && action === 'max'){
            on = state.depth >= max;
        }
        btn.classList.toggle('active', on);
    });
    setCenterModeIcon(nav);
}

//---------------   Auto modes   ---------------
function getTocTargets(nav){
    const article = document.querySelector('article.content');
    if(!article){ return { article:null, entries:[] }; }
    const links = [...nav.querySelectorAll('a.toc_href')];
    const entries = links.map((a)=>{
        const target = article.querySelector(escape_href(a.getAttribute('href')));
        return { a, target };
    }).filter((e)=> e.target);
    return { article, entries };
}

function applyAutoSpy(nav){
    const { article, entries } = getTocTargets(nav);
    if(!article || entries.length === 0){ return; }
    const artRect = article.getBoundingClientRect();
    collapseAll(nav);
    for(let i=0;i<entries.length;i++){
        const thisTop = entries[i].target.getBoundingClientRect().top;
        const nextTop = (i+1 < entries.length)
            ? entries[i+1].target.getBoundingClientRect().top
            : Infinity;
        if(thisTop < artRect.bottom && nextTop > artRect.top){
            expandChain(nav, entries[i].a, true);
        }
    }
    ensureActiveVisible(nav);
}

function applyAuto(nav, options = {}){
    const state = getState(nav);
    state.mode = 'auto';
    if(isToc(nav)){
        applyAutoSpy(nav);
        state.depth = currentVisibleDepth(nav);
    }else{
        state.depth = estimateDefaultDepth(nav);
        applyDepth(nav, state.depth);
    }
    updateButtons(nav);
    if(options.persist !== false){
        safeWriteState(nav);
    }
}

function setManual(nav, depth, options = {}){
    const state = getState(nav);
    const max = getMaxLevel(nav);
    state.mode = 'manual';
    state.manualKind = 'depth';
    state.depth = Math.min(Math.max(1, depth), max);
    state.manualDepth = state.depth;
    applyDepth(nav, state.depth);
    updateButtons(nav);
    if(options.persist !== false){
        safeWriteState(nav);
    }
}

function setManualCustom(nav, expandedKeys, options = {}){
    const state = getState(nav);
    state.mode = 'manual';
    state.manualKind = 'custom';
    state.expandedKeys = [...new Set((expandedKeys ?? []).filter(Boolean))];
    applyExpandedKeyState(nav, state.expandedKeys, {scroll: options.scroll !== false});
    state.depth = currentVisibleDepth(nav);
    updateButtons(nav);
    if(options.persist !== false){
        safeWriteState(nav);
    }
}

function restoreManualState(nav, options = {}){
    const state = getState(nav);
    if(state.manualKind === 'custom'){
        applyExpandedKeyState(nav, state.expandedKeys, {scroll: options.scroll !== false});
        state.depth = currentVisibleDepth(nav);
        updateButtons(nav);
        if(options.persist !== false){
            safeWriteState(nav);
        }
        return;
    }
    setManual(nav, state.manualDepth, options);
}

function toggleMode(nav){
    const state = getState(nav);
    if(state.mode === 'auto'){
        restoreManualState(nav);
    }else{
        applyAuto(nav);
    }
}

function restoreScroll(nav){
    const state = getState(nav);
    if(state.scrollTop > 0){
        nav.scrollTop = state.scrollTop;
    }
    ensureActiveVisible(nav);
}

function syncNavAfterReveal(nav){
    if(!canMeasureNav(nav)){
        return;
    }
    if(!initializedNavs.has(nav)){
        initMenuState(nav);
        return;
    }
    const state = getState(nav);
    if(state.mode === 'auto'){
        applyAuto(nav);
        return;
    }
    restoreManualState(nav, {persist:false});
    restoreScroll(nav);
}

const initializedNavs = new WeakSet();

function scheduleRevealSync(nav){
    requestAnimationFrame(()=>{
        syncNavAfterReveal(nav);
    });
    window.setTimeout(()=>{
        syncNavAfterReveal(nav);
    }, REVEAL_SYNC_DELAY_MS);
}

function initDepthButtons(nav){
    const controls = nav.querySelector('.depth-controls');
    if(!controls){ return; }
    controls.addEventListener('click', (e)=>{
        const btn = e.target.closest('[data-action]');
        if(!btn || !controls.contains(btn)){ return; }
        e.preventDefault();
        const state = getState(nav);
        const max = getMaxLevel(nav);
        const base = state.mode === 'auto'
            ? state.depth
            : (state.manualKind === 'custom' ? currentVisibleDepth(nav) : state.manualDepth);
        switch(btn.getAttribute('data-action')){
            case 'min':  setManual(nav, 1); break;
            case 'down': setManual(nav, base - 1); break;
            case 'auto': toggleMode(nav); break;
            case 'up':   setManual(nav, base + 1); break;
            case 'max':  setManual(nav, max); break;
        }
    });
}

function initScrollPersistence(nav){
    let ticking = false;
    nav.addEventListener('scroll', ()=>{
        if(ticking){ return; }
        ticking = true;
        requestAnimationFrame(()=>{
            const state = getState(nav);
            state.scrollTop = nav.scrollTop;
            safeWriteState(nav);
            ticking = false;
        });
    }, {passive:true});
}

//---------------   Scroll spy + cross highlight (toc only)   ---------------
function initScrollSpy(nav){
    const { article, entries } = getTocTargets(nav);
    if(!article || entries.length === 0){ return; }

    function currentEntry(){
        const artRect = article.getBoundingClientRect();
        const threshold = artRect.top + 4;
        let current = entries[0];
        for(const e of entries){
            if(e.target.getBoundingClientRect().top <= threshold){
                current = e;
            }else{
                break;
            }
        }
        return current;
    }
    function updateHighlight(){
        const cur = currentEntry();
        if(!cur){ return; }
        document.querySelector('.toc_href.active')?.classList.remove('active');
        document.querySelector('.heading.active')?.classList.remove('active');
        cur.a.classList.add('active');
        cur.target.classList.add('active');
    }

    let ticking = false;
    article.addEventListener('scroll', ()=>{
        if(ticking){ return; }
        ticking = true;
        requestAnimationFrame(()=>{
            updateHighlight();
            if(getState(nav).mode === 'auto'){ applyAutoSpy(nav); }
            ticking = false;
        });
    }, {passive:true});

    entries.forEach(({a, target})=>{
        a.addEventListener('mouseenter', ()=> target.classList.add('hover'));
        a.addEventListener('mouseleave', ()=> target.classList.remove('hover'));
        target.addEventListener('mouseenter', ()=> a.classList.add('hover'));
        target.addEventListener('mouseleave', ()=> a.classList.remove('hover'));
    });

    updateHighlight();
}

function initMenuState(nav){
    const state = getState(nav);
    if(state.mode === 'manual'){
        restoreManualState(nav, {persist:false});
    }else{
        applyAuto(nav, {persist:false});
    }
    restoreScroll(nav);
    safeWriteState(nav);
    initializedNavs.add(nav);
}

function toc_menu_activation(){
    const menus = document.querySelectorAll("nav.toc_menu, nav.pages_menu");
    menus.forEach((toc_menu)=>{
        const toggler = toc_menu.getElementsByClassName("expand");
        for (let i = 0; i < toggler.length; i++) {
            toggler[i].addEventListener("click", function(e) {
                const entry = this.parentElement;
                const childList = childListForEntry(entry);
                if(childList){
                    const expanded = childList.classList.contains("hidden");
                    setEntryExpanded(entry, expanded);
                }
                setManualCustom(toc_menu, collectExpandedKeys(toc_menu));
                e.preventDefault();
            });
        }
        initDepthButtons(toc_menu);
        initScrollPersistence(toc_menu);
        toc_menu.addEventListener('microwebstacks:nav-visibility', (event)=>{
            if(event.detail?.open){
                if(!initializedNavs.has(toc_menu) && canMeasureNav(toc_menu)){
                    initMenuState(toc_menu);
                }
                scheduleRevealSync(toc_menu);
            }
        });
        if(isToc(toc_menu)){
            initScrollSpy(toc_menu);
        }
        if(canMeasureNav(toc_menu)){
            initMenuState(toc_menu);
        }else{
            updateButtons(toc_menu);
        }
    });

    let resizeTick = false;
    window.addEventListener('resize', ()=>{
        if(resizeTick){ return; }
        resizeTick = true;
        requestAnimationFrame(()=>{
            document.querySelectorAll("nav.toc_menu, nav.pages_menu").forEach((nav)=>{
                if(canMeasureNav(nav) && getState(nav).mode === 'auto'){ applyAuto(nav); }
            });
            resizeTick = false;
        });
    });
}

document.addEventListener('DOMContentLoaded', toc_menu_activation, false);
