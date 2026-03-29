"""
app.py — Ponto de entrada da aplicação Flask.
Rotas públicas, rotas administrativas e API REST para busca/filtro.
"""

import os
import json
import logging
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, abort, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

import config
import database as db
from utils import (
    gerar_slug, slug_unico, buscar_capa, gerar_imagem_default,
    deletar_arquivos_jogo, extensao_valida, salvar_upload,
    buscar_info_rawg, pesquisar_duckduckgo_info, pesquisar_duckduckgo_capa,
    extrair_tamanho_torrent, limpar_nome_torrent, adivinhar_categoria
)

# ─── Configuração de logs ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ─── Criação da app ──────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["SESSION_PERMANENT"] = config.SESSION_PERMANENT
app.config["PERMANENT_SESSION_LIFETIME"] = config.PERMANENT_SESSION_LIFETIME
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH


# ─── Inicialização ───────────────────────────────────────────────────────────
def inicializar_app():
    """Garante que as pastas existem, o banco está criado e a imagem padrão existe."""
    os.makedirs(config.UPLOADS_DIR, exist_ok=True)
    os.makedirs(config.COVERS_DIR, exist_ok=True)
    db.init_db()
    gerar_imagem_default()
    logger.info("Aplicação inicializada com sucesso.")


# ─── Decorador de autenticação ────────────────────────────────────────────────
def admin_required(f):
    """Redireciona para login se o admin não estiver autenticado."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Faça login para acessar o painel.", "warning")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ─── Context processors ──────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    """Injeta variáveis globais disponíveis em todos os templates."""
    return {
        "categorias": config.CATEGORIAS,
        "site_name": "TorrentZone",
    }


# ════════════════════════════════════════════════════════════════════════════
# ROTAS PÚBLICAS
# ════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Página principal com grid de jogos, filtros e paginação."""
    page = request.args.get("page", 1, type=int)
    query = request.args.get("q", "").strip()
    categoria = request.args.get("categoria", "")

    jogos, total = db.search_jogos(
        query=query,
        categoria=categoria,
        page=page,
        per_page=config.JOGOS_POR_PAGINA,
        current_user_id=session.get("user_id")
    )

    total_paginas = max(1, (total + config.JOGOS_POR_PAGINA - 1) // config.JOGOS_POR_PAGINA)

    return render_template(
        "index.html",
        jogos=jogos,
        page=page,
        total_paginas=total_paginas,
        total=total,
        query=query,
        categoria_filtro=categoria,
    )


@app.route("/jogo/<int:jogo_id>")
def jogo_detail(jogo_id):
    """Página de detalhes de um jogo."""
    jogo = db.get_jogo_by_id(jogo_id)
    if not jogo:
        abort(404)
        
    try:
        screenshots = json.loads(jogo.get("screenshots", "[]"))
    except Exception:
        screenshots = []
        
    comentarios = db.get_comentarios_jogo(jogo_id)
    total_curtidas = db.get_curtidas_count(jogo_id)
    curtiu = False
    favoritou = False
    
    user_id = session.get("user_id")
    if user_id:
        curtiu = db.user_curtiu_jogo(user_id, jogo_id)
        favoritou = db.user_favoritou_jogo(user_id, jogo_id)
        
    return render_template("jogo.html", 
        jogo=jogo, 
        screenshots=screenshots, 
        comentarios=comentarios, 
        total_curtidas=total_curtidas, 
        curtiu=curtiu,
        favoritou=favoritou
    )


@app.route("/download/<int:jogo_id>")
def download_torrent(jogo_id):
    """Serve o arquivo .torrent para download."""
    jogo = db.get_jogo_by_id(jogo_id)
    if not jogo or not jogo["torrent_path"]:
        abort(404)

    # torrent_path é relativo a /static/  ex: "uploads/arquivo.torrent"
    parts = jogo["torrent_path"].split("/", 1)
    if len(parts) != 2:
        abort(404)

    folder, filename = parts
    directory = os.path.join(app.static_folder, folder)
    return send_from_directory(directory, filename, as_attachment=True)


# ════════════════════════════════════════════════════════════════════════════
# API — Busca para JS (fetch com debounce)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/api/search")
def api_search():
    """
    API de busca/filtro para o JavaScript.
    Retorna JSON com lista de jogos e metadados de paginação.
    """
    query = request.args.get("q", "").strip()
    categoria = request.args.get("categoria", "")
    page = request.args.get("page", 1, type=int)

    jogos, total = db.search_jogos(
        query=query,
        categoria=categoria,
        page=page,
        per_page=config.JOGOS_POR_PAGINA,
        current_user_id=session.get("user_id")
    )

    total_paginas = max(1, (total + config.JOGOS_POR_PAGINA - 1) // config.JOGOS_POR_PAGINA)

    return jsonify({
        "jogos": jogos,
        "total": total,
        "page": page,
        "total_paginas": total_paginas,
    })


@app.route("/api/enrich")
@admin_required
def api_enrich():
    """
    Auto-enriquecimento do formulário admin via RAWG ou DuckDuckGo.
    """
    raw_name = request.args.get("q", "").strip()
    categoria = request.args.get("categoria", "Jogo")

    if len(raw_name) < 3:
        return jsonify({"encontrado": False})

    # Decisão baseada na categoria
    if categoria == "Jogo":
        dados = buscar_info_rawg(raw_name)
    else:
        dados = pesquisar_duckduckgo_info(raw_name, categoria)

    return jsonify({
        "dados_rawg": dados
    })


# ════════════════════════════════════════════════════════════════════════════
# ROTAS DE COMUNIDADE (Usuário, Curtidas, Comentários)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro_usuario():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        senha = request.form.get("senha", "")
        
        if not username or not senha:
            flash("Preencha todos os campos.", "error")
            return redirect(url_for("cadastro_usuario"))
            
        if db.get_user_by_username(username):
            flash("Nome de usuário já existe.", "error")
            return redirect(url_for("cadastro_usuario"))
            
        pwd_hash = generate_password_hash(senha)
        user_id = db.add_user(username, pwd_hash)
        session["user_id"] = user_id
        session["username"] = username
        session["avatar_url"] = f"https://api.dicebear.com/7.x/bottts/svg?seed={username}"
        flash("Bem-vindo(a) à comunidade DRIVEtorrent!", "success")
        return redirect(url_for("index"))

    return render_template("auth.html", mode="cadastro")


@app.route("/login", methods=["GET", "POST"])
def login_usuario():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        senha = request.form.get("senha", "")
        
        user = db.get_user_by_username(username)
        if user and check_password_hash(user["password_hash"], senha):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["avatar_url"] = user.get("avatar_url", f"https://api.dicebear.com/7.x/bottts/svg?seed={username}")
            flash("Login realizado com sucesso!", "success")
            return redirect(url_for("index"))
        else:
            flash("Usuário ou senha incorretos.", "error")
            
    return render_template("auth.html", mode="login")


@app.route("/logout")
def logout_usuario():
    # Only clear user specific session to preserve admin if they happen to be both, though structurally rare.
    session.pop("user_id", None)
    session.pop("username", None)
    session.pop("avatar_url", None)
    flash("Sessão encerrada.", "info")
    return redirect(url_for("index"))

@app.route("/perfil", methods=["GET", "POST"])
def user_perfil():
    user_id = session.get("user_id")
    if not user_id:
        flash("Faça login para acessar o perfil.", "warning")
        return redirect(url_for("login_usuario"))
        
    user = db.get_user_by_id(user_id)
        
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "update_avatar":
            novo_avatar = request.form.get("avatar_url")
            if novo_avatar:
                db.update_user_avatar(user_id, novo_avatar)
                session["avatar_url"] = novo_avatar
                flash("Avatar atualizado com sucesso!", "success")
                
        elif action == "update_info":
            novo_username = request.form.get("username", "").strip()
            novo_email = request.form.get("email", "").strip()
            
            if novo_username:
                if db.check_user_exists(novo_username, novo_email, exclude_id=user_id):
                    flash("Nome de usuário ou email já estão em uso por outra conta.", "danger")
                else:
                    db.update_user_info(user_id, novo_username, novo_email)
                    session["username"] = novo_username
                    flash("Informações atualizadas com sucesso!", "success")
            else:
                flash("O nome de usuário não pode ficar vazio.", "warning")
                
        elif action == "update_password":
            senha_atual = request.form.get("senha_atual")
            nova_senha = request.form.get("nova_senha")
            confirmar_senha = request.form.get("confirmar_senha")
            
            if check_password_hash(user["password_hash"], senha_atual):
                if nova_senha == confirmar_senha and len(nova_senha) >= 4:
                    db.update_user_password(user_id, generate_password_hash(nova_senha))
                    flash("Senha atualizada com segurança!", "success")
                else:
                    flash("A nova senha não confere ou é muito curta (min. 4 chars).", "danger")
            else:
                flash("A senha atual informada está incorreta.", "danger")
        
        return redirect(url_for("user_perfil"))
        
    favoritos = db.get_user_favorites(user_id)
    comentarios = db.get_user_comments_history(user_id)
    return render_template("perfil.html", user=user, favoritos=favoritos, comentarios=comentarios)


@app.route("/api/jogo/<int:jogo_id>/curtir", methods=["POST"])
def api_curtir(jogo_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "unauthorized"}), 401
    
    status = db.toggle_curtida(user_id, jogo_id)
    total = db.get_curtidas_count(jogo_id)
    return jsonify({"success": True, "curtiu": status, "total": total})


@app.route("/api/jogo/<int:jogo_id>/favoritar", methods=["POST"])
def api_favoritar(jogo_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "unauthorized"}), 401
    
    status = db.toggle_favorito(user_id, jogo_id)
    return jsonify({"success": True, "favoritou": status})


@app.route("/jogo/<int:jogo_id>/comentar", methods=["POST"])
def comentar_jogo(jogo_id):
    user_id = session.get("user_id")
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json
    
    if not user_id:
        if is_ajax:
            return jsonify({"success": False, "message": "Faça login para comentar."}), 401
        flash("Você precisa estar logado para comentar.", "error")
        return redirect(url_for("login_usuario"))
        
    # Pega texto do form ou JSON
    if request.is_json:
        texto = request.json.get("texto", "").strip()
    else:
        texto = request.form.get("texto", "").strip()
        
    if texto:
        db.add_comentario(user_id, jogo_id, texto)
        
        if is_ajax:
            from datetime import datetime
            data_postagem = datetime.now().strftime("%Y-%m-%d %H:%M")
            username = session.get("username")
            avatar_url = session.get("avatar_url") or f"https://api.dicebear.com/7.x/bottts/svg?seed={username}"
            return jsonify({
                "success": True, 
                "comentario": {
                    "texto": texto,
                    "data_postagem": data_postagem,
                    "username": username,
                    "avatar_url": avatar_url
                }
            })
            
        flash("Comentário publicado!", "success")
    else:
        if is_ajax:
            return jsonify({"success": False, "message": "O comentário não pode ser vazio."}), 400
        flash("O comentário não pode estar vazio.", "error")
        
    return redirect(url_for("jogo_detail", jogo_id=jogo_id) + "#comentarios")


# ════════════════════════════════════════════════════════════════════════════
# ROTAS ADMIN
# ════════════════════════════════════════════════════════════════════════════

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Login do painel administrativo."""
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        senha = request.form.get("senha", "")
        if senha == config.ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            flash("Login realizado com sucesso!", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Senha incorreta. Tente novamente.", "error")

    return render_template("admin_login.html")


@app.route("/admin/logout")
@admin_required
def admin_logout():
    """Encerra a sessão do admin."""
    session.clear()
    flash("Você saiu do painel.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    """Painel principal com listagem de todos os jogos."""
    page = request.args.get("page", 1, type=int)
    query = request.args.get("q", "").strip()
    jogos, total = db.search_jogos(query=query, page=page, per_page=20)
    total_paginas = max(1, (total + 19) // 20)

    # Para edição inline, passamos o jogo a editar se houver
    edit_id = request.args.get("edit")
    jogo_edit = db.get_jogo_by_id(int(edit_id)) if edit_id and edit_id.isdigit() else None

    return render_template(
        "admin_dashboard.html",
        jogos=jogos,
        total=total,
        page=page,
        total_paginas=total_paginas,
        edit_id=edit_id,
        jogo_edit=jogo_edit
    )


@app.route("/admin/api/lista_ids")
@admin_required
def admin_api_lista_ids():
    """Retorna lista de todos os IDs para processamento em lote via AJAX."""
    all_jogos = db.get_all_jogos_simple()
    return jsonify([j["id"] for j in all_jogos])


@app.route("/admin/api/analisar_item/<int:jogo_id>", methods=["POST"])
@admin_required
def admin_api_analisar_item(jogo_id):
    """Anatisa um único item: ajusta categoria e busca capa se faltar."""
    try:
        jogo = db.get_jogo_by_id(jogo_id)
        if not jogo:
            return jsonify({"error": "Não encontrado"}), 404
            
        nome = jogo["nome"]
        cat_atual = jogo["categoria"]
        capa_atual = jogo["capa_path"]
        
        # 1. Sugere nova categoria
        nova_cat = adivinhar_categoria(nome)
        
        # 2. Busca capa se necessário
        nova_capa = capa_atual
        if capa_atual == "covers/default.jpg":
            slug = jogo["slug"]
            if nova_cat == "Jogo":
                nova_capa = buscar_capa(nome, slug)
            else:
                nova_capa = pesquisar_duckduckgo_capa(nome, nova_cat, slug)
        
        # 3. Atualiza se houver mudança
        mudou = False
        if nova_cat != cat_atual or nova_capa != capa_atual:
            db.update_jogo(
                jogo_id,
                nome=nome,
                slug=jogo["slug"],
                categoria=nova_cat,
                tamanho=jogo["tamanho"],
                descricao=jogo["descricao"],
                capa_path=nova_capa,
                torrent_path=jogo["torrent_path"],
                screenshots=jogo["screenshots"],
                youtube_url=jogo["youtube_url"]
            )
            mudou = True
            
        return jsonify({
            "success": True,
            "nome": nome,
            "mudou": mudou,
            "nova_cat": nova_cat,
            "tem_capa": nova_capa != "covers/default.jpg"
        })
    except Exception as e:
        logger.error("Erro ao analisar item %s: %s", jogo_id, e)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/analisar_torrents", methods=["POST"])
@admin_required
def admin_analisar_torrents():
    """
    Varre todos os torrents no banco:
    1. Atualiza categoria baseada no nome (adivinhar).
    2. Busca capa se for a padrão.
    """
    try:
        page = 1
        per_page = 100
        total_atualizados = 0
        
        while True:
            jogos, total = db.get_all_jogos(page=page, per_page=per_page)
            if not jogos:
                break
                
            for jogo in jogos:
                id_jogo = jogo["id"]
                nome = jogo["nome"]
                cat_atual = jogo["categoria"]
                capa_atual = jogo["capa_path"]
                
                # 1. Sugere nova categoria
                nova_cat = adivinhar_categoria(nome)
                
                # 2. Busca capa se necessário
                nova_capa = capa_atual
                if capa_atual == "covers/default.jpg":
                    slug = jogo["slug"]
                    if nova_cat == "Jogo":
                        nova_capa = buscar_capa(nome, slug)
                    else:
                        nova_capa = pesquisar_duckduckgo_capa(nome, nova_cat, slug)
                
                # 3. Atualiza se houver mudança
                if nova_cat != cat_atual or nova_capa != capa_atual:
                    # Mantemos os outros campos como estão
                    db.update_jogo(
                        id_jogo,
                        nome=jogo["nome"],
                        slug=jogo["slug"],
                        categoria=nova_cat,
                        tamanho=jogo["tamanho"],
                        descricao=jogo["descricao"],
                        capa_path=nova_capa,
                        torrent_path=jogo["torrent_path"],
                        screenshots=jogo["screenshots"],
                        youtube_url=jogo["youtube_url"]
                    )
                    total_atualizados += 1
            
            if len(jogos) < per_page:
                break
            page += 1
            
        flash(f"Análise concluída! {total_atualizados} torrents foram atualizados.", "success")
    except Exception as e:
        logger.error("Erro na análise em lote: %s", e)
        flash("Erro durante a análise em lote.", "error")
        
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/adicionar", methods=["POST"])
@admin_required
def admin_adicionar():
    """Processa o formulário de adição de novo jogo."""
    nome = request.form.get("nome", "").strip()
    categoria = request.form.get("categoria", "")
    tamanho_form = request.form.get("tamanho", "0")
    descricao = request.form.get("descricao", "").strip()

    # ─── Validações ───────────────────────────────────────────────────────
    if not nome:
        flash("O nome do jogo é obrigatório.", "error")
        return redirect(url_for("admin_dashboard"))

    if categoria not in config.CATEGORIAS:
        flash("Categoria inválida.", "error")
        return redirect(url_for("admin_dashboard"))

    try:
        tamanho = float(tamanho_form)
    except ValueError:
        tamanho = 0.0

    if db.check_duplicate(nome, categoria):
        flash(f'"{nome}" para {categoria} já está cadastrado.', "error")
        return redirect(url_for("admin_dashboard"))

    # ─── Slug ─────────────────────────────────────────────────────────────
    slug = slug_unico(nome, db.get_jogo_by_slug)

    # ─── Capa ─────────────────────────────────────────────────────────────
    capa_path = "covers/default.jpg"
    file_capa = request.files.get("capa")
    if file_capa and file_capa.filename:
        if extensao_valida(file_capa.filename, config.ALLOWED_IMAGE_EXTENSIONS):
            _, ext = os.path.splitext(file_capa.filename.lower())
            capa_path = salvar_upload(file_capa, config.COVERS_DIR, slug, ext)
        else:
            flash("Formato de imagem inválido. Use JPG, PNG ou WEBP.", "warning")
            capa_path = buscar_capa(nome, slug) if categoria == "Jogo" else pesquisar_duckduckgo_capa(nome, categoria, slug)
    else:
        capa_path = buscar_capa(nome, slug) if categoria == "Jogo" else pesquisar_duckduckgo_capa(nome, categoria, slug)

    # ─── Torrent ──────────────────────────────────────────────────────────
    torrent_path = ""
    file_torrent = request.files.get("torrent")
    if file_torrent and file_torrent.filename:
        if extensao_valida(file_torrent.filename, config.ALLOWED_TORRENT_EXTENSIONS):
            torrent_path = salvar_upload(file_torrent, config.UPLOADS_DIR, slug, ".torrent")
            # Extrai o tamanho real do torrent se anexado
            full_torrent_path = os.path.join(app.static_folder, torrent_path)
            tamanho_real = extrair_tamanho_torrent(full_torrent_path)
            if tamanho_real > 0:
                tamanho = tamanho_real
        else:
            flash("Apenas arquivos .torrent são aceitos.", "error")
            return redirect(url_for("admin_dashboard"))

    # ─── Novos campos API ─────────────────────────────────────────────────
    screenshots = request.form.get("screenshots", "[]")
    youtube_url = request.form.get("youtube_url", "")

    # ─── Salvar ───────────────────────────────────────────────────────────
    jogo_id = db.add_jogo(nome, slug, categoria, tamanho,
                          descricao, capa_path, torrent_path,
                          screenshots=screenshots, youtube_url=youtube_url)
    flash(f'"{nome}" adicionado com sucesso!', "success")
    logger.info("Jogo adicionado: id=%s nome=%s", jogo_id, nome)
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/editar/<int:jogo_id>", methods=["POST"])
@admin_required
def admin_editar(jogo_id):
    """Processa o formulário de edição de um jogo existente."""
    jogo = db.get_jogo_by_id(jogo_id)
    if not jogo:
        flash("Jogo não encontrado.", "error")
        return redirect(url_for("admin_dashboard"))

    nome = request.form.get("nome", "").strip()
    categoria = request.form.get("categoria", "")
    descricao = request.form.get("descricao", "").strip()

    try:
        tamanho = float(request.form.get("tamanho", "0"))
    except ValueError:
        tamanho = 0.0

    if not nome:
        flash("O nome é obrigatório.", "error")
        return redirect(url_for("admin_dashboard", edit=jogo_id))

    if db.check_duplicate(nome, categoria, exclude_id=jogo_id):
        flash(f'"{nome}" para {categoria} já está cadastrado.', "error")
        return redirect(url_for("admin_dashboard", edit=jogo_id))

    # Recalcula slug só se o nome mudou
    if nome != jogo["nome"]:
        slug = slug_unico(nome, db.get_jogo_by_slug)
    else:
        slug = jogo["slug"]

    # ─── Capa ─────────────────────────────────────────────────────────────
    capa_path = jogo["capa_path"]
    file_capa = request.files.get("capa")
    if file_capa and file_capa.filename:
        if extensao_valida(file_capa.filename, config.ALLOWED_IMAGE_EXTENSIONS):
            _, ext = os.path.splitext(file_capa.filename.lower())
            nova_capa = salvar_upload(file_capa, config.COVERS_DIR, slug, ext)
            # Remove a capa antiga se não for default
            if jogo["capa_path"] != "covers/default.jpg":
                deletar_arquivos_jogo(jogo["capa_path"], "")
            capa_path = nova_capa
        else:
            flash("Formato de imagem inválido.", "warning")

    # ─── Torrent ──────────────────────────────────────────────────────────
    torrent_path = jogo["torrent_path"]
    file_torrent = request.files.get("torrent")
    if file_torrent and file_torrent.filename:
        if extensao_valida(file_torrent.filename, config.ALLOWED_TORRENT_EXTENSIONS):
            novo_torrent = salvar_upload(file_torrent, config.UPLOADS_DIR, slug, ".torrent")
            # Extrai tamanho e sobrescreve
            full_torrent_path = os.path.join(app.static_folder, novo_torrent)
            tamanho_real = extrair_tamanho_torrent(full_torrent_path)
            if tamanho_real > 0:
                tamanho = tamanho_real
                
            # Remove o torrent antigo
            if jogo["torrent_path"]:
                deletar_arquivos_jogo("", jogo["torrent_path"])
            torrent_path = novo_torrent
        else:
            flash("Apenas arquivos .torrent são aceitos.", "error")
            return redirect(url_for("admin_dashboard", edit=jogo_id))

    # ─── Novos campos API ─────────────────────────────────────────────────
    screenshots = request.form.get("screenshots", "[]")
    youtube_url = request.form.get("youtube_url", "")

    db.update_jogo(jogo_id, nome, slug, categoria, tamanho,
                   descricao, capa_path, torrent_path,
                   screenshots=screenshots, youtube_url=youtube_url)
    flash(f'"{nome}" atualizado com sucesso!', "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/bulk_upload", methods=["POST"])
@admin_required
def admin_bulk_upload():
    """
    Processa um único arquivo de um lote (chamado via JS em loop).
    Garante enriquecimento automático completo.
    """
    file_torrent = request.files.get("torrent")
    categoria = request.form.get("categoria", "Jogo")

    if not file_torrent or not file_torrent.filename:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    if not extensao_valida(file_torrent.filename, config.ALLOWED_TORRENT_EXTENSIONS):
        return jsonify({"error": "Apenas .torrent é permitido"}), 400

    from utils import limpar_nome_torrent
    nome_limpo = limpar_nome_torrent(file_torrent.filename)
    
    # Verifica duplicata
    if db.check_duplicate(nome_limpo, categoria):
        return jsonify({"error": f"'{nome_limpo}' já existe nesta categoria."}), 409

    slug = slug_unico(nome_limpo, db.get_jogo_by_slug)
    
    try:
        # 1. Salva Torrent Temporário para extrair tamanho
        temp_path = salvar_upload(file_torrent, config.UPLOADS_DIR, slug, ".torrent")
        full_temp_path = os.path.join(app.static_folder, temp_path)
        tamanho = extrair_tamanho_torrent(full_temp_path)
        
        # 2. Enriquecimento Automático
        descricao = ""
        screenshots = "[]"
        youtube_url = ""
        capa_path = "covers/default.jpg"

        if categoria == "Jogo":
            info = buscar_info_rawg(nome_limpo)
            if not info["encontrado"]:
                # Fallback DDGS se RAWG falhar
                info = pesquisar_duckduckgo_info(nome_limpo, categoria)
            
            nome_limpo = info["nome"] # Nome mais oficial se encontrado
            descricao = info["descricao"]
            screenshots = json.dumps(info["screenshots"])
            youtube_url = info["youtube_url"]
            capa_path = buscar_capa(nome_limpo, slug)
        else:
            # Para Cursos/Softwares, usa DuckDuckGo
            info = pesquisar_duckduckgo_info(nome_limpo, categoria)
            descricao = info["descricao"]
            screenshots = json.dumps(info["screenshots"])
            youtube_url = info["youtube_url"]
            capa_path = pesquisar_duckduckgo_capa(nome_limpo, categoria, slug)

        # 3. Salva no Banco
        db.add_jogo(
            nome=nome_limpo,
            slug=slug,
            categoria=categoria,
            tamanho=tamanho,
            descricao=descricao,
            capa_path=capa_path,
            torrent_path=temp_path,
            screenshots=screenshots,
            youtube_url=youtube_url
        )

        return jsonify({
            "success": True, 
            "nome": nome_limpo,
            "tamanho": tamanho
        })

    except Exception as e:
        logger.error("Erro no bulk upload de '%s': %s", file_torrent.filename, e)
        return jsonify({"error": str(e)}), 500


@app.route("/admin/excluir/<int:jogo_id>", methods=["POST"])
@admin_required
def admin_excluir(jogo_id):
    """Remove um jogo do banco e seus arquivos físicos."""
    jogo = db.delete_jogo(jogo_id)
    if jogo:
        deletar_arquivos_jogo(jogo["capa_path"], jogo["torrent_path"])
        flash(f'"{jogo["nome"]}" excluído com sucesso.', "success")
        logger.info("Jogo excluído: id=%s nome=%s", jogo_id, jogo["nome"])
    else:
        flash("Jogo não encontrado.", "error")
    return redirect(url_for("admin_dashboard"))


# ─── Tratamento de erros ──────────────────────────────────────────────────────
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(413)
def request_entity_too_large(e):
    flash("Arquivo muito grande. Limite: 512 MB.", "error")
    return redirect(request.referrer or url_for("admin_dashboard"))


# ─── Entrypoint ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    inicializar_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
