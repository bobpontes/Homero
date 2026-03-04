import sqlite3
from flask import Flask, request, render_template, redirect, url_for, abort
import json

app = Flask(__name__)

@app.errorhandler(404)
def pagina_nao_encontrada(e):
    return render_template("404.html"), 404

@app.route("/", methods=["GET", "POST"])
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

    conn = sqlite3.connect("escola.db")
    cursor = conn.cursor()

    if busca:
        cursor.execute(
            "SELECT * FROM alunos WHERE nome LIKE ?",
            (f"%{busca}%", )
        )
    else:
        cursor.execute("SELECT * FROM alunos")

    alunos = cursor.fetchall()
    conn.close()

    total = len(alunos)
    return render_template("index.html", alunos=alunos, total=total, sucesso=sucesso, busca=busca)

@app.route("/remover/<int:id>")
def remover_aluno(id):
    conn = sqlite3.connect('escola.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM alunos WHERE id = ?", (id, ))
    aluno = cursor.fetchone()

    if aluno is None:
        conn.close()
        abort(404)

    cursor.execute("DELETE FROM alunos WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("home"))

@app.route("/editar/<int:id>", methods=["GET", "POST"])
def editar_aluno(id):

    conn = sqlite3.connect('escola.db')
    cursor = conn.cursor()

    # buscar aluno primeiro:
    cursor.execute("SELECT * FROM alunos WHERE id = ?", (id, ))
    aluno = cursor.fetchone()

    if aluno is None:
        conn.close()
        abort(404)

    # se o aluno existir, prossegue:

    if request.method == "POST":
        nome = request.form.get("nome")
        idade = request.form.get("idade")
        turma = request.form.get("turma")

        cursor.execute(
            "UPDATE alunos SET nome = ?, idade = ?, turma = ? WHERE id = ?",
            (nome, idade, turma, id)
        )

        conn.commit()
        conn.close()
        return redirect(url_for("home"))

    conn.close()
    return render_template("editar.html", aluno=aluno)

def criar_banco():
    conn = sqlite3.connect('escola.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alunos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            idade INTEGER NOT NULL,
            turma TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def listar_alunos_db():
    conn = sqlite3.connect('escola.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM alunos")
    alunos = cursor.fetchall()

    conn.close()
    return alunos

def inserir_aluno(nome, idade, turma):
    conn = sqlite3.connect('escola.db')
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO alunos (nome, idade, turma) VALUES (?, ?, ?)",
        (nome, idade, turma)
    )

    conn.commit()
    conn.close()

criar_banco()

if __name__ == '__main__':
    app.run(debug=True)
