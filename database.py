"""
database.py — Camada de acesso a dados (SQLite).
CRUD completo + busca + filtros para a tabela de jogos.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from config import DATABASE_PATH


# ─── Gerenciador de contexto ─────────────────────────────────────────────────
@contextmanager
def get_db():
    """Abre uma conexão com o banco e garante o fechamento correto."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # acesso por nome de coluna
    conn.execute("PRAGMA journal_mode=WAL")  # melhor performance em leitura concorrente
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── Inicialização ───────────────────────────────────────────────────────────
def init_db():
    """Cria as tabelas se não existirem e aplica migrações incrementais."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jogos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nome        TEXT    NOT NULL,
                slug        TEXT    NOT NULL UNIQUE,
                categoria   TEXT    NOT NULL,
                tamanho     REAL    NOT NULL DEFAULT 0,
                descricao   TEXT    DEFAULT '',
                capa_path   TEXT    DEFAULT 'covers/default.jpg',
                torrent_path TEXT   DEFAULT '',
                data_adicao TEXT    NOT NULL,
                screenshots TEXT    DEFAULT '[]',
                youtube_url TEXT    DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_jogos_slug       ON jogos(slug);
            CREATE INDEX IF NOT EXISTS idx_jogos_nome       ON jogos(nome);
            CREATE INDEX IF NOT EXISTS idx_jogos_categoria  ON jogos(categoria);
        """)

        # ─ Migrações incrementais: adiciona colunas novas sem recriar a tabela ─
        _add_column_if_missing(conn, "jogos", "screenshots",  "TEXT DEFAULT '[]'")
        _add_column_if_missing(conn, "jogos", "youtube_url",  "TEXT DEFAULT ''")


def _add_column_if_missing(conn, table: str, column: str, definition: str):
    """Adiciona uma coluna à tabela se ela ainda não existir."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


# ─── CRUD ────────────────────────────────────────────────────────────────────
def add_jogo(nome, slug, categoria, tamanho, descricao,
             capa_path, torrent_path, screenshots="[]", youtube_url=""):
    """Insere um novo jogo e retorna seu id."""
    data_adicao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO jogos
               (nome, slug, categoria, tamanho, descricao,
                capa_path, torrent_path, data_adicao, screenshots, youtube_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (nome, slug, categoria, tamanho, descricao,
             capa_path, torrent_path, data_adicao, screenshots, youtube_url)
        )
        return cursor.lastrowid


def get_all_jogos(page=1, per_page=12):
    """Retorna todos os jogos paginados, ordenados por data decrescente."""
    offset = (page - 1) * per_page
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jogos").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM jogos ORDER BY data_adicao DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()
    return [dict(r) for r in rows], total


def get_all_jogos_simple():
    """Retorna IDs e nomes de TODOS os jogos (sem paginação)."""
    with get_db() as conn:
        rows = conn.execute("SELECT id, nome FROM jogos ORDER BY id ASC").fetchall()
    return [dict(r) for r in rows]


def get_jogo_by_id(jogo_id):
    """Retorna um jogo pelo id ou None se não encontrado."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM jogos WHERE id = ?", (jogo_id,)
        ).fetchone()
    return dict(row) if row else None


def get_jogo_by_slug(slug):
    """Retorna um jogo pelo slug ou None se não encontrado."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM jogos WHERE slug = ?", (slug,)
        ).fetchone()
    return dict(row) if row else None


def update_jogo(jogo_id, nome, slug, categoria, tamanho,
                descricao, capa_path, torrent_path, screenshots=None, youtube_url=None):
    """Atualiza os dados de um jogo existente."""
    with get_db() as conn:
        # Busca valores atuais para não sobrescrever com None
        row = conn.execute("SELECT screenshots, youtube_url FROM jogos WHERE id=?",
                           (jogo_id,)).fetchone()
        _screenshots = screenshots if screenshots is not None else (row[0] if row else "[]")
        _youtube_url = youtube_url if youtube_url is not None else (row[1] if row else "")

        conn.execute(
            """UPDATE jogos SET
               nome=?, slug=?, categoria=?, tamanho=?,
               descricao=?, capa_path=?, torrent_path=?,
               screenshots=?, youtube_url=?
               WHERE id=?""",
            (nome, slug, categoria, tamanho,
             descricao, capa_path, torrent_path,
             _screenshots, _youtube_url, jogo_id)
        )


def delete_jogo(jogo_id):
    """Remove um jogo pelo id e retorna seus dados (para limpeza de arquivos)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM jogos WHERE id = ?", (jogo_id,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM jogos WHERE id = ?", (jogo_id,))
    return dict(row) if row else None


def search_jogos(query="", categoria="", page=1, per_page=12):
    """Busca/filtra jogos com suporte a query de texto + filtros combinados."""
    conditions = []
    params = []

    if query:
        conditions.append("(nome LIKE ? OR categoria LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like])

    if categoria:
        conditions.append("categoria = ?")
        params.append(categoria)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * per_page

    with get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM jogos {where_clause}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM jogos {where_clause} ORDER BY data_adicao DESC LIMIT ? OFFSET ?",
            params + [per_page, offset]
        ).fetchall()

    return [dict(r) for r in rows], total


def check_duplicate(nome, categoria, exclude_id=None):
    """Verifica se já existe um jogo com o mesmo nome e categoria."""
    with get_db() as conn:
        if exclude_id:
            row = conn.execute(
                "SELECT id FROM jogos WHERE nome=? AND categoria=? AND id!=?",
                (nome, categoria, exclude_id)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM jogos WHERE nome=? AND categoria=?",
                (nome, categoria)
            ).fetchone()
    return row is not None
