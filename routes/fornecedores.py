from flask import Blueprint, render_template, request, redirect, url_for, abort

from database.connection import get_db
from utils.auth import login_required

fornecedores_bp = Blueprint("fornecedores", __name__)

@fornecedores_bp.route("/fornecedores")
@login_required
def fornecedores():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nome, telefone, email, cpf, cnpj
        FROM fornecedores
        ORDER BY nome
    """)

    lista_fornecedores = cursor.fetchall()
    total_fornecedores = len(lista_fornecedores)

    conn.close()

    return render_template(
        "fornecedores.html",
        lista_fornecedores=lista_fornecedores,
        total_fornecedores=total_fornecedores,
    )

@fornecedores_bp.route("/fornecedores/novo", methods=["POST"])
@login_required
def novo_fornecedor():

    nome = request.form.get("nome")
    telefone = request.form.get("telefone")
    email = request.form.get("email")
    cpf = request.form.get("cpf")
    cnpj = request.form.get("cnpj")

    if not nome:
        abort(400, "Nome do fornecedor é obrigatório.")

    if telefone:
        try:
            telefone = telefone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        except (ValueError, TypeError):
            abort(400, "Número de telefone inválido, preencha apenas os números")

    if email and ("@" not in email or "." not in email):
        abort(400, "Endereço de e-mail inválido.")
    

    if cpf and cnpj:
        abort(400, "Informe apenas CPF ou CNPJ.")


    if cpf and not cnpj:
        try:
            cpf = cpf.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        except (ValueError, TypeError):
            abort(400, "Número de documento inválido, preencha apenas os números")

    if cnpj and not cpf:
        try:
            cnpj = cnpj.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        except (ValueError, TypeError):
            abort(400, "Número de documento inválido, preencha apenas os números")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT nome FROM fornecedores WHERE nome = %s", (nome, ))
    nome_existente = cursor.fetchone()

    if nome_existente:
        conn.close()
        abort(400, "Este fornecedor já foi registrado em nosso sistema.") 

    try:
        cursor.execute(
            "INSERT INTO fornecedores (nome, telefone, email, CPF, CNPJ) VALUES (%s, %s, %s, %s, %s)",
            (nome, telefone, email, cpf, cnpj)
        )

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        abort(500, "Erro ao criar fornecedor.")

    conn.close()

    return redirect(url_for("fornecedores.fornecedores"))

@fornecedores_bp.route("/fornecedores/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_fornecedor(id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, nome, telefone, email, cpf, cnpj FROM fornecedores WHERE id = %s",
        (id,)
    )
    fornecedor = cursor.fetchone()

    if not fornecedor:
        conn.close()
        abort(404, "Fornecedor não encontrado.")

    if request.method == "POST":
        nome = request.form.get("nome")
        telefone = request.form.get("telefone")
        email = request.form.get("email")
        cpf = request.form.get("cpf")
        cnpj = request.form.get("cnpj")

        if not nome:
            conn.close()
            abort(400, "Nome do fornecedor é obrigatório.")
        
        if telefone:
            try:
                telefone = telefone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            except (ValueError, TypeError):
                abort(400, "Número de telefone inválido, preencha apenas os números")

        if email and ("@" not in email or "." not in email):
            abort(400, "Endereço de e-mail inválido.")

        if cpf and cnpj:
            abort(400, "Informe apenas CPF ou CNPJ.")

        if cpf and not cnpj:
            try:
                cpf = cpf.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            except (ValueError, TypeError):
                abort(400, "Número de documento inválido, preencha apenas os números")

        if cnpj and not cpf:
            try:
                cnpj = cnpj.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            except (ValueError, TypeError):
                abort(400, "Número de documento inválido, preencha apenas os números")

        try:
            cursor.execute(
                """
                UPDATE fornecedores
                SET nome = %s, telefone = %s, email = %s, CPF = %s, CNPJ = %s
                WHERE id = %s
                """,
                (nome, telefone, email, cpf, cnpj, id)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(e)
            abort(500, "Erro ao atualizar fornecedor.")

        conn.close()
        return redirect(url_for("fornecedores.fornecedores"))
    
    conn.close()

    return render_template("fornecedor_editar.html", fornecedor=fornecedor)

@fornecedores_bp.route("/fornecedores/remover/<int:id>", methods=["POST"])
@login_required
def remover_fornecedor(id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM fornecedores WHERE id = %s", (id,))
    fornecedor = cursor.fetchone()

    if not fornecedor:
        conn.close()
        abort(400, "Esse fornecedor não existe, portanto não pode ser excluído.")

    cursor.execute("SELECT id FROM contas_pagar WHERE fornecedor_id = %s", (id,))
    conta_pagar = cursor.fetchone()

    if conta_pagar:
        conn.close()
        abort(400, "Não é possível excluir fornecedor que está vinculado com contas a pagar.")

    cursor.execute("SELECT id FROM contas_receber WHERE fornecedor_id = %s", (id,))
    conta_receber = cursor.fetchone()

    if conta_receber:
        conn.close()
        abort(400, "Não é possível excluir fornecedor que está vinculado com contas a receber.")

    try:
        cursor.execute("DELETE FROM fornecedores WHERE id = %s", (id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        abort(500, "Erro ao remover fornecedor.")

    conn.close()
    return redirect(url_for("fornecedores.fornecedores"))