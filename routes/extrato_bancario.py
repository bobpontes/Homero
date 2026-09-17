from flask import (
    Blueprint,
    render_template,
)
from services.banco_inter import BancoInter
from database.connection import get_db
from utils.auth import login_required

extrato_bancario_bp = Blueprint('extrato_bancario', __name__)

@extrato_bancario_bp.route("/extrato_bancario")
@login_required
def movimentacoes_inter():
    inter = BancoInter()

    extrato = inter.consultar_extrato(
        "2026-09-01",
        "2026-09-17"
    )

    for movimentacao in extrato["transacoes"]:
        movimentacao["valor"] = float(movimentacao["valor"])

    return render_template("extrato_bancario.html", extrato=extrato)