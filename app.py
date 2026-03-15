import sqlite3
from flask import Flask, request, render_template, redirect, url_for, abort
from datetime import datetime, timedelta, date
import calendar

app = Flask(__name__)

# função para chamar o banco de dados:
def get_db():
    return sqlite3.connect("escola.db")

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

    conn = get_db()
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
    conn = get_db()
    cursor = conn.cursor()


    cursor.execute("SELECT * FROM alunos WHERE id = ?", (id, ))
    aluno = cursor.fetchone()

    if aluno is None:
        conn.close()
        abort(404)

    # apagar mensalidades associadas a este aluno (antes de apagar o aluno)
    cursor.execute("DELETE FROM mensalidades WHERE aluno_id = ?", (id, ))
    # (após) apagar o aluno do banco
    cursor.execute("DELETE FROM alunos WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("home"))

@app.route("/editar/<int:id>", methods=["GET", "POST"])
def editar_aluno(id):

    conn = get_db()
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
    
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT mensalidades.id,
                alunos.nome,
                mensalidades.valor,
                mensalidades.data_vencimento,
                CASE
                    WHEN mensalidades.status = 'pago' THEN 'Pago'
                    WHEN mensalidades.status = 'pendente'
                        AND date(mensalidades.data_vencimento) < date('now')
                    THEN 'Vencido'
                    ELSE 'Pendente'
                END AS status
            FROM mensalidades
            LEFT JOIN alunos ON mensalidades.aluno_id = alunos.id
            ORDER BY
                CASE 
                    WHEN mensalidades.status = 'pendente'
                        AND date(mensalidades.data_vencimento) < date('now') THEN 0 
                    WHEN mensalidades.status = 'pendente' THEN 1
                    ELSE 2
                END,
                mensalidades.data_vencimento ASC
        ''')
    
    mensalidades = cursor.fetchall()

    mensalidades_com_atraso = []
    for m in mensalidades:
        id, nome, valor, vencimento, status = m

        dias_atraso = 0

        if status == 'Vencido':
            vencimento_data = date.fromisoformat(vencimento)
            dias_atraso = (date.today() - vencimento_data).days
        
        mensalidades_com_atraso.append(
            (id, nome, valor, vencimento, status, dias_atraso)
        )
    
    mensalidades = mensalidades_com_atraso

    cursor.execute("SELECT COUNT(*) FROM mensalidades WHERE status = 'pendente'")
    pendentes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM mensalidades WHERE status = 'pago'")
    pagos = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM mensalidades")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT id, nome FROM alunos ORDER BY nome")
    alunos = cursor.fetchall()

    # Calcula quantas mensalidades pendentes estão vencidas
    cursor.execute("""
    SELECT COUNT(*)
    FROM mensalidades
    WHERE status = 'pendente'
    AND date(data_vencimento) < date('now')
    """)
    vencidas = cursor.fetchone()[0]

    # Calcula qual o valor total vencido e pendente (ou seja, o valor total em aberto)
    cursor.execute("""
    SELECT SUM(valor)
    FROM mensalidades
    WHERE status = 'pendente'
    """)
    resultado = cursor.fetchone()
    total_aberto = resultado[0] or 0.0  # Se for None, retorna 0.0


    conn.close()

    return render_template(
        "financeiro.html",
        mensalidades=mensalidades,
        pendentes=pendentes,
        pagos=pagos,
        total=total,
        alunos=alunos,
        vencidas=vencidas,
        total_aberto=total_aberto
    )

def adicionar_meses(data_base, meses):
    mes = data_base.month -1 + meses
    ano = data_base.year + mes // 12
    mes = mes % 12 + 1
    dia = min(data_base.day, calendar.monthrange(ano, mes)[1])
    return datetime(ano, mes, dia)


@app.route("/mensalidade/nova", methods=["POST"])
def nova_mensalidade():

    conn = get_db()
    cursor = conn.cursor()

    # Checagem se o aluno existe para evitar erros:
    try:
        aluno_id = int(request.form.get("aluno_id"))
    except (TypeError, ValueError):
        abort(400, "Aluno inválido.")

    cursor.execute("SELECT id FROM alunos WHERE id = ?", (aluno_id, ))
    aluno = cursor.fetchone()

    if not aluno:
        conn.close()
        abort(400, "Aluno não encontrado.")

    valor = request.form.get("valor")
    data_vencimento = request.form.get("data_vencimento")
    parcelas = request.form.get("parcelas") 
    try:
        parcelas = int(parcelas) if parcelas else 1 # Se não for informado, assume 1 parcela
    except ValueError:
        abort(400, "Número de parcelas inválido.")
    
    if aluno_id and valor and data_vencimento and parcelas:
        data_base = datetime.strptime(data_vencimento, "%Y-%m-%d")

        try:
            valor = float(valor)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Valor inválido.")

        if valor <= 0:
            conn.close()
            abort(400, "Valor deve ser maior que zero.")

        for i in range(parcelas):
            data_parcela = adicionar_meses(data_base, i)

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

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""UPDATE mensalidades SET status = 'pago', data_pagamento = ?, metodo_pagamento = ? WHERE id = ?""", 
                   (data_pagamento, metodo_pagamento,id))

    conn.commit()
    conn.close()

    return redirect(url_for("financeiro"))

@app.route("/mensalidade/remover/<int:id>", methods=["POST"])
def remover_mensalidade(id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM mensalidades WHERE id = ?", (id, ))
    mensalidade = cursor.fetchone()

    if not mensalidade:
        conn.close()
        abort(404)

    cursor.execute("DELETE FROM mensalidades WHERE id = ?", (id, ))

    conn.commit()
    conn.close()

    return redirect(url_for("financeiro"))


def criar_banco():
    conn = get_db()
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
        "INSERT INTO alunos (nome, idade, turma) VALUES (?, ?, ?)",
        (nome, idade, turma)
    )

    conn.commit()
    conn.close()

criar_banco()

if __name__ == '__main__':
    app.run(debug=True)
