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
  const capaUrl = `/static/${jogo.capa_path}`;
  const defaultUrl = '/static/covers/default.jpg';
  const detailUrl = `/jogo/${jogo.id}`;
  const nome = jogo.nome;

  return `
    <div class="game-card group neon-border flex outline-none" data-id="${jogo.id}" data-nome="${nome}" data-capa="${capaUrl}">
      <div class="card-image-container flex-1 relative rounded-[11px] overflow-hidden">
        <img src="${capaUrl}" alt="${nome}" onerror="this.src='${defaultUrl}'" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110" loading="lazy" />
        <div class="scout-overlay">
          <div class="scout-actions">
            <button class="btn-scout-mini btn-zoom" title="Ver em tamanho real" onclick="event.preventDefault(); openLightbox('${nome}', '${capaUrl}')">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0M10 7v6m3-3H7"/></svg>
            </button>
            <button class="btn-scout-mini btn-reload" title="Trocar Imagem" onclick="event.preventDefault(); reloadCardImage(this, ${jogo.id}, '${nome}', '${jogo.categoria}')">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            </button>
          </div>
          <div class="card-scout-footer">
            <h3 class="card-scout-title">${nome}</h3>
          </div>
        </div>
        <a href="${detailUrl}" class="absolute inset-0 z-10"></a>
      </div>
    </div>`;
}

/**
 * Global Lightbox Logic
 */
window.openLightbox = (title, url) => {
  const overlay = document.getElementById('lightbox-overlay');
  const img = document.getElementById('lightbox-img');
  const titleEl = document.getElementById('lightbox-title');
  if (!overlay || !img || !titleEl) return;

  img.src = url;
  titleEl.textContent = title;
  overlay.classList.remove('hidden');
};

/**
 * Rapid Reload Logic for Scout Cards
 */
window.reloadCardImage = async (btn, id, nome, categoria) => {
  const icon = btn.querySelector('svg');
  icon.classList.add('animate-spin');
  btn.classList.add('opacity-50', 'pointer-events-none');

  try {
    const res = await fetch(`/admin/api/buscar_previas?q=${encodeURIComponent(nome)}&cat=${categoria}`);
    const data = await res.json();

    if (data.success && data.opcoes && data.opcoes.length > 0) {
      // Pega a primeira opção e salva automaticamente
      const saveRes = await fetch('/admin/api/salvar_capa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jogo_id: id, url: data.opcoes[0] })
      });
      const saveData = await saveRes.json();

      if (saveData.success) {
        // Atualiza a imagem no card
        const card = btn.closest('.game-card');
        const img = card.querySelector('img');
        img.src = saveData.novo_path + '?t=' + Date.now();
        showToast('Capa atualizada!', 'success');
      }
    } else {
      showToast('Nenhuma imagem encontrada.', 'error');
    }
  } catch (err) {
    showToast('Erro ao buscar imagem.', 'error');
  } finally {
    icon.classList.remove('animate-spin');
    btn.classList.remove('opacity-50', 'pointer-events-none');
  }
};

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
    let isDone = false;
    try { isDone = sessionStorage.getItem('loaderDone'); } catch(e) {}
    
    if (immediate || isDone) {
      loader.style.display = 'none';
      loader.remove();
    } else {
      loader.classList.add('loader-hidden');
      setTimeout(() => loader.remove(), 400);
      try { sessionStorage.setItem('loaderDone', 'true'); } catch(e) {}
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
  try {
    if (sessionStorage.getItem('loaderDone')) {
      hideLoader(true);
    }
  } catch(e) {}
  
  // Guarantee loader is hidden quickly on pages that don't invoke fetchJogos
  setTimeout(() => hideLoader(false), 200);

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

// Fallback robusto para esconder o loader
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    try { hideLoader(false); } catch(e) { 
      const loader = document.getElementById('startup-loader');
      if(loader) loader.remove();
    }
  }, 500);
});

window.addEventListener('load', () => {
  try { hideLoader(true); } catch(e) {
    const loader = document.getElementById('startup-loader');
    if(loader) loader.remove();
  }
});
