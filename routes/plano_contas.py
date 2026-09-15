from flask import Blueprint, render_template, request, redirect, url_for, abort
from database.connection import get_db
from utils.auth import login_required

plano_contas_bp = Blueprint("plano_contas", __name__)

TIPOS_VALIDOS = ("receita", "despesa", "transferencia")


@plano_contas_bp.route("/plano_contas")
@login_required
def plano_contas():

    categoria_editar_id = request.args.get("categoria_editar")
    plano_editar_id = request.args.get("plano_editar")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, codigo, nome, tipo
        FROM categorias_plano_contas
        ORDER BY codigo
    """)
    categorias = cursor.fetchall()

    cursor.execute("""
        SELECT id, codigo, nome, categoria_id
        FROM plano_contas
        ORDER BY codigo
    """)
    planos = cursor.fetchall()

    categoria_em_edicao = None
    if categoria_editar_id:

        try:
            categoria_editar_id = int(categoria_editar_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Categoria inválida.")
        
        cursor.execute("""
            SELECT id, codigo, nome, tipo
            FROM categorias_plano_contas
            WHERE id = %s
        """, (categoria_editar_id, ))
        categoria_em_edicao = cursor.fetchone()
    
    plano_em_edicao = None
    if plano_editar_id:
        try:
            plano_editar_id = int(plano_editar_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Plano de contas inválido.")
        
        cursor.execute("""
            SELECT id, codigo, nome, categoria_id
            FROM plano_contas
            WHERE id = %s
        """, (plano_editar_id, ))

        plano_em_edicao = cursor.fetchone()


    conn.close()

    return render_template(
        "plano_contas.html",
        categorias=categorias,
        planos=planos,
        categoria_em_edicao=categoria_em_edicao,
        plano_em_edicao=plano_em_edicao
    )
# NOVA CATEGORIA
@plano_contas_bp.route("/plano_contas/categoria/nova", methods=["POST"])
@login_required
def nova_categoria_plano_conta():

    codigo = (request.form.get("codigo") or "").strip()
    nome = (request.form.get("nome") or "").strip()
    tipo = (request.form.get("tipo") or "").strip()

    if not codigo or not nome or not tipo:
        abort(400, "Todos os campos são obrigatórios.")

    if tipo not in TIPOS_VALIDOS:
        abort(400, "Tipo inválido.")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM categorias_plano_contas WHERE codigo = %s", (codigo,))
    if cursor.fetchone():
        conn.close()
        abort(400, "Já existe uma categoria com este código.")

    try:
        cursor.execute("""
            INSERT INTO categorias_plano_contas (codigo, nome, tipo)
            VALUES (%s, %s, %s)
        """, (codigo, nome, tipo))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        abort(500, "Erro ao criar categoria.")

    conn.close()

    return redirect(url_for("plano_contas.plano_contas"))


# NOVO PLANO
@plano_contas_bp.route("/plano_contas/novo", methods=["POST"])
@login_required
def novo_plano_conta():

    codigo = (request.form.get("codigo") or "").strip()
    nome = (request.form.get("nome") or "").strip()
    categoria_id = request.form.get("categoria_id")

    if not codigo or not nome or not categoria_id:
        abort(400, "Todos os campos são obrigatórios.")

    try:
        categoria_id = int(categoria_id)
    except (TypeError, ValueError):
        abort(400, "Categoria inválida.")

    conn = get_db()
    cursor = conn.cursor()

    # Verifica se a categoria existe
    cursor.execute("SELECT id FROM categorias_plano_contas WHERE id = %s", (categoria_id,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Categoria não encontrada.")

    # Código único
    cursor.execute("SELECT id FROM plano_contas WHERE codigo = %s", (codigo,))
    if cursor.fetchone():
        conn.close()
        abort(400, "Já existe um plano de contas com este código.")

    try:
        cursor.execute("""
            INSERT INTO plano_contas (codigo, nome, categoria_id)
            VALUES (%s, %s, %s)
        """, (codigo, nome, categoria_id))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        abort(500, "Erro ao criar plano de contas.")

    conn.close()

    return redirect(url_for("plano_contas.plano_contas"))

# EDITAR CATEGORIA
@plano_contas_bp.route("/plano_contas/categoria/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_categoria_plano_conta(id):

    if request.method == "GET":

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id, codigo, nome, tipo FROM categorias_plano_contas WHERE id = %s", (id, ))
        categoria = cursor.fetchone()

        if not categoria:
            conn.close()
            abort(404, "Categoria não encontrada.")
        
        conn.close()
        return redirect(url_for("plano_contas.plano_contas", categoria_editar=id))

    if request.method == "POST":

        codigo = (request.form.get("codigo") or "").strip()
        nome = (request.form.get("nome") or "").strip()
        tipo = (request.form.get("tipo") or "").strip()

        if not codigo or not nome or not tipo:
            abort(400, "Todos os campos são obrigatórios.")

        if tipo not in TIPOS_VALIDOS:
            abort(400, "Tipo inválido.")

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM categorias_plano_contas WHERE id = %s", (id,))
        if not cursor.fetchone():
            conn.close()
            abort(404, "Categoria não encontrada.")

        cursor.execute("SELECT id FROM categorias_plano_contas WHERE codigo = %s AND id != %s", (codigo, id))
        if cursor.fetchone():
            conn.close()
            abort(400, "Já existe outra categoria com este código.")

        try:
            cursor.execute("""
                UPDATE categorias_plano_contas
                SET codigo = %s, nome = %s, tipo = %s
                WHERE id = %s
            """, (codigo, nome, tipo, id))

            conn.commit()

        except Exception as e:
            conn.rollback()
            print(e)
            abort(500, "Erro ao atualizar categoria.")

        conn.close()

    return redirect(url_for("plano_contas.plano_contas"))

# REMOVER CATEGORIA
@plano_contas_bp.route("/plano_contas/categoria/remover/<int:id>", methods=["POST"])
@login_required
def remover_categoria_plano_conta(id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM categorias_plano_contas WHERE id = %s", (id,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Categoria não existe.")

    # Segurança: não permitir se houver planos vinculados
    cursor.execute("SELECT id FROM plano_contas WHERE categoria_id = %s LIMIT 1", (id,))
    if cursor.fetchone():
        conn.close()
        abort(400, "Categoria possui planos vinculados.")

    try:
        cursor.execute("DELETE FROM categorias_plano_contas WHERE id = %s", (id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        abort(500, "Erro ao remover categoria.")

    conn.close()

    return redirect(url_for("plano_contas.plano_contas"))

# EDITAR PLANO
@plano_contas_bp.route("/plano_contas/plano/editar/<int:id>", methods=["GET","POST"])
@login_required
def editar_plano_conta(id):

    if request.method == "GET":

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, codigo, nome, categoria_id
            FROM plano_contas
            WHERE id = %s
        """, (id, ))
        plano = cursor.fetchone()

        if not plano:
            conn.close()
            abort(404, "Plano não encontrado.")
        
        conn.close()
        return redirect(url_for("plano_contas.plano_contas", plano_editar=id))        
        
    if request.method == "POST":

        codigo = (request.form.get("codigo") or "").strip()
        nome = (request.form.get("nome") or "").strip()
        categoria_id = request.form.get("categoria_id")

        if not codigo or not nome or not categoria_id:
            abort(400, "Todos os campos são obrigatórios.")

        try:
            categoria_id = int(categoria_id)
        except (TypeError, ValueError):
            abort(400, "Categoria inválida.")

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM plano_contas WHERE id = %s", (id,))
        if not cursor.fetchone():
            conn.close()
            abort(404, "Plano não encontrado.")

        cursor.execute("SELECT id FROM categorias_plano_contas WHERE id = %s", (categoria_id,))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Categoria não encontrada.")

        cursor.execute("SELECT id FROM plano_contas WHERE codigo = %s AND id != %s", (codigo, id))
        if cursor.fetchone():
            conn.close()
            abort(400, "Já existe outro plano com este código.")

        try:
            cursor.execute("""
                UPDATE plano_contas
                SET codigo = %s, nome = %s, categoria_id = %s
                WHERE id = %s
            """, (codigo, nome, categoria_id, id))

            conn.commit()

        except Exception as e:
            conn.rollback()
            print(e)
            abort(500, "Erro ao atualizar plano.")

        conn.close()

    return redirect(url_for("plano_contas.plano_contas"))

# REMOVER PLANO
@plano_contas_bp.route("/plano_contas/plano/remover/<int:id>", methods=["POST"])
@login_required
def remover_plano_conta(id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM plano_contas WHERE id = %s", (id,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Plano não existe.")

    # Segurança: verificar vínculos
    cursor.execute("SELECT id FROM contas_pagar WHERE plano_conta_id = %s LIMIT 1", (id,))
    if cursor.fetchone():
        conn.close()
        abort(400, "Plano vinculado a contas a pagar.")

    cursor.execute("SELECT id FROM contas_receber WHERE plano_conta_id = %s LIMIT 1", (id,))
    if cursor.fetchone():
        conn.close()
        abort(400, "Plano vinculado a contas a receber.")

    try:
        cursor.execute("DELETE FROM plano_contas WHERE id = %s", (id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        abort(500, "Erro ao remover plano.")

    conn.close()

    return redirect(url_for("plano_contas.plano_contas"))