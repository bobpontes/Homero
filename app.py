from flask import Flask, request, render_template, redirect, url_for, session
from datetime import datetime, date
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_key")

# Data de hoje
today = date.today()

# Login Required:
from utils.auth import login_required

# função para chamar o banco de dados:
from database.connection import get_db


@app.errorhandler(404)
def pagina_nao_encontrada(e):
    return render_template("404.html"), 404

@app.route("/", methods=["GET", "POST"])
@login_required
def home():

    sucesso = request.args.get("sucesso")

    if request.method == "POST":
        nome = request.form.get("nome")
        idade = request.form.get("idade")
        turma = request.form.get("turma")

        if nome and idade and turma:
            inserir_aluno(nome, idade, turma)

        return redirect(url_for("home", sucesso=1))
    
    busca = request.args.get("busca")

    conn = get_db()
    cursor = conn.cursor()

    if busca:
        cursor.execute(
            "SELECT * FROM alunos WHERE nome ILIKE %s",
            (f"%{busca}%", )
        )
    else:
        cursor.execute("SELECT * FROM alunos ORDER BY nome")

    alunos = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM alunos")
    total = cursor.fetchone()[0]

    conn.close()

    return render_template("index.html", alunos=alunos, total=total, sucesso=sucesso, busca=busca)

# Rotas de alunos:
from routes.alunos import alunos_bp
app.register_blueprint(alunos_bp)

# Rotas de autenticação:
from routes.auth import auth_bp
app.register_blueprint(auth_bp)

# Rotas de fornecedores:
from routes.fornecedores import fornecedores_bp 
app.register_blueprint(fornecedores_bp)

# Rotas de mensalidades:
from routes.mensalidades import mensalidades_bp
app.register_blueprint(mensalidades_bp)

# Rotas de plano de contas e categorias:
from routes.plano_contas import plano_contas_bp
app.register_blueprint(plano_contas_bp)

# Rotas de contas a pagar:
from routes.contas_pagar import contas_pagar_bp
app.register_blueprint(contas_pagar_bp)

# Rotas das contas bancárias:
from routes.contas_bancarias import contas_bancarias_bp
app.register_blueprint(contas_bancarias_bp)

# Rotas das contas a receber:
from routes.contas_receber import contas_receber_bp
app.register_blueprint(contas_receber_bp)

# Rotas do extrato bancário:
from routes.extrato import extrato_bp
app.register_blueprint(extrato_bp)

# Rotas do extrato bancário do Banco Inter:
from routes.extrato_bancario import extrato_bancario_bp
app.register_blueprint(extrato_bancario_bp)
    

@app.context_processor
def inject_usuario():
    usuario_nome = None

    if "usuario_id" in session:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT nome FROM usuarios WHERE id = %s", (session["usuario_id"],))
        usuario = cursor.fetchone()

        conn.close()

        if usuario:
            usuario_nome = usuario[0]

    return dict(usuario_nome=usuario_nome)


def backup_banco():
    hoje = datetime.now().strftime("%Y-%m-%d_%H-%M")

    os.makedirs("backup", exist_ok=True)

    destino = f"backup/homero_{hoje}.sql"

    comando = f"pg_dump homero_db > {destino}"

    resultado = os.system(comando)

    if resultado == 0:
        print(f"✅ Backup criado em: {destino}")
    else:
        print("❌ Erro ao criar backup.")

def listar_alunos_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM alunos")
    alunos = cursor.fetchall()

    conn.close()
    return alunos

def inserir_aluno(nome, idade, turma):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO alunos (nome, idade, turma) VALUES (%s, %s, %s)",
        (nome, idade, turma)
    )

    conn.commit()
    conn.close()

# cria um backup automático do banco sempre que o sistema iniciar
# backup_banco()

if __name__ == '__main__':
    app.run(debug=True)
