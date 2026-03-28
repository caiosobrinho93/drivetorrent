"""
utils.py — Funções utilitárias: geração de slug, busca de capa no SteamGridDB,
enriquecimento via RAWG API, duckduckgo-search, leitura de .torrent e utilidades gerais.
"""

import os
import re
import time
import json
import logging
import requests
from slugify import slugify as _slugify
from duckduckgo_search import DDGS
import bencode

from config import (
    COVERS_DIR, UPLOADS_DIR,
    STEAMGRIDDB_API_KEY, STEAMGRIDDB_BASE_URL, COVER_REQUEST_TIMEOUT,
    RAWG_API_KEY, RAWG_BASE_URL, RAWG_TIMEOUT, RAWG_SCREENSHOTS_MAX,
    WAREZ_SUFFIXES,
)

logger = logging.getLogger(__name__)


# ─── Slug ─────────────────────────────────────────────────────────────────────
def gerar_slug(nome: str) -> str:
    """Gera um slug URL-friendly a partir do nome do jogo."""
    return _slugify(nome, max_length=80, word_boundary=True, separator="-")


def slug_unico(nome: str, get_by_slug_fn) -> str:
    """Garante que o slug seja único adicionando sufixo numérico se necessário."""
    base = gerar_slug(nome)
    slug = base
    counter = 1
    while get_by_slug_fn(slug) is not None:
        slug = f"{base}-{counter}"
        counter += 1
    return slug


# ─── Limpeza de nome warez ────────────────────────────────────────────────────
def limpar_nome_jogo(nome_raw: str) -> str:
    """
    Converte um nome de arquivo warez num nome legível.
    Ex: 'assassins_creed_mirage_repack' -> 'Assassins Creed Mirage'
    """
    nome = re.sub(r"[_\-\.]+", " ", nome_raw)
    nome = re.sub(r"\bv?\d+(\.\d+){1,3}\b", "", nome, flags=re.IGNORECASE)
    palavras = [
        p for p in nome.split()
        if p.lower() not in WAREZ_SUFFIXES and len(p) > 1
    ]
    resultado = " ".join(palavras).strip()
    return resultado.title() if resultado else nome_raw.replace("_", " ").title()


def limpar_nome_torrent(filename: str) -> str:
    """
    Limpa o nome de um arquivo .torrent para busca de metadados.
    Remove extensões, nomes de grupos de release, anos e tags comuns.
    """
    # 1. Remove .torrent
    nome = re.sub(r"\.torrent$", "", filename, flags=re.IGNORECASE)
    
    # 2. Troca pontos, underscores e hífens por espaços
    nome = re.sub(r"[._\-\[\]]", " ", nome)
    
    # 3. Remove anos (ex: 2023, 2024) que podem atrapalhar busca exata se estiverem colados
    nome = re.sub(r"\b(19|20)\d{2}\b", " ", nome)
    
    # 4. Remove tags comuns de release (WAREZ_SUFFIXES + extras)
    tags_extra = [
        "repack", "multi", "eng", "crack", "steam", "unlocked", "deluxe", "edition",
        "gold", "fitgirl", "dodi", "codex", "skidrow", "cpy", "plaza", "razor1911",
        "empress", "elamigos", "gaotd", "p2p", "v1", "v2", "update", "setup", "portable"
    ]
    
    from config import WAREZ_SUFFIXES
    todas_tags = set(list(WAREZ_SUFFIXES) + tags_extra)
    
    palavras = nome.split()
    limpas = []
    for p in palavras:
        if p.lower() not in todas_tags and len(p) > 1:
            # Se a palavra parece uma versão (v1.0, etc), para por aqui ou ignora
            if re.match(r"^v?\d+(\.\d+)*$", p, re.IGNORECASE):
                continue
            limpas.append(p)
            
    # 5. Reconstrói e formata
    resultado = " ".join(limpas).strip()
    return resultado.title() if resultado else filename.replace(".torrent", "").title()


def adivinhar_categoria(nome: str) -> str:
    """
    Tenta adivinhar se um torrent é Jogo, Curso ou Software baseado no nome.
    """
    nome_low = nome.lower()
    
    # Palavras-chave para Cursos
    keywords_curso = [
        "curso", "course", "tutorial", "learn", "how to", "masterclass", 
        "udemy", "formação", "treinamento", "aula", "class"
    ]
    if any(k in nome_low for k in keywords_curso):
        return "Curso"
        
    # Palavras-chave para Software
    keywords_soft = [
        "adobe", "photoshop", "windows", "office", "autocad", "activator", 
        "crack", "software", "tool", "app", "installer", "setup", "portable",
        "corel", "vegas", "maya", "zbrush", "substance", "ableton", "fl studio"
    ]
    if any(k in nome_low for k in keywords_soft):
        return "Software"
        
    # Padrão é Jogo
    return "Jogo"


# ─── RAWG API — Enriquecimento de metadados ───────────────────────────────────
def buscar_info_rawg(nome_query: str) -> dict:
    """
    Busca metadados completos na RAWG API.
    Retorna dict com: nome, descricao, screenshots, youtube_url, encontrado.
    """
    resultado = {
        "nome": nome_query,
        "descricao": "",
        "screenshots": [],
        "youtube_url": "",
        "encontrado": False,
    }

    if not RAWG_API_KEY:
        logger.info("RAWG: API key não configurada.")
        return resultado

    params_base = {"key": RAWG_API_KEY}

    try:
        # ─ 1. Busca o jogo ──────────────────────────────────────────────────
        resp = requests.get(
            f"{RAWG_BASE_URL}/games",
            params={**params_base, "search": nome_query, "page_size": 3,
                    "search_exact": False},
            timeout=RAWG_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("results"):
            logger.info("RAWG: nenhum resultado para '%s'", nome_query)
            return resultado

        jogo = data["results"][0]
        game_id = jogo["id"]
        resultado["nome"] = jogo.get("name", nome_query)
        resultado["encontrado"] = True

        # ─ 2. Detalhes completos (descrição + clip YouTube) ─────────────────
        det = requests.get(
            f"{RAWG_BASE_URL}/games/{game_id}",
            params=params_base,
            timeout=RAWG_TIMEOUT
        )
        det.raise_for_status()
        det_data = det.json()

        # Descrição: prefere description_raw (texto limpo sem HTML)
        descricao = det_data.get("description_raw") or ""
        if not descricao:
            raw_html = det_data.get("description") or ""
            descricao = re.sub(r"<[^>]+>", " ", raw_html)
            descricao = re.sub(r"\s+", " ", descricao).strip()
        resultado["descricao"] = descricao[:4000]

        # YouTube trailer via campo clip da RAWG
        clip = det_data.get("clip")
        if clip and isinstance(clip, dict):
            video_id = clip.get("video")
            if video_id:
                resultado["youtube_url"] = f"https://www.youtube.com/embed/{video_id}"

        # ─ 3. Screenshots ────────────────────────────────────────────────────
        ss_resp = requests.get(
            f"{RAWG_BASE_URL}/games/{game_id}/screenshots",
            params={**params_base, "page_size": RAWG_SCREENSHOTS_MAX},
            timeout=RAWG_TIMEOUT
        )
        ss_resp.raise_for_status()
        ss_data = ss_resp.json()
        resultado["screenshots"] = [
            s["image"] for s in ss_data.get("results", []) if s.get("image")
        ][:RAWG_SCREENSHOTS_MAX]

    except requests.exceptions.Timeout:
        logger.warning("RAWG: timeout para query '%s'", nome_query)
    except requests.exceptions.HTTPError as e:
        logger.warning("RAWG: erro HTTP: %s", e)
    except Exception as e:
        logger.error("RAWG: erro inesperado: %s", e)

    return resultado


# ─── Capa via SteamGridDB ────────────────────────────────────────────────────
def _sanitize_query(nome: str) -> str:
    """Remove caracteres especiais para melhorar a busca na API."""
    # Remove conteúdo entre parênteses/colchetes (ex: edição, ano)
    nome = re.sub(r"[\(\[\{][^)\]\}]*[\)\]\}]", "", nome)
    # Remove pontuação excessiva
    nome = re.sub(r"[^\w\s]", " ", nome)
    return " ".join(nome.split()).strip()


def _buscar_grid_id(nome_sanitizado: str, headers: dict) -> int | None:
    """Busca o ID do jogo no SteamGridDB."""
    url = f"{STEAMGRIDDB_BASE_URL}/search/autocomplete/{requests.utils.quote(nome_sanitizado)}"
    try:
        resp = requests.get(url, headers=headers, timeout=COVER_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") and data.get("data"):
            return data["data"][0]["id"]
    except requests.exceptions.Timeout:
        logger.warning("SteamGridDB: timeout ao buscar ID para '%s'", nome_sanitizado)
    except requests.exceptions.HTTPError as e:
        logger.warning("SteamGridDB: erro HTTP ao buscar ID: %s", e)
    except Exception as e:
        logger.error("SteamGridDB: erro inesperado ao buscar ID: %s", e)
    return None


def _buscar_url_capa(grid_id: int, headers: dict) -> str | None:
    """Busca a URL da melhor capa (grid) para o jogo."""
    url = f"{STEAMGRIDDB_BASE_URL}/grids/game/{grid_id}"
    params = {"dimensions": "600x900", "limit": 1}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=COVER_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") and data.get("data"):
            return data["data"][0]["url"]
    except requests.exceptions.Timeout:
        logger.warning("SteamGridDB: timeout ao buscar capa id=%s", grid_id)
    except requests.exceptions.HTTPError as e:
        logger.warning("SteamGridDB: erro HTTP ao buscar capa: %s", e)
    except Exception as e:
        logger.error("SteamGridDB: erro inesperado ao buscar capa: %s", e)
    return None


def _baixar_imagem(url_imagem: str, slug: str) -> str | None:
    """Faz o download da imagem e salva em /static/covers/. Retorna o path relativo."""
    timestamp = int(time.time())
    filename = f"{slug}_{timestamp}.jpg"
    filepath = os.path.join(COVERS_DIR, filename)
    try:
        resp = requests.get(url_imagem, timeout=COVER_REQUEST_TIMEOUT, stream=True)
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return f"covers/{filename}"
    except Exception as e:
        logger.error("Erro ao baixar imagem '%s': %s", url_imagem, e)
        return None


def buscar_capa(nome: str, slug: str) -> str:
    """
    Pipeline completo: sanitiza nome → busca ID no SteamGridDB → busca URL da capa
    → baixa e salva. Retorna path relativo ou 'covers/default.jpg' como fallback.
    """
    fallback = "covers/default.jpg"

    if not STEAMGRIDDB_API_KEY:
        logger.info("SteamGridDB: API key não configurada. Usando capa padrão.")
        return fallback

    headers = {"Authorization": f"Bearer {STEAMGRIDDB_API_KEY}"}
    nome_sanitizado = _sanitize_query(nome)

    if not nome_sanitizado:
        return fallback

    grid_id = _buscar_grid_id(nome_sanitizado, headers)
    if not grid_id:
        return fallback

    url_capa = _buscar_url_capa(grid_id, headers)
    if not url_capa:
        return fallback

    path = _baixar_imagem(url_capa, slug)
    return path if path else fallback


# ─── DuckDuckGo — Enriquecimento (Cursos e Softwares) ────────────────────────
def pesquisar_duckduckgo_info(nome_query: str, categoria: str) -> dict:
    """Busca descrição, tamanho, imagens e video via DuckDuckGo (Universal Fallback)."""
    resultado = {
        "nome": nome_query,
        "descricao": "",
        "screenshots": [],
        "youtube_url": "",
        "encontrado": False,
        "tamanho_gb": 0.0
    }

    try:
        with DDGS() as ddgs:
            # 1. TEXTO e TAMANHO
            query_text = f"{nome_query} {categoria} overview description"
            results_text = list(ddgs.text(query_text, max_results=3))
            if results_text:
                descricao = "\n\n".join(r.get("body", "") for r in results_text if "body" in r)
                resultado["descricao"] = descricao[:2000].strip()
                resultado["encontrado"] = True
                
                size_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:gb|gigabytes)", descricao, re.IGNORECASE)
                if size_match:
                    resultado["tamanho_gb"] = float(size_match.group(1))

            # 2. SCREENSHOTS / IMAGENS
            query_img = f"{nome_query} {categoria} interface screenshots high resolution"
            results_img = list(ddgs.images(query_img, max_results=4))
            for res in results_img:
                if "image" in res:
                    resultado["screenshots"].append(res["image"])

            # 3. YOUTUBE TRAILER / GAMEPLAY
            query_vid = f"{nome_query} {categoria} full gameplay trailer review"
            results_vid = list(ddgs.videos(query_vid, max_results=1))
            if results_vid and "content" in results_vid[0]:
                resultado["youtube_url"] = results_vid[0]["content"]

    except Exception as e:
        logger.error("DDGS Universal info error: %s", e)

    return resultado


def pesquisar_duckduckgo_capa(nome: str, categoria: str, slug: str) -> str:
    """Busca imagem de capa via DuckDuckGo e salva."""
    fallback = "covers/default.jpg"
    query = f"{nome} {categoria} poster cover box art high resolution"
    
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=1))
        
        if results and "image" in results[0]:
            img_url = results[0]["image"]
            path = _baixar_imagem(img_url, slug)
            return path if path else fallback
            
    except Exception as e:
        logger.error("DDGS capa error: %s", e)
        
    return fallback


# ─── Extrator de Tamanho de Torrent ──────────────────────────────────────────
def extrair_tamanho_torrent(filepath: str) -> float:
    """
    Lê o arquivo .torrent com bencode e retorna o tamanho total em GB.
    Garante exatidão do tamanho do payload ignorando metadados do tracker.
    """
    try:
        with open(filepath, 'rb') as f:
            torrent_data = f.read()
            
        torrent = bencode.decode(torrent_data)
        info = torrent.get(b'info', {})
        total_size = 0
        
        if b'length' in info:
            total_size = info[b'length']
        elif b'files' in info:
            for file in info[b'files']:
                total_size += file.get(b'length', 0)
                
        # Converte bytes para GB com 2 casas
        return round(total_size / (1024**3), 2)
    except Exception as e:
        logger.error("Erro ao extrair tamanho do torrent '%s': %s", filepath, e)
        return 0.0


# ─── Imagem padrão (Pillow) ───────────────────────────────────────────────────
def gerar_imagem_default():
    """Gera /static/covers/default.jpg com Pillow se não existir."""
    caminho = os.path.join(COVERS_DIR, "default.jpg")
    if os.path.exists(caminho):
        return

    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (600, 900), color=(20, 20, 28))  # fundo escuro
        draw = ImageDraw.Draw(img)

        # Gradient effect com retângulos sobrepostos
        for i in range(0, 900, 3):
            alpha = int(255 * (1 - i / 900) * 0.08)
            overlay_color = (255, 100, 30, alpha)
            draw.rectangle([0, i, 600, i + 3], fill=(20 + int(i * 0.02), 20, 28))

        # Borda laranja
        draw.rectangle([20, 20, 580, 880], outline=(255, 100, 30), width=3)

        # Ícone central (losango)
        cx, cy = 300, 380
        sz = 60
        draw.polygon([(cx, cy - sz), (cx + sz, cy), (cx, cy + sz), (cx - sz, cy)],
                     fill=(255, 100, 30))

        # Texto principal
        try:
            font_big = ImageFont.truetype("arial.ttf", 44)
            font_small = ImageFont.truetype("arial.ttf", 22)
        except OSError:
            font_big = ImageFont.load_default()
            font_small = font_big

        # "Sem Capa"
        draw.text((300, 480), "SEM CAPA", fill=(230, 230, 230), font=font_big, anchor="mm")
        draw.text((300, 545), "Nenhuma imagem disponível", fill=(140, 140, 160),
                  font=font_small, anchor="mm")

        img.save(caminho, "JPEG", quality=90)
        logger.info("Imagem padrão gerada em: %s", caminho)

    except ImportError:
        logger.warning("Pillow não encontrado. Criando placeholder mínimo.")
        # Cria um JPEG mínimo válido como último recurso
        with open(caminho, "wb") as f:
            # JPEG 1x1 pixel escuro
            f.write(bytes([
                0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00,
                0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB,
                0x00, 0x43, 0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07,
                0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B,
                0x0B, 0x0C, 0x19, 0x12, 0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E,
                0x1D, 0x1A, 0x1C, 0x1C, 0x20, 0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C,
                0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29, 0x2C, 0x30, 0x31, 0x34, 0x34,
                0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34,
                0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01,
                0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01, 0x05,
                0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
                0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01,
                0x03, 0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00,
                0x01, 0x7D, 0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21,
                0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32,
                0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1,
                0xF0, 0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16, 0x17, 0x18,
                0x19, 0x1A, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x34, 0x35, 0x36,
                0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
                0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64,
                0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75, 0x76, 0x77,
                0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A,
                0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
                0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5,
                0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
                0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9,
                0xDA, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA,
                0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF,
                0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5,
                0xFF, 0xD9
            ]))


# ─── Limpeza de arquivos ──────────────────────────────────────────────────────
def deletar_arquivos_jogo(capa_path: str, torrent_path: str):
    """
    Remove os arquivos físicos do jogo excluído.
    Preserva o default.jpg e ignora paths vazios.
    """
    # Capa (só remove se não for o default)
    if capa_path and capa_path != "covers/default.jpg":
        caminho_capa = os.path.join(os.path.dirname(COVERS_DIR), "static", capa_path) \
            if not os.path.isabs(capa_path) \
            else capa_path
        # Reconstrói o path absoluto a partir de COVERS_DIR
        caminho_capa = os.path.join(os.path.dirname(COVERS_DIR), capa_path)
        _remover_arquivo(caminho_capa)

    # Torrent
    if torrent_path:
        caminho_torrent = os.path.join(os.path.dirname(UPLOADS_DIR), torrent_path) \
            if not os.path.isabs(torrent_path) \
            else torrent_path
        caminho_torrent = os.path.join(os.path.dirname(UPLOADS_DIR), torrent_path)
        _remover_arquivo(caminho_torrent)


def _remover_arquivo(caminho: str):
    """Remove um arquivo com tratamento de erro."""
    try:
        if os.path.exists(caminho):
            os.remove(caminho)
            logger.info("Arquivo removido: %s", caminho)
    except OSError as e:
        logger.error("Erro ao remover arquivo '%s': %s", caminho, e)


# ─── Validação de extensão ────────────────────────────────────────────────────
def extensao_valida(filename: str, extensoes_permitidas: set) -> bool:
    """Verifica se o arquivo tem uma extensão permitida."""
    _, ext = os.path.splitext(filename.lower())
    return ext in extensoes_permitidas


def salvar_upload(file_obj, destino_dir: str, slug: str, extensao: str) -> str:
    """Salva um arquivo de upload com nome baseado no slug + timestamp."""
    timestamp = int(time.time())
    filename = f"{slug}_{timestamp}{extensao}"
    filepath = os.path.join(destino_dir, filename)
    file_obj.save(filepath)
    # Retorna path relativo ao /static/
    rel = os.path.relpath(filepath, os.path.dirname(destino_dir))
    return rel.replace("\\", "/")
