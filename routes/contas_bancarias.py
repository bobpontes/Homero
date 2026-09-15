from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    abort
)
from database.connection import get_db
from utils.auth import login_required

contas_bancarias_bp = Blueprint('contas_bancarias', __name__)

@contas_bancarias_bp.route("/contas_bancarias")
@login_required
def listar_contas_bancarias():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM contas_bancarias ORDER BY saldo DESC")
    contas_banco = cursor.fetchall()

    cursor.execute("SELECT SUM(saldo) FROM contas_bancarias")
    resultado = cursor.fetchone()
    saldo_total_contas = resultado[0] if resultado and resultado[0] else 0

    conn.close()

    return render_template("contas_bancarias.html", contas_banco=contas_banco, saldo_total_contas=saldo_total_contas)

@contas_bancarias_bp.route("/contas_bancarias/nova", methods=["POST"])
@login_required
def nova_conta_bancaria():

    nome = (request.form.get("nome") or '').strip()
    tipo = request.form.get("tipo") or "outro"
    saldo = request.form.get("saldo")
    ativo = True if request.form.get("ativo") else False

    if not nome:
        abort(400, "Nome da conta é obrigatório.")

    try:
        saldo = float(saldo)
    except (TypeError, ValueError):
        abort(400, "Valor inválido para saldo inicial.")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT nome FROM contas_bancarias WHERE nome = %s", (nome, ))
    conta_existente = cursor.fetchone()

    if conta_existente:
        conn.close()
        abort(400, "Esta conta já foi registrada em nosso sistema.")    
    
    cursor.execute(
        "INSERT INTO contas_bancarias (nome, tipo, saldo, ativo) VALUES (%s, %s, %s, %s)",
        (nome, tipo, saldo, ativo)
    )
    
    conn.commit()
    conn.close()

    return redirect(url_for("contas_bancarias.listar_contas_bancarias"))