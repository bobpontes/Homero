import sqlite3
from flask import Flask, request, render_template, redirect, url_for, abort
from datetime import datetime, timedelta

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
        cursor.execute("SELECT * FROM alunos ORDER BY nome")

    alunos = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM alunos")
    total = cursor.fetchone()[0]

    conn.close()

    return render_template("index.html", alunos=alunos, total=total, sucesso=sucesso, busca=busca)

@app.route("/remover/<int:id>", methods=["POST"])
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

@app.route("/financeiro")
def financeiro():
    
    conn = sqlite3.connect("escola.db")
    cursor = conn.cursor()

    cursor.execute('''
        SELECT mensalidades.id,
                alunos.nome,
                mensalidades.valor,
                mensalidades.data_vencimento,
                mensalidades.status
            FROM mensalidades
            JOIN alunos ON mensalidades.aluno_id = alunos.id
            ORDER BY
                CASE WHEN mensalidades.status = 'pendente' THEN 0 ELSE 1 END,
                mensalidades.data_vencimento ASC
        ''')
    
    mensalidades = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM mensalidades WHERE status = 'pendente'")
    pendentes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM mensalidades WHERE status = 'pago'")
    pagos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM mensalidades")
    total = cursor.fetchone()[0]
    conn.close()

    return render_template(
        "financeiro.html",
        mensalidades=mensalidades,
        pendentes=pendentes,
        pagos=pagos,
        total=total
    )

@app.route("/mensalidade/nova", methods=["POST"])
def nova_mensalidade():

    conn = sqlite3.connect("escola.db")
    cursor = conn.cursor()

    aluno_id = request.form.get("aluno_id")
    valor = request.form.get("valor")
    data_vencimento = request.form.get("data_vencimento")
    parcelas = int(request.form.get("parcelas") or 1)
    
    if aluno_id and valor and data_vencimento and parcelas:
        data_base = datetime.strptime(data_vencimento, "%Y-%m-%d")
        valor = float(valor)

        for i in range(parcelas):
            data_parcela = data_base + timedelta(days=30 * i)

            cursor.execute(
                "INSERT INTO mensalidades (aluno_id, valor, data_vencimento) VALUES (?, ?, ?)",
                (aluno_id, valor, data_parcela.strftime("%Y-%m-%d"))
            )
        conn.commit()
        conn.close()
        return redirect(url_for("financeiro"))
    
    conn.close()
    abort(400, "Todos os campos são obrigatórios.")



@app.route("/pagar/<int:id>", methods=["POST"])
def registrar_pagamento(id):

    data_pagamento = request.form.get("data_pagamento")
    metodo_pagamento = request.form.get("metodo_pagamento")

    if not data_pagamento or not metodo_pagamento:
        abort(400, "Data de pagamento e método de pagamento são obrigatórios.")

    conn = sqlite3.connect("escola.db")
    cursor = conn.cursor()

    cursor.execute("""UPDATE mensalidades SET status = 'pago', data_pagamento = ?, metodo_pagamento = ? WHERE id = ?""", 
                   (data_pagamento, metodo_pagamento,id))

    conn.commit()
    conn.close()

    return redirect(url_for("financeiro"))


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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mensalidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER NOT NULL,
            valor REAL,
            data_vencimento TEXT,
            status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','pago')),
            data_pagamento TEXT,
            metodo_pagamento TEXT,
            FOREIGN KEY (aluno_id) REFERENCES alunos(id)
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
