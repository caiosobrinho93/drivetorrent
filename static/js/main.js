/**
 * main.js — JavaScript modular principal.
 * Responsável por: busca com debounce, filtros combinados,
 * renderização de cards via API, paginação dinâmica.
 */

'use strict';

// ══════════════════════════════════════════════════════
// ESTADO GLOBAL
// ══════════════════════════════════════════════════════
const AppState = {
  query: '',
  categoria: '',
  page: 1,
  totalPaginas: 1,
  isLoading: false,
  debounceTimer: null,
};

// ... (utilities remain same) ...

/**
 * Gera o HTML de um card de jogo a partir dos dados da API.
 * SINCRONIZADO com _card.html (Single Face Edition)
 */
function renderCard(jogo) {
  const capaUrl = `/static/${escapeHtml(jogo.capa_path)}`;
  const defaultUrl = '/static/covers/default.jpg';
  const detailUrl = `/jogo/${jogo.id}`;
  const tamanho = formatarTamanho(jogo.tamanho);
  const categoria = escapeHtml(jogo.categoria);
  const nome = escapeHtml(jogo.nome);
  const plataforma = escapeHtml(jogo.plataforma || 'PC');

  return `
    <a href="${detailUrl}" class="game-card group neon-border flex outline-none" data-id="${jogo.id}">
      <div class="card-image-container relative rounded-[11px] overflow-hidden shrink-0">
        <img src="${capaUrl}" alt="Capa ${nome}" onerror="this.src='${defaultUrl}'" class="w-full h-full object-cover transition-filter duration-300" loading="lazy" />
        <div class="card-badge-grid absolute top-3 left-3 z-10 transition-opacity duration-200">
          <div class="bg-black/60 backdrop-blur-sm px-2 py-1 rounded border border-white/10">
            <span class="text-[10px] font-bold uppercase tracking-wider text-brand">${categoria}</span>
          </div>
        </div>
        <div class="img-overlay-gradient absolute bottom-0 left-0 w-full h-[80px] bg-gradient-to-t from-black via-black/80 to-transparent pointer-events-none transition-opacity duration-200"></div>
      </div>
      <div class="card-info flex flex-col justify-end pt-2 pb-3 px-3 transition-all duration-200 z-10 min-w-0">
        <div class="card-badge-list hidden mb-1 truncate">
          <span class="text-[10px] font-bold uppercase tracking-wider text-brand bg-brand/10 px-1.5 py-0.5 rounded border border-brand/20">${categoria}</span>
        </div>
        <h3 class="card-title text-[13px] font-bold text-white leading-snug line-clamp-2 mt-auto" data-tooltip="${nome}">
          ${nome}
        </h3>
        <div class="card-meta flex items-center justify-between mt-1 opacity-80 min-w-0 gap-2">
          <span class="text-[11px] text-gray-300 truncate">${plataforma}</span>
          <span class="text-[11px] font-bold text-brand whitespace-nowrap">${tamanho} GB</span>
        </div>
      </div>
    </a>`;
}

/**
 * Renderiza a grade de jogos.
 */
function renderGrid(jogos) {
  const grid = document.getElementById('games-grid');
  if (!grid) return;

  if (!jogos || jogos.length === 0) {
    grid.innerHTML = `
      <div class="text-center py-24 w-full col-span-full">
        <div class="w-20 h-20 rounded-full mx-auto mb-5 flex items-center justify-center bg-surface-elevated">
          <svg class="w-10 h-10 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
          </svg>
        </div>
        <h3 class="text-xl font-semibold mb-2 text-gray-400">Nenhum resultado encontrado</h3>
        <p class="text-gray-600">Tente outros termos ou limpe os filtros.</p>
      </div>`;
    return;
  }

  // Renderiza cards diretamente no container para respeitar a classe de visualização (grid/list)
  grid.innerHTML = jogos.map(renderCard).join('');
}

/**
 * Renderiza paginação dinâmica.
 */
function renderPaginacao(page, totalPaginas) {
  const nav = document.getElementById('pagination');
  if (!nav) return;

  if (totalPaginas <= 1) {
    nav.innerHTML = '';
    return;
  }

  let html = '';

  if (page > 1) {
    html += `<button class="btn-secondary !px-4" onclick="goToPage(${page - 1})" data-tooltip="Página Anterior">‹</button>`;
  }

  for (let p = 1; p <= totalPaginas; p++) {
    if (p === page) {
      html += `<span class="w-10 h-10 flex items-center justify-center rounded-xl bg-brand text-white font-semibold text-sm">${p}</span>`;
    } else if (p === 1 || p === totalPaginas || (p >= page - 2 && p <= page + 2)) {
      html += `<button onclick="goToPage(${p})" class="w-10 h-10 flex items-center justify-center rounded-xl border border-surface-border text-gray-400 hover:border-brand hover:text-brand transition-colors text-sm" data-tooltip="Ir para página ${p}">${p}</button>`;
    } else if (p === page - 3 || p === page + 3) {
      html += `<span class="text-gray-600 px-1">…</span>`;
    }
  }

  if (page < totalPaginas) {
    html += `<button class="btn-secondary !px-4" onclick="goToPage(${page + 1})" data-tooltip="Próxima Página">›</button>`;
  }

  nav.innerHTML = html;
}

/**
 * Atualiza o contador de resultados.
 */
function renderContador(total) {
  const el = document.getElementById('results-info');
  if (!el) return;

  const temFiltro = AppState.query || AppState.categoria;
  const filtradoStr = temFiltro ? ' <span class="text-brand">&nbsp;(filtrado)</span>' : '';

  if (total === 0) el.innerHTML = `Nenhum resultado encontrado.${filtradoStr}`;
  else if (total === 1) el.innerHTML = `1 resultado encontrado${filtradoStr}`;
  else el.innerHTML = `${total} resultados encontrados${filtradoStr}`;
}

async function fetchJogos(page = 1) {
  if (AppState.isLoading) return;
  AppState.isLoading = true;

  const grid = document.getElementById('games-grid');
  if (grid) {
    grid.innerHTML = `
      <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6 lg:gap-8 animate-pulse">
        ${Array.from({ length: 4 }).map(() => `
          <div class="aspect-[3/4] bg-surface-elevated rounded-2xl border border-surface-border"></div>
        `).join('')}
      </div>`;
  }

  const params = new URLSearchParams({
    q: AppState.query,
    categoria: AppState.categoria,
    page,
  });

  try {
    const res = await fetch(`/api/search?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    AppState.page = data.page;
    AppState.totalPaginas = data.total_paginas;

    renderGrid(data.jogos);
    renderPaginacao(data.page, data.total_paginas);
    renderContador(data.total);

    // Update URL
    const urlParams = new URLSearchParams();
    if (AppState.query) urlParams.set('q', AppState.query);
    if (AppState.categoria) urlParams.set('categoria', AppState.categoria);
    if (page > 1) urlParams.set('page', page);
    const newUrl = urlParams.toString() ? `?${urlParams}` : window.location.pathname;
    history.replaceState(null, '', newUrl);

  } catch (err) {
    console.error('[TorrentZone] Erro ao buscar:', err);
    if (grid) {
      grid.innerHTML = `<p class="text-center py-12 text-red-500">Erro ao carregar resultados. Tente novamente.</p>`;
    }
  } finally {
    AppState.isLoading = false;
    hideLoader(); // Esconde o loader após o primeiro carregamento
  }
}

function hideLoader(immediate = false) {
  const loader = document.getElementById('startup-loader');
  if (loader) {
    if (immediate || sessionStorage.getItem('loaderDone')) {
      loader.style.display = 'none';
      loader.remove();
    } else {
      loader.classList.add('loader-hidden');
      setTimeout(() => loader.remove(), 400);
      sessionStorage.setItem('loaderDone', 'true');
    }
  }
}

function goToPage(page) {
  AppState.page = page;
  fetchJogos(page);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

const debouncedSearch = debounce(() => {
  AppState.page = 1;
  fetchJogos(1);
}, 350);

function init() {
  // Config loader
  if (sessionStorage.getItem('loaderDone')) {
    hideLoader(true);
  }
  
  const searchInput = document.getElementById('search-input');
  if (!searchInput) return;

  const filterCategory = document.getElementById('filter-category');
  const btnClear = document.getElementById('btn-clear-filters');

  const urlParams = new URLSearchParams(window.location.search);
  AppState.query = urlParams.get('q') || '';
  AppState.categoria = urlParams.get('categoria') || '';
  AppState.page = parseInt(urlParams.get('page')) || 1;

  searchInput.addEventListener('input', () => {
    AppState.query = searchInput.value.trim();
    debouncedSearch();
  });

  filterCategory?.addEventListener('change', () => {
    AppState.categoria = filterCategory.value;
    AppState.page = 1;
    fetchJogos(1);
  });

  // ─── View Toggle (Grid/List) ──────────────────────────────────────────────
  const toggleGrid = document.getElementById('toggle-grid');
  const toggleList = document.getElementById('toggle-list');
  const gamesGrid = document.getElementById('games-grid');

  function setViewMode(mode) {
    if (!gamesGrid) return;
    
    if (mode === 'list') {
      gamesGrid.classList.replace('view-mode-grid', 'view-mode-list');
      toggleList.classList.add('text-brand', 'bg-brand/10');
      toggleList.classList.remove('text-gray-500');
      toggleGrid.classList.remove('text-brand', 'bg-brand/10');
      toggleGrid.classList.add('text-gray-500');
    } else {
      gamesGrid.classList.replace('view-mode-list', 'view-mode-grid');
      toggleGrid.classList.add('text-brand', 'bg-brand/10');
      toggleGrid.classList.remove('text-gray-500');
      toggleList.classList.remove('text-brand', 'bg-brand/10');
      toggleList.classList.add('text-gray-500');
    }
    localStorage.setItem('viewMode', mode);
  }

  if (toggleGrid && toggleList) {
    toggleGrid.addEventListener('click', () => setViewMode('grid'));
    toggleList.addEventListener('click', () => setViewMode('list'));
    
    // Restore preference
    const savedMode = localStorage.getItem('viewMode') || 'grid';
    setViewMode(savedMode);
  }

  btnClear?.addEventListener('click', () => {
    AppState.query = '';
    AppState.categoria = '';
    AppState.page = 1;
    searchInput.value = '';
    if (filterCategory) filterCategory.value = '';
    fetchJogos(1);
  });

  // ─── Admin Toggle Form ──────────────────────────────────────────────────
  const btnToggleForm = document.getElementById('btn-toggle-form');
  const formSection = document.getElementById('admin-form-section');
  if (btnToggleForm && formSection) {
    btnToggleForm.addEventListener('click', () => {
      formSection.classList.toggle('hidden');
      const isHidden = formSection.classList.contains('hidden');
      btnToggleForm.innerHTML = isHidden 
        ? `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg> Adicionar Novo`
        : `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg> Fechar Formulário`;
    });
  }
}

function debounce(fn, delay) {
  return function (...args) {
    clearTimeout(AppState.debounceTimer);
    AppState.debounceTimer = setTimeout(() => fn.apply(this, args), delay);
  };
}

function escapeHtml(str) {
  const el = document.createElement('div');
  el.textContent = str ?? '';
  return el.innerHTML;
}

function formatarTamanho(gb) {
  const n = parseFloat(gb);
  return isNaN(n) ? '?' : n.toFixed(1);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

// Fallback para esconder o loader
window.addEventListener('load', () => {
  if (!sessionStorage.getItem('loaderDone')) {
    setTimeout(() => hideLoader(false), 800);
  } else {
    hideLoader(true);
  }
});
