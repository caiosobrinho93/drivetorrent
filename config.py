"""
config.py — Configurações centralizadas da aplicação.
Todas as constantes e configurações ficam aqui para facilitar manutenção.
"""

import os
from datetime import timedelta

# ─── Caminhos base ───────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads")
COVERS_DIR = os.path.join(STATIC_DIR, "covers")
DATABASE_PATH = os.path.join(BASE_DIR, "blog.db")

# ─── Flask ───────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "TorrentBlog@SuperSecretKey#2025")
SESSION_PERMANENT = False
PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

# ─── Admin ───────────────────────────────────────────────────────────────────
ADMIN_PASSWORD = "torrentadmin2025"

# ─── Upload ──────────────────────────────────────────────────────────────────
ALLOWED_TORRENT_EXTENSIONS = {".torrent"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_CONTENT_LENGTH = 512 * 1024 * 1024  # 512 MB

# ─── Paginação ────────────────────────────────────────────────────────────────
JOGOS_POR_PAGINA = 12

# ─── SteamGridDB ─────────────────────────────────────────────────────────────
STEAMGRIDDB_API_KEY = os.environ.get("STEAMGRIDDB_API_KEY", "")
STEAMGRIDDB_BASE_URL = "https://www.steamgriddb.com/api/v2"
COVER_REQUEST_TIMEOUT = 10  # segundos

# ─── RAWG API (enriquecimento de metadados) ───────────────────────────────────
RAWG_API_KEY = os.environ.get("RAWG_API_KEY", "")
RAWG_BASE_URL = "https://api.rawg.io/api"
RAWG_TIMEOUT = 12  # segundos
RAWG_SCREENSHOTS_MAX = 6  # máximo de screenshots a salvar

# ─── Sufixos warez para limpeza de nome ──────────────────────────────────────
# Palavras que indicam grupos de repacks e devem ser removidas do nome digitado
WAREZ_SUFFIXES = {
    "repack", "fitgirl", "dodi", "skidrow", "codex", "gog", "steam",
    "crack", "plaza", "rg", "mechanics", "tencentgames", "elamigos",
    "igg", "igggames", "delusional", "cpy", "hoodlum", "razor1911",
    "empress", "kaos", "prophet", "darksisters", "multi", "update",
    "dlc", "patch", "hotfix", "v2", "v3", "edition", "cracked",
    "preinstalled", "portable", "complete", "goty", "deluxe",
}

# ─── Categorias válidas ───────────────────────────────────────────
CATEGORIAS = [
    "Jogo", "Curso", "Software"
]
