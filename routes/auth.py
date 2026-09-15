from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
)

from werkzeug.security import check_password_hash
from database.connection import get_db
from utils.auth import login_required

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").lower().strip()
        senha = request.form.get("senha")

        if not email or not senha:
            return "Email e senha são obrigatórios", 400

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id, senha_hash FROM usuarios WHERE email = %s AND ativo = TRUE", (email, ))
        usuario = cursor.fetchone()

        conn.close()

        if usuario:
            senha_hash = usuario[1]
            if check_password_hash(senha_hash, senha):
                session["usuario_id"] = usuario[0]
                return redirect(url_for("home"))
    
    return render_template("login.html", erro="Email ou senha inválidos")

@auth_bp.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("auth.login"))