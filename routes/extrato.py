from flask import (
    Blueprint,
    render_template,
)

from database.connection import get_db
from utils.auth import login_required

extrato_bp = Blueprint('extrato', __name__)

@extrato_bp.route("/extrato")
@login_required
def movimentacoes_bancarias():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            m.data,
            m.tipo,
            m.descricao,
            m.valor,
            m.origem,
            m.origem_id,
            c.nome as conta
        FROM movimentacoes_bancarias m
        JOIN contas_bancarias c ON m.conta_bancaria_id = c.id
        ORDER BY m.data DESC, m.id DESC
    """)
    movimentacoes_bancarias = cursor.fetchall()

    cursor.execute("SELECT SUM(saldo) FROM contas_bancarias")
    resultado = cursor.fetchone()
    saldo_total_contas = resultado[0] if resultado and resultado[0] else 0

    conn.close()

    return render_template("extrato.html", movimentacoes_bancarias=movimentacoes_bancarias, saldo_total_contas=saldo_total_contas)