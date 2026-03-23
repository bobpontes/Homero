import sqlite3
from flask import Flask, request, render_template, redirect, url_for, abort, Response
from datetime import datetime, timedelta, date
import calendar
import shutil
import os
import csv

app = Flask(__name__)

# Data de hoje
today = date.today().strftime("%Y-%m-%d")

# função para chamar o banco de dados:
def get_db():
    conn = sqlite3.connect("escola.db")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

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

@app.route("/exportar/alunos")
def exportar_alunos():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, nome, idade, turma FROM alunos ORDER BY nome")
    alunos = cursor.fetchall()

    conn.close()

    def gerar_csv():
        yield "ID,Nome,Idade,Turma\n"

        for aluno in alunos:
            yield f'"{aluno[0]}","{aluno[1]}","{aluno[2]}","{aluno[3]}"\n'

    return Response(
        gerar_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=alunos.csv"}
    )

@app.route("/financeiro")
def financeiro():
    
    # Filtro para dados
    mes = request.args.get("mes") or None
    ano = request.args.get("ano") or None
    data_inicio = request.args.get("data_inicio") or None
    data_fim = request.args.get("data_fim") or None

    filtro_sql = ""
    parametros = ()

    if data_inicio and data_fim:
        filtro_sql = "WHERE date(mensalidades.data_vencimento) BETWEEN date(?) AND date(?)"
        parametros = (data_inicio, data_fim)
    elif ano:
        filtro_sql = "WHERE strftime('%Y', mensalidades.data_vencimento) = ?"
        parametros = (ano, )
    else:
        if not mes:
            mes = date.today().strftime("%Y-%m")
            
        filtro_sql = "WHERE strftime('%Y-%m', mensalidades.data_vencimento) = ?"
        parametros = (mes, )

    conn = get_db()
    cursor = conn.cursor()

    query = f'''
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
            {filtro_sql}
            ORDER BY
                CASE 
                    WHEN mensalidades.status = 'pendente'
                        AND date(mensalidades.data_vencimento) < date('now') THEN 0 
                    WHEN mensalidades.status = 'pendente' THEN 1
                    ELSE 2
                END,
                mensalidades.data_vencimento ASC
        '''
    
    cursor.execute(query, parametros)
    
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

    cursor.execute("""
    SELECT COUNT(*)
    FROM mensalidades
    WHERE status = 'pendente'
    AND date(data_vencimento) >= date('now')
    """)
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
    total_aberto = resultado[0] if resultado[0] else 0.0  # Se for None, retorna 0.0

    # Calculo de Receita Prevista para Dashboard Financeiro
    cursor.execute("""
    SELECT SUM(valor)
        FROM mensalidades WHERE status = 'pendente' AND strftime('%Y-%m', data_vencimento) = ?
    """, (mes, ))

    resultado = cursor.fetchone()
    receita_prevista = resultado[0] if resultado[0] else 0

    # Calculo de Despesa Prevista para Dashboard Financeiro
    cursor.execute("""
    SELECT SUM(valor)
        FROM contas_pagar WHERE status = 'pendente' AND strftime('%Y-%m', data_vencimento) = ?
    """, (mes, ))

    resultado = cursor.fetchone()
    despesa_prevista = resultado[0] if resultado[0] else 0

    # Saldo Projetado
    saldo_projetado = receita_prevista - despesa_prevista

    conn.close()

    return render_template(
        "financeiro.html",
        mensalidades=mensalidades,
        pendentes=pendentes,
        pagos=pagos,
        total=total,
        alunos=alunos,
        vencidas=vencidas,
        total_aberto=total_aberto,
        receita_prevista=receita_prevista,
        despesa_prevista=despesa_prevista,
        saldo_projetado=saldo_projetado,
        mes=mes
    )

def adicionar_meses(data_base, meses):
    dia_original = data_base.day

    mes = data_base.month -1 + meses
    ano = data_base.year + mes // 12
    mes = mes % 12 + 1
    
    ultimo_dia = calendar.monthrange(ano, mes)[1]

    # mantém o mesmo dia sempre que possível
    dia = dia_original if dia_original <= ultimo_dia else ultimo_dia
    return date(ano, mes, dia)


@app.route("/mensalidade/nova", methods=["POST"])
def nova_mensalidade():

    conn = get_db()
    cursor = conn.cursor()

    # Checagem se o aluno existe para evitar erros:
    try:
        aluno_id = int(request.form.get("aluno_id"))
    except (TypeError, ValueError):
        conn.close()
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

    if valor and data_vencimento and parcelas:
        data_base = datetime.strptime(data_vencimento, "%Y-%m-%d").date()

        try:
            valor = float(valor)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Valor inválido.")

        if valor <= 0:
            conn.close()
            abort(400, "Valor deve ser maior que zero.")

        grupo_parcela_id = int(datetime.now().timestamp()) 

        for i in range(parcelas):
            data_parcela = adicionar_meses(data_base, i)

            cursor.execute(
                "INSERT INTO mensalidades (aluno_id, valor, data_vencimento, grupo_parcela_id) VALUES (?, ?, ?, ?)",
                (aluno_id, valor, data_parcela.strftime("%Y-%m-%d"), grupo_parcela_id)
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
    conta_bancaria_id = request.form.get("conta_bancaria_id")

    if not data_pagamento or not metodo_pagamento or not conta_bancaria_id:
        abort(400, "Todos os campos são obrigatórios.")

    conn = get_db()
    cursor = conn.cursor()

    # Primeiro: verificar se conta bancária existe:
    cursor.execute("SELECT id FROM contas_bancarias WHERE id = ?", (conta_bancaria_id, ))
    conta_bancaria = cursor.fetchone()

    if not conta_bancaria:
        conn.close()
        abort(400, "Uma conta bancária inválida foi selecionada.")

    # Segundo: verificar se a mensalidade existe
    cursor.execute("SELECT id FROM mensalidades WHERE id = ?", (id, ))
    mensalidade = cursor.fetchone()

    if not mensalidade:
        conn.close()
        abort(404)

    # Terceiro: verificar se a mensalidade ainda não foi paga
    cursor.execute("SELECT status FROM mensalidades WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Não é possível registrar o pagamento, a mensalidade já havia sido paga.")
    
    # Antes de atualizar mensalidade, atualizar o saldo bancário:
    cursor.execute("SELECT valor FROM mensalidades WHERE id = ?", (id, ))
    valor = cursor.fetchone()[0]

    cursor.execute("""
        UPDATE contas_bancarias
        SET saldo = saldo + ?
        WHERE id = ?
    """, (valor, conta_bancaria_id))

    # Se existir e não tiver sido paga, registrar pagamento:
    cursor.execute("""UPDATE mensalidades SET status = 'pago', data_pagamento = ?, metodo_pagamento = ?, conta_bancaria_id = ? WHERE id = ?""", 
                   (data_pagamento, metodo_pagamento, conta_bancaria_id, id))
    conn.commit()
    conn.close()

    return redirect(url_for("financeiro"))

@app.route("/mensalidade/remover/<int:id>", methods=["POST"])
def remover_mensalidade(id):
    conn = get_db()
    cursor = conn.cursor()

    # Verificar se mensalidade existe
    cursor.execute("SELECT id FROM mensalidades WHERE id = ?", (id, ))
    mensalidade = cursor.fetchone()

    if not mensalidade:
        conn.close()
        abort(404)

    # Verficar se mensalidade ainda não foi paga
    cursor.execute("SELECT status FROM mensalidades WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Não é possível excluir uma mensalidade que já foi registrada como paga.")

    cursor.execute("DELETE FROM mensalidades WHERE id = ?", (id, ))

    conn.commit()
    conn.close()

    return redirect(url_for("financeiro"))

@app.route("/mensalidade/remover_grupo/<int:grupo_id>", methods = ['POST'])
def remover_grupo_mensalidade(grupo_id):

    conn = get_db()
    cursor = conn.cursor()

    # Verificar se o grupo existe
    cursor.execute("SELECT grupo_parcela_id FROM mensalidades WHERE grupo_parcela_id = ?", (grupo_id, ))
    grupo = cursor.fetchone()

    if not grupo:
        conn.close()
        abort(400, "Este grupo de parcelas não existe, portanto nenhuma mensalidade foi excluída.")

    # Verificar se existe alguma mensalidade paga no grupo
    cursor.execute("""SELECT status FROM mensalidades WHERE grupo_parcela_id = ? AND status = 'pago'""", (grupo_id, ))
    existe_pago = cursor.fetchone()

    if existe_pago:
        conn.close()
        abort(400, "Não é possível excluir um grupo com mensalidades já pagas.")

    cursor.execute("DELETE FROM mensalidades WHERE grupo_parcela_id = ?", (grupo_id, ))

    conn.commit()
    conn.close()

    return redirect(url_for("financeiro"))

@app.route("/conta/nova", methods=["POST"])
def nova_conta():
    
    descricao = request.form.get("descricao")
    valor = request.form.get("valor")
    data_vencimento = request.form.get("data_vencimento")
    plano_conta_id = request.form.get("plano_conta_id")
    fornecedor_id = request.form.get("fornecedor_id")
    parcelas = request.form.get("parcelas")


    try:
        valor = float(valor)
    except (TypeError, ValueError):
        abort(400, "Valor inválido.")

    if valor <= 0:
        abort(400, "Valor deve ser maior que zero.")

    try:
        parcelas = max(1, int(parcelas)) if parcelas else 1
    except ValueError:
        abort(400, "Número de parcelas inválido")

    try:
        plano_conta_id = int(plano_conta_id)
        fornecedor_id = int(fornecedor_id)
    except (TypeError, ValueError):
        abort(400, "Plano de conta ou fornecedor inválido.")

    
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM plano_contas WHERE id = ?", (plano_conta_id, ))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Plano de conta não encontrado.")

    cursor.execute("SELECT id FROM fornecedores WHERE id = ?", (fornecedor_id, ))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Fornecedor não encontrado.")

    if not descricao or not data_vencimento:
        conn.close()
        abort(400, "Descrição e data são obrigatórios.")


    data_base = datetime.strptime(data_vencimento, "%Y-%m-%d").date()
    
    grupo_parcela_id = int(datetime.now().timestamp())

    for i in range(parcelas):
        data_parcela = adicionar_meses(data_base, i)

        cursor.execute(
            "INSERT INTO contas_pagar (descricao, valor, data_vencimento, plano_conta_id, grupo_parcela_id, fornecedor_id) VALUES (?, ?, ?, ?, ?, ?)",
            (descricao, valor, data_parcela.strftime("%Y-%m-%d"), plano_conta_id, grupo_parcela_id, fornecedor_id)
        )

    conn.commit()
    conn.close()

    return redirect(url_for("contas_pagar"))

@app.route("/contas_pagar")
def contas_pagar():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT contas_pagar.id,
            contas_pagar.descricao,
            contas_pagar.valor,
            contas_pagar.data_vencimento,
            CASE
                WHEN contas_pagar.status = 'pago' THEN 'Pago'
                WHEN contas_pagar.status = 'pendente'
                    AND date(contas_pagar.data_vencimento) < date('now')
                THEN 'Vencido'
                ELSE 'Pendente'
            END AS status,
            plano_contas.nome AS plano_conta,
            fornecedores.nome AS fornecedor
        FROM contas_pagar
        LEFT JOIN plano_contas
            ON contas_pagar.plano_conta_id = plano_contas.id
        LEFT JOIN fornecedores
            ON contas_pagar.fornecedor_id = fornecedores.id
        ORDER BY
            CASE
                WHEN contas_pagar.status = 'pendente'
                    AND date(contas_pagar.data_vencimento) < date('now') THEN 0
                WHEN contas_pagar.status = 'pendente' THEN 1
                ELSE 2
            END,
            contas_pagar.data_vencimento ASC
                
""")
    
    contas = cursor.fetchall()

    contas_com_atraso = []
    for c in contas:
        id, descricao, valor, vencimento, status, plano_conta, fornecedor = c

        dias_atraso = 0

        if status == 'Vencido':
            vencimento_data = date.fromisoformat(vencimento)
            dias_atraso = (date.today() - vencimento_data).days
        
        contas_com_atraso.append(
            (id, descricao, valor, vencimento, status, plano_conta, fornecedor, dias_atraso)
        )

    contas = contas_com_atraso

    cursor.execute("SELECT id, nome FROM categorias_plano_contas ORDER BY nome")
    categorias = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM plano_contas ORDER BY nome")
    planos = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM fornecedores ORDER BY nome")
    fornecedores = cursor.fetchall()

    conn.close()

    return render_template("contas_pagar.html", contas=contas, categorias=categorias, planos=planos, fornecedores=fornecedores, today=today)

@app.route("/contas_pagar/pagar/<int:id>", methods=["POST"])
def registrar_conta(id):

    data_pagamento = request.form.get("data_pagamento")
    metodo_pagamento = request.form.get("metodo_pagamento")

    if not data_pagamento or not metodo_pagamento:
        abort(400, "Data de pagamento e método de pagamento são obrigatórios.")

    conn = get_db()
    cursor = conn.cursor()

    # Verificar se conta existe:
    cursor.execute("SELECT id FROM contas_pagar WHERE id = ?", (id, ))
    conta = cursor.fetchone()

    if not conta:
        conn.close()
        abort(404)

    # Verificar se conta já está paga:
    cursor.execute("SELECT status FROM contas_pagar WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Conta já está paga.")

    # Existe a conta, seguir com o pagamento:
    cursor.execute("""UPDATE contas_pagar SET status = 'pago', data_pagamento = ?, metodo_pagamento = ? WHERE id = ?""",
        (data_pagamento, metodo_pagamento, id))
    conn.commit()
    conn.close()

    return redirect(url_for("contas_pagar"))

@app.route("/contas_pagar/remover/<int:id>", methods=["POST"])
def remover_conta(id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM contas_pagar WHERE id = ?", (id, ))
    conta = cursor.fetchone()

    if not conta:
        conn.close()
        abort(400, "Essa conta não existe, portanto não pode ser excluída.")

    cursor.execute("SELECT status FROM contas_pagar WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Não é possível excluir conta já paga.")

    cursor.execute("DELETE FROM contas_pagar WHERE id = ?", (id, ))

    conn.commit()
    conn.close()

    return redirect(url_for("contas_pagar"))

@app.route("/contas_pagar/remover_grupo/<int:grupo_id>", methods=["POST"])
def remover_grupo_conta(grupo_id):

    conn = get_db()
    cursor = conn.cursor()

    # Verificar se existe o grupo
    cursor.execute("SELECT grupo_parcela_id FROM contas_pagar WHERE grupo_parcela_id = ?", (grupo_id, ))
    grupo = cursor.fetchone()

    if not grupo:
        conn.close()
        abort(400, "Este grupo de parcelas não existe, portanto nenhuma conta foi excluída.")

    # Verificar se já existe conta paga no grupo
    cursor.execute("""SELECT status FROM contas_pagar WHERE grupo_parcela_id = ? AND status = 'pago'""", (grupo_id, ))
    existe_pago = cursor.fetchone()

    if existe_pago:
        conn.close()
        abort(400, "Não é possível excluir um grupo com contas já pagas.")

    cursor.execute("DELETE FROM contas_pagar WHERE grupo_parcela_id = ?", (grupo_id, ))

    conn.commit()
    conn.close()

    return redirect(url_for("contas_pagar"))

@app.route("/contas_receber")
def contas_receber():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT contas_receber.id,
            contas_receber.descricao,
            contas_receber.valor,
            contas_receber.data_vencimento,
            CASE
                WHEN contas_receber.status = 'pago' THEN 'Pago'
                WHEN contas_receber.status = 'pendente'
                    AND date(contas_receber.data_vencimento) < date('now')
                THEN 'Vencido'
                ELSE 'Pendente'
            END AS status,
            plano_contas.nome AS plano_conta,
            fornecedores.nome AS fornecedor
        FROM contas_receber
        LEFT JOIN plano_contas
            ON contas_receber.plano_conta_id = plano_contas.id
        LEFT JOIN fornecedores
            ON contas_receber.fornecedor_id = fornecedores.id
        ORDER BY
            CASE
                WHEN contas_receber.status = 'pendente'
                    AND date(contas_receber.data_vencimento) < date('now') THEN 0
                WHEN contas_receber.status = 'pendente' THEN 1
                ELSE 2
            END,
            contas_receber.data_vencimento ASC
                
""")
    
    receitas = cursor.fetchall()

    receitas_com_atraso = []
    for r in receitas:
        id, descricao, valor, vencimento, status, plano_conta, fornecedor = r

        dias_atraso = 0

        if status == 'Vencido':
            vencimento_data = date.fromisoformat(vencimento)
            dias_atraso = (date.today() - vencimento_data).days
        
        receitas_com_atraso.append(
            (id, descricao, valor, vencimento, status, plano_conta, fornecedor, dias_atraso)
        )

    receitas = receitas_com_atraso

    cursor.execute("SELECT id, nome FROM categorias_plano_contas ORDER BY nome")
    categorias = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM plano_contas ORDER BY nome")
    planos = cursor.fetchall()

    conn.close()

    return render_template("contas_receber.html", receitas=receitas, categorias=categorias, planos=planos, today=today)

@app.route("/receita/nova", methods=["POST"])
def nova_receita():
    
    descricao = request.form.get("descricao")
    valor = request.form.get("valor")
    data_vencimento = request.form.get("data_vencimento")
    plano_conta_id = request.form.get("plano_conta_id")
    fornecedor_id = request.form.get("fornecedor_id")
    evento_id = request.form.get("evento_id")
    parcelas = request.form.get("parcelas")


    try:
        valor = float(valor)
    except (TypeError, ValueError):
        abort(400, "Valor inválido.")

    if valor <= 0:
        abort(400, "Valor deve ser maior que zero.")

    try:
        parcelas = max(1, int(parcelas)) if parcelas else 1
    except ValueError:
        abort(400, "Número de parcelas inválido")

    try:
        plano_conta_id = int(plano_conta_id)
        fornecedor_id = int(fornecedor_id)
    except (TypeError, ValueError):
        abort(400, "Plano de conta ou fornecedor inválido.")

    
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM plano_contas WHERE id = ?", (plano_conta_id, ))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Plano de conta não encontrado.")

    cursor.execute("SELECT id FROM fornecedores WHERE id = ?", (fornecedor_id, ))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Fornecedor não encontrado.")

    if evento_id:
        try:
            evento_id = int(evento_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Evento inválido.")

        cursor.execute("SELECT id FROM eventos WHERE id = ?", (evento_id, ))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Evento não encontrado para associar a este recebimento.")
    else:
        evento_id = None

    if not descricao or not data_vencimento:
        conn.close()
        abort(400, "Descrição e data são obrigatórios.")


    data_base = datetime.strptime(data_vencimento, "%Y-%m-%d").date()
    
    grupo_parcela_id = int(datetime.now().timestamp())

    for i in range(parcelas):
        data_parcela = adicionar_meses(data_base, i)

        cursor.execute(
            "INSERT INTO contas_receber (descricao, valor, data_vencimento, plano_conta_id, grupo_parcela_id, fornecedor_id, evento_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (descricao, valor, data_parcela.strftime("%Y-%m-%d"), plano_conta_id, grupo_parcela_id, fornecedor_id, evento_id)
        )

    conn.commit()
    conn.close()

    return redirect(url_for("contas_receber"))

@app.route("/contas_receber/receber/<int:id>", methods=["POST"])
def registrar_receita(id):

    data_pagamento = request.form.get("data_pagamento")
    metodo_pagamento = request.form.get("metodo_pagamento")

    if not data_pagamento or not metodo_pagamento:
        abort(400, "Data de pagamento e método de pagamento são obrigatórios.")

    conn = get_db()
    cursor = conn.cursor()

    # Verificar se conta existe:
    cursor.execute("SELECT id FROM contas_receber WHERE id = ?", (id, ))
    receita = cursor.fetchone()

    if not receita:
        conn.close()
        abort(404)

    # Verificar se conta já está paga:
    cursor.execute("SELECT status FROM contas_receber WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Recebimento já está pago.")

    # Existe a conta, seguir com o pagamento:
    cursor.execute("""UPDATE contas_receber SET status = 'pago', data_pagamento = ?, metodo_pagamento = ? WHERE id = ?""",
        (data_pagamento, metodo_pagamento, id))
    conn.commit()
    conn.close()

    return redirect(url_for("contas_receber"))

@app.route("/contas_receber/remover/<int:id>", methods=["POST"])
def remover_receita(id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM contas_receber WHERE id = ?", (id, ))
    receita = cursor.fetchone()

    if not receita:
        conn.close()
        abort(400, "Esse recebimento não existe, portanto não pode ser excluída.")

    cursor.execute("SELECT status FROM contas_receber WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Não é possível excluir recebimento já pago.")

    cursor.execute("DELETE FROM contas_receber WHERE id = ?", (id, ))

    conn.commit()
    conn.close()

    return redirect(url_for("contas_receber"))

@app.route("/contas_receber/remover_grupo/<int:grupo_id>", methods=["POST"])
def remover_grupo_receita(grupo_id):

    conn = get_db()
    cursor = conn.cursor()

    # Verificar se existe o grupo
    cursor.execute("SELECT grupo_parcela_id FROM contas_receber WHERE grupo_parcela_id = ?", (grupo_id, ))
    grupo = cursor.fetchone()

    if not grupo:
        conn.close()
        abort(400, "Este grupo de parcelas não existe, portanto nenhum recebimento foi excluído.")

    # Verificar se já existe conta paga no grupo
    cursor.execute("""SELECT status FROM contas_receber WHERE grupo_parcela_id = ? AND status = 'pago'""", (grupo_id, ))
    existe_pago = cursor.fetchone()

    if existe_pago:
        conn.close()
        abort(400, "Não é possível excluir um grupo com recebimentos já pagos.")

    cursor.execute("DELETE FROM contas_receber WHERE grupo_parcela_id = ?", (grupo_id, ))

    conn.commit()
    conn.close()

    return redirect(url_for("contas_receber"))

@app.route("/contas_bancarias")
def contas_bancarias():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM contas_bancarias ORDER BY saldo DESC")
    contas_banco = cursor.fetchall()

    cursor.execute("SELECT SUM(saldo) FROM contas_bancarias")
    resultado = cursor.fetchone()
    saldo_total_contas = resultado[0] if resultado and resultado[0] else 0

    conn.close()

    return render_template("contas_bancarias.html", contas_banco=contas_banco, saldo_total_contas=saldo_total_contas)

@app.route("/contas_bancarias/nova", methods=["POST"])
def nova_conta_bancaria():

    nome = request.form.get("nome")
    tipo = request.form.get("tipo") or "outro"
    saldo = request.form.get("saldo")
    ativo = 1 if request.form.get("ativo") else 0

    if not nome:
        abort(400, "Nome da conta é obrigatório.")

    try:
        saldo = float(saldo)
    except (TypeError, ValueError):
        abort(400, "Valor inválido para saldo inicial.")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT nome FROM contas_bancarias WHERE nome = ?", (nome, ))
    conta_existente = cursor.fetchone()

    if conta_existente:
        conn.close()
        abort(400, "Esta conta já foi registrada em nosso sistema.")    
    
    cursor.execute(
        "INSERT INTO contas_bancarias (nome, tipo, saldo, ativo) VALUES (?, ?, ?, ?)",
        (nome, tipo, saldo, ativo)
    )
    
    conn.commit()
    conn.close()

    return redirect(url_for("contas_bancarias"))
    

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
        CREATE TABLE IF NOT EXISTS contas_bancarias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT,
            saldo REAL DEFAULT 0,
            ativo BOOLEAN DEFAULT 1
        )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS categorias_plano_contas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE,
        nome TEXT NOT NULL,
        tipo TEXT CHECK(tipo IN ('receita','despesa','transferencia'))
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS plano_contas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE,
        nome TEXT NOT NULL,
        categoria_id INTEGER,
        FOREIGN KEY (categoria_id) REFERENCES categorias_plano_contas(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            email TEXT,
            CPF TEXT,
            CNPJ TEXT)
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contas_pagar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            data_vencimento TEXT,
            status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','pago')),
            data_pagamento TEXT,
            plano_conta_id INTEGER,
            grupo_parcela_id INTEGER,
            fornecedor_id INTEGER,
            evento_id INTEGER,
            metodo_pagamento TEXT,
            conta_bancaria_id INTEGER,
            FOREIGN KEY (plano_conta_id) REFERENCES plano_contas(id),
            FOREIGN KEY (fornecedor_id) REFERENCES fornecedores(id),
            FOREIGN KEY (evento_id) REFERENCES eventos(id),
            FOREIGN KEY (conta_bancaria_id) REFERENCES contas_bancarias(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contas_receber (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            data_vencimento TEXT,
            status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','pago')),
            data_pagamento TEXT,
            plano_conta_id INTEGER,
            grupo_parcela_id INTEGER,
            fornecedor_id INTEGER,
            evento_id INTEGER,
            metodo_pagamento TEXT,
            conta_bancaria_id INTEGER,
            FOREIGN KEY (plano_conta_id) REFERENCES plano_contas(id),
            FOREIGN KEY (fornecedor_id) REFERENCES fornecedores(id),
            FOREIGN KEY (evento_id) REFERENCES eventos(id),
            FOREIGN KEY (conta_bancaria_id) REFERENCES contas_bancarias(id)
        )
    ''')

    conn.commit()
    conn.close()

def backup_banco():
    hoje = datetime.now().strftime("%Y-%m-%d_%H-%M")
    
    os.makedirs("backup", exist_ok=True)
    
    origem = "escola.db"
    destino = f"backup/escola_{hoje}.db"

    shutil.copy(origem, destino)

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

# cria um backup automático do banco sempre que o sistema iniciar
backup_banco()

if __name__ == '__main__':
    app.run(debug=True)
