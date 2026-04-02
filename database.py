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
            
            -- Comunidade
            CREATE TABLE IF NOT EXISTS usuarios (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT    NOT NULL UNIQUE,
                password_hash TEXT  NOT NULL,
                data_cadastro TEXT  NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS curtidas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                jogo_id     INTEGER NOT NULL,
                UNIQUE(user_id, jogo_id),
                FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE,
                FOREIGN KEY (jogo_id) REFERENCES jogos(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS comentarios (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                jogo_id     INTEGER NOT NULL,
                texto       TEXT    NOT NULL,
                data_postagem TEXT  NOT NULL,
                FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE,
                FOREIGN KEY (jogo_id) REFERENCES jogos(id) ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_curtidas_jogo ON curtidas(jogo_id);
            CREATE INDEX IF NOT EXISTS idx_comentarios_jogo ON comentarios(jogo_id);
            CREATE INDEX IF NOT EXISTS idx_comentarios_jogo ON comentarios(jogo_id);
            
            -- Favoritos separados
            CREATE TABLE IF NOT EXISTS favoritos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                jogo_id     INTEGER NOT NULL,
                UNIQUE(user_id, jogo_id),
                FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE,
                FOREIGN KEY (jogo_id) REFERENCES jogos(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_favoritos_jogo ON favoritos(jogo_id);
        """)

        # Necessário para habilitar FKs globais no SQLite
        conn.execute("PRAGMA foreign_keys = ON;")

        # ─ Migrações incrementais: adiciona colunas novas sem recriar a tabela ─
        _add_column_if_missing(conn, "jogos", "screenshots",  "TEXT DEFAULT '[]'")
        _add_column_if_missing(conn, "jogos", "youtube_url",  "TEXT DEFAULT ''")
        _add_column_if_missing(conn, "usuarios", "avatar_url", "TEXT DEFAULT ''")
        _add_column_if_missing(conn, "usuarios", "email", "TEXT DEFAULT ''")


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


def get_all_jogos(page=1, per_page=12, current_user_id=None):
    """Retorna todos os jogos paginados, ordenados por data decrescente."""
    offset = (page - 1) * per_page
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jogos").fetchone()[0]
        
        # Subqueries para likes e favs personalizados
        like_sub = "(SELECT 1 FROM curtidas WHERE jogo_id = j.id AND user_id = ?) as is_liked"
        fav_sub = "(SELECT 1 FROM favoritos WHERE jogo_id = j.id AND user_id = ?) as is_favorited"
        
        rows = conn.execute(
            f"""SELECT j.*, 
                (SELECT COUNT(*) FROM curtidas WHERE jogo_id = j.id) as total_curtidas,
                {like_sub}, {fav_sub}
               FROM jogos j
               ORDER BY j.data_adicao DESC LIMIT ? OFFSET ?""",
            (current_user_id, current_user_id, per_page, offset)
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


def get_jogos_sem_capa():
    """Retorna todos os jogos que ainda estão com a capa padrão."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM jogos WHERE capa_path = 'covers/default.jpg' ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def update_jogo_capa(jogo_id, capa_path):
    """Atualiza apenas a capa de um jogo."""
    with get_db() as conn:
        conn.execute(
            "UPDATE jogos SET capa_path = ? WHERE id = ?",
            (capa_path, jogo_id)
        )


# ─── COMUNIDADE (Usuários, Curtidas, Comentários) ────────────────────────────

def get_user_by_username(username):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM usuarios WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None

def get_user_by_id(user_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None

def add_user(username, password_hash):
    data_cadastro = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Default avatar via DiceBear
    default_avatar = f"https://api.dicebear.com/7.x/bottts/svg?seed={username}"
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO usuarios (username, password_hash, data_cadastro, avatar_url) VALUES (?, ?, ?, ?)",
            (username, password_hash, data_cadastro, default_avatar)
        )
        return cursor.lastrowid

def update_user_avatar(user_id, avatar_url):
    with get_db() as conn:
        conn.execute("UPDATE usuarios SET avatar_url = ? WHERE id = ?", (avatar_url, user_id))

def update_user_info(user_id, username, email):
    with get_db() as conn:
        conn.execute("UPDATE usuarios SET username = ?, email = ? WHERE id = ?", (username, email, user_id))

def update_user_password(user_id, password_hash):
    with get_db() as conn:
        conn.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", (password_hash, user_id))

def check_user_exists(username, email, exclude_id=None):
    with get_db() as conn:
        if exclude_id:
            row = conn.execute("SELECT id FROM usuarios WHERE (username = ? OR (email != '' AND email = ?)) AND id != ?", (username, email, exclude_id)).fetchone()
        else:
            row = conn.execute("SELECT id FROM usuarios WHERE username = ? OR (email != '' AND email = ?)", (username, email)).fetchone()
    return bool(row)

def get_user_favorites(user_id):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT j.*, (SELECT COUNT(*) FROM curtidas WHERE jogo_id = j.id) as total_curtidas
            FROM jogos j
            JOIN favoritos f ON f.jogo_id = j.id
            WHERE f.user_id = ?
            ORDER BY j.nome ASC
        """, (user_id,)).fetchall()
    return [dict(r) for r in rows]

def get_user_comments_history(user_id):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT c.id, c.texto, c.data_postagem, j.nome as jogo_nome, j.id as jogo_id, j.slug as jogo_slug
            FROM comentarios c
            JOIN jogos j ON c.jogo_id = j.id
            WHERE c.user_id = ?
            ORDER BY c.data_postagem DESC
            LIMIT 50
        """, (user_id,)).fetchall()
    return [dict(r) for r in rows]

def toggle_curtida(user_id, jogo_id):
    """Adiciona a curtida se não existir, ou remove se existir (Toggle). Retorna True se curtiu, False se removeu."""
    with get_db() as conn:
        existe = conn.execute("SELECT 1 FROM curtidas WHERE user_id = ? AND jogo_id = ?", (user_id, jogo_id)).fetchone()
        if existe:
            conn.execute("DELETE FROM curtidas WHERE user_id = ? AND jogo_id = ?", (user_id, jogo_id))
            return False
        else:
            conn.execute("INSERT INTO curtidas (user_id, jogo_id) VALUES (?, ?)", (user_id, jogo_id))
            return True

def get_curtidas_count(jogo_id):
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) FROM curtidas WHERE jogo_id = ?", (jogo_id,)).fetchone()
    return row[0]

def user_curtiu_jogo(user_id, jogo_id):
    if not user_id: return False
    with get_db() as conn:
        row = conn.execute("SELECT 1 FROM curtidas WHERE user_id = ? AND jogo_id = ?", (user_id, jogo_id)).fetchone()
    return bool(row)

def toggle_favorito(user_id, jogo_id):
    """Adiciona o favorito se não existir, ou remove se existir (Toggle)."""
    with get_db() as conn:
        existe = conn.execute("SELECT 1 FROM favoritos WHERE user_id = ? AND jogo_id = ?", (user_id, jogo_id)).fetchone()
        if existe:
            conn.execute("DELETE FROM favoritos WHERE user_id = ? AND jogo_id = ?", (user_id, jogo_id))
            return False
        else:
            conn.execute("INSERT INTO favoritos (user_id, jogo_id) VALUES (?, ?)", (user_id, jogo_id))
            return True

def user_favoritou_jogo(user_id, jogo_id):
    if not user_id: return False
    with get_db() as conn:
        row = conn.execute("SELECT 1 FROM favoritos WHERE user_id = ? AND jogo_id = ?", (user_id, jogo_id)).fetchone()
    return bool(row)

def add_comentario(user_id, jogo_id, texto):
    data_postagem = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO comentarios (user_id, jogo_id, texto, data_postagem) VALUES (?, ?, ?, ?)",
            (user_id, jogo_id, texto, data_postagem)
        )
        return cursor.lastrowid

def get_comentarios_jogo(jogo_id):
    """Retorna os comentários de um jogo, com o nome do autor acoplado."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT c.id, c.texto, c.data_postagem, u.username, u.id as user_id, u.avatar_url
            FROM comentarios c
            JOIN usuarios u ON c.user_id = u.id
            WHERE c.jogo_id = ?
            ORDER BY c.data_postagem DESC
        """, (jogo_id,)).fetchall()
    return [dict(r) for r in rows]


def search_jogos(query="", categoria="", page=1, per_page=12, current_user_id=None):
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

    # Subqueries para likes e favs personalizados
    like_sub = "(SELECT 1 FROM curtidas WHERE jogo_id = j.id AND user_id = ?) as is_liked"
    fav_sub = "(SELECT 1 FROM favoritos WHERE jogo_id = j.id AND user_id = ?) as is_favorited"

    with get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM jogos {where_clause}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""SELECT j.*, 
                (SELECT COUNT(*) FROM curtidas WHERE jogo_id = j.id) as total_curtidas,
                {like_sub}, {fav_sub}
                FROM jogos j {where_clause}
                ORDER BY j.data_adicao DESC LIMIT ? OFFSET ?""",
            params + [current_user_id, current_user_id, per_page, offset]
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
