import sqlite3
from flask import Flask, request, render_template, redirect, url_for, abort, Response, session
from datetime import datetime, timedelta, date
from werkzeug.security import check_password_hash
from functools import wraps
import calendar
import shutil
import os
import csv

app = Flask(__name__)
app.secret_key = "chave_super_secreta_temporaria"

# Data de hoje
today = date.today().strftime("%Y-%m-%d")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# Adicionar Meses na data inicial de parcelas de mensalidades, contas_pagar e contas_receber:
def adicionar_meses(data_base, meses):
    dia_original = data_base.day

    mes = data_base.month -1 + meses
    ano = data_base.year + mes // 12
    mes = mes % 12 + 1
    
    ultimo_dia = calendar.monthrange(ano, mes)[1]

    # mantém o mesmo dia sempre que possível
    dia = dia_original if dia_original <= ultimo_dia else ultimo_dia
    return date(ano, mes, dia)


# função para chamar o banco de dados:
def get_db():
    conn = sqlite3.connect("escola.db")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# helper para aplicação de filtro no sql:
def aplicar_condicao(filtro_sql, condicao):
    if filtro_sql:
        return filtro_sql + " AND " + condicao
    else:
        return "WHERE " + condicao

# Formatar mês por extenso em pt-BR:
meses = {
    "01": "Janeiro",
    "02": "Fevereiro",
    "03": "Março",
    "04": "Abril",
    "05": "Maio",
    "06": "Junho",
    "07": "Julho",
    "08": "Agosto",
    "09": "Setembro",
    "10": "Outubro",
    "11": "Novembro",
    "12": "Dezembro"
}

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
@login_required
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
@login_required
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
@login_required
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
@login_required
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

    # Contas Bancárias
    cursor.execute("SELECT id, nome FROM contas_bancarias WHERE ativo = 1")
    contas_banco = cursor.fetchall()

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
        contas_banco=contas_banco,
        mes=mes
    )

@app.route("/mensalidade/nova", methods=["POST"])
@login_required
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

# Rotas para atualização de valores: (1 - Mens individual, 2 - tela de grupos de parcelas, 3 - tela de um grupo de parcelas, 4 - edição de parcelas de um grupo em lote)
# 1
@app.route("/mensalidade/atualizar_valor/<int:id>", methods=["POST"])
@login_required
def atualizar_valor_mensalidade(id):
    conn = get_db()
    cursor = conn.cursor()

    novo_valor = request.form.get("novo_valor")

    if not novo_valor:
        conn.close()
        abort(400, "O novo valor é obrigatório.")

    try:
        novo_valor = float(novo_valor)
    except (TypeError, ValueError):
        conn.close()
        abort(400, "Novo valor inválido.")

    if novo_valor <= 0:
        conn.close()
        abort(400, "O novo valor deve ser maior que zero.")

    cursor.execute("""
        SELECT id, aluno_id, status
        FROM mensalidades
        WHERE id = ?
    """, (id,))
    mensalidade = cursor.fetchone()

    if not mensalidade:
        conn.close()
        abort(404)

    _, aluno_id, status = mensalidade

    if status != "pendente":
        conn.close()
        abort(400, "Só é possível editar mensalidades pendentes.")

    cursor.execute("SELECT id FROM alunos WHERE id = ?", (aluno_id,))
    aluno = cursor.fetchone()

    if not aluno:
        conn.close()
        abort(400, "Aluno vinculado à mensalidade não foi encontrado.")

    try:
        cursor.execute("""
            UPDATE mensalidades
            SET valor = ?
            WHERE id = ?
              AND status = 'pendente'
        """, (novo_valor, id))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return redirect(url_for("financeiro"))

# 2
@app.route("/mensalidade/grupos")
@login_required
def listar_grupos_mensalidades():
    
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            m.grupo_parcela_id,
            a.nome,
            COUNT (*) AS total_parcelas,
            SUM(CASE WHEN m.status = 'pago' THEN 1 ELSE 0 END) AS parcelas_pagas,
            SUM(CASE WHEN m.status = 'pendente' THEN 1 ELSE 0 END) AS parcelas_pendentes,
            MIN(m.data_vencimento) AS primeiro_vencimento,
            MAX(m.data_vencimento) AS ultimo_vencimento,
            SUM(CASE WHEN m.status = 'pendente' THEN m.valor ELSE 0 END) AS total_em_aberto
        FROM mensalidades m
        JOIN alunos a ON a.id = m.aluno_id
        WHERE m.grupo_parcela_id IS NOT NULL
        GROUP BY m.grupo_parcela_id, m.aluno_id, a.nome
        HAVING COUNT(*) > 1
        ORDER BY primeiro_vencimento ASC
    """)
    
    grupos = cursor.fetchall()

    conn.close()
    return render_template("mensalidades_grupos.html", grupos=grupos)

# 3
@app.route("/mensalidade/grupo/<int:grupo_id>")
@login_required
def detalhar_grupo_mensalidade(grupo_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            m.id,
            m.aluno_id,
            a.nome,
            m.valor,
            m.data_vencimento,
            m.status,
            m.grupo_parcela_id
        FROM mensalidades m
        JOIN alunos a ON a.id = m.aluno_id
        WHERE m.grupo_parcela_id = ?
        ORDER BY m.data_vencimento ASC, m.id ASC
    """, (grupo_id,))
    parcelas = cursor.fetchall()

    if not parcelas:
        conn.close()
        abort(404)

    aluno_ids = {p[1] for p in parcelas}
    if len(aluno_ids) != 1:
        conn.close()
        abort(400, "Grupo de parcelas inconsistente.")

    primeira_pendente = None

    for p in parcelas:
        if p[5] == "pendente":
            primeira_pendente = p[4]
            break

    parcelas_pendentes = []
    parcelas_pagas = []

    for p in parcelas:
        if p[5] == "pendente":
            parcelas_pendentes.append(p)
        else:
            parcelas_pagas.append(p)

    conn.close()
    return render_template(
        "mensalidade_grupo.html",
        grupo_id=grupo_id,
        parcelas=parcelas,
        aluno_nome=parcelas[0][2],
        primeira_pendente=primeira_pendente,
        parcelas_pendentes=parcelas_pendentes,
        parcelas_pagas=parcelas_pagas
    )

# 3
@app.route("/mensalidade/grupo/<int:grupo_id>/atualizar_valor", methods=["POST"])
@login_required
def atualizar_grupo_mensalidade(grupo_id):
    conn = get_db()
    cursor = conn.cursor()

    novo_valor = request.form.get("novo_valor")
    data_inicial = request.form.get("data_vencimento_inicial")

    if not novo_valor or not data_inicial:
        conn.close()
        abort(400, "Todos os campos são obrigatórios.")

    cursor.execute("""
        SELECT COUNT(DISTINCT aluno_id)
        FROM mensalidades
        WHERE grupo_parcela_id = ?
    """, (grupo_id, ))

    if cursor.fetchone()[0] != 1:
        conn.close()
        abort(400, "Grupo inconsistente: contém mensalidades de mais de um aluno.")

    try:
        novo_valor = float(novo_valor)
    except (TypeError, ValueError):
        conn.close()
        abort(400, "Novo valor inválido.")

    if novo_valor <= 0:
        conn.close()
        abort(400, "O novo valor deve ser maior que zero.")

    try:
        datetime.strptime(data_inicial, "%Y-%m-%d")
    except ValueError:
        conn.close()
        abort(400, "Data de vencimento inválida.")

    cursor.execute("SELECT id FROM mensalidades WHERE grupo_parcela_id = ?", (grupo_id,))
    if not cursor.fetchone():
        conn.close()
        abort(404)

    # Buscar a primeira data de parcela pendente no banco:
    cursor.execute("""
        SELECT MIN(data_vencimento)
        FROM mensalidades
        WHERE grupo_parcela_id = ?
        AND status = 'pendente'
    """, (grupo_id,))
    resultado = cursor.fetchone()
    primeira_pendente = resultado[0] if resultado and resultado[0] else None

    # transformar data de string para data:
    data_inicial_date = datetime.strptime(data_inicial, "%Y-%m-%d").date()
    if primeira_pendente:
        primeira_pendente_date = datetime.strptime(primeira_pendente, "%Y-%m-%d").date()

        if primeira_pendente and data_inicial_date < primeira_pendente_date:
            data_inicial = primeira_pendente

    cursor.execute("""
        SELECT COUNT(*)
        FROM mensalidades
        WHERE grupo_parcela_id = ?
          AND status = 'pendente'
          AND date(data_vencimento) >= date(?)
    """, (grupo_id, data_inicial))
    total_editaveis = cursor.fetchone()[0]

    if total_editaveis == 0:
        conn.close()
        abort(400, "Não existem parcelas pendentes para atualizar a partir desta data.")

    try:
        cursor.execute("""
            UPDATE mensalidades
            SET valor = ?
            WHERE grupo_parcela_id = ?
              AND status = 'pendente'
              AND date(data_vencimento) >= date(?)
        """, (novo_valor, grupo_id, data_inicial))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return redirect(url_for("detalhar_grupo_mensalidade", grupo_id=grupo_id))

# Edição individual de parcelas no grupo
@app.route("/mensalidade/grupo/<int:grupo_id>/parcela/<int:id>/atualizar_valor", methods=["POST"])
@login_required
def atualizar_valor_mensalidade_no_grupo(grupo_id, id):

    conn = get_db()
    cursor = conn.cursor()

    novo_valor = request.form.get("novo_valor")

    if not novo_valor:
        conn.close()
        abort(400, "O novo valor é obrigatório.")

    try:
        novo_valor = float(novo_valor)
    except (TypeError, ValueError):
        conn.close()
        abort(400, "Novo valor inválido.")

    if novo_valor <= 0:
        conn.close()
        abort(400, "O novo valor deve ser maior que zero.")

    cursor.execute("""
        SELECT id, aluno_id, status, grupo_parcela_id
        FROM mensalidades
        WHERE id=?
    """, (id, ))
    mensalidade = cursor.fetchone()

    if not mensalidade:
        conn.close()
        abort(404)

    _, aluno_id, status, grupo_parcela_id = mensalidade

    if grupo_parcela_id != grupo_id:
        conn.close()
        abort(400, "Esta parcela não pertence ao grupo informado.")

    if status != 'pendente':
        conn.close()
        abort(400, "Só é possível editar mensalidades pendentes.")

    cursor.execute("SELECT id FROM alunos WHERE id=?", (aluno_id, ))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Aluno vinculado à mensalidade não foi encontrado.")

    try:
        cursor.execute("""
            UPDATE mensalidades
            SET valor = ?
            WHERE id = ?
                AND grupo_parcela_id = ?
                AND status = 'pendente'
        """, (novo_valor, id, grupo_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return (redirect(url_for("detalhar_grupo_mensalidade", grupo_id=grupo_id)))

@app.route("/pagar/<int:id>", methods=["POST"])
@login_required
def registrar_pagamento(id):

    data_pagamento = request.form.get("data_pagamento")
    metodo_pagamento = request.form.get("metodo_pagamento")
    conta_bancaria_id = request.form.get("conta_bancaria_id")
    valor_pago = request.form.get("valor_pago")

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
    
    # 4) Segurança: conferir o valor da mensalidade:
    cursor.execute("SELECT valor FROM mensalidades WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if not resultado:
        conn.close()
        abort(404)

    valor_original = resultado[0]

    if valor_pago is not None and valor_pago != "":
        try:
            valor = float(valor_pago)
        except ValueError:
            conn.close()
            abort(400, "Valor pago inválido.")
    else:
        valor = valor_original

    if valor <= 0:
        conn.close()
        abort(400, "Valor deve ser maior que zero.")

    try:
        # 5) Registrar o pagamento da conta:
        cursor.execute("""UPDATE mensalidades SET status = 'pago', data_pagamento = ?, metodo_pagamento = ?, conta_bancaria_id = ? WHERE id = ?""", 
            (data_pagamento, metodo_pagamento, conta_bancaria_id, id))

        # 6) Atualizar tabela movimentacoes_bancarias:
        cursor.execute("""
            SELECT alunos.nome
            FROM mensalidades
            JOIN alunos ON mensalidades.aluno_id = alunos.id
            WHERE mensalidades.id = ?
        """, (id, ))
        resultado_nome = cursor.fetchone()

        if not resultado_nome:
            conn.rollback()
            abort(500, "Erro ao obter nome do aluno.")

        nome_aluno = resultado_nome[0]

        cursor.execute("""
            INSERT INTO movimentacoes_bancarias
                       (conta_bancaria_id, tipo, valor, data, origem, origem_id, descricao)
                       VALUES (?, 'entrada', ?, ?, 'mensalidade', ?, ?)
        """, (
            conta_bancaria_id,
            valor,
            data_pagamento,
            id,
            f"Mensalidade - {nome_aluno} - (ID {id})"
        ))

        # 7) Atualizar saldo da conta bancária:
        cursor.execute("""
            UPDATE contas_bancarias
            SET saldo = saldo + ?
            WHERE id = ?
        """, (valor, conta_bancaria_id))
        
        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        raise
    
    conn.close()

    return redirect(url_for("financeiro"))

@app.route("/mensalidade/estornar/<int:id>", methods=["POST"])
@login_required
def estornar_mensalidade(id):

    # 0) Data da movimentação:
    data_hoje = date.today().strftime("%Y-%m-%d")

    conn = get_db()
    cursor = conn.cursor()

    # 1) Verifica se existe
    cursor.execute("SELECT status, valor, conta_bancaria_id FROM mensalidades WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if not resultado:
        conn.close()
        abort(404)

    status, valor, conta_bancaria_id = resultado

    # 2) Segurança: Verifica se está pago
    if status != 'pago':
        conn.close()
        abort(400, "Só é possível estornar mensalidades pagas.")

    # 3) Segurança: verifica se tem conta bancária:
    if not conta_bancaria_id:
        conn.close()
        abort(400, "Mensalidade não possui conta bancária vinculada.")

    # 4) Buscar nome do aluno
    cursor.execute("""
        SELECT alunos.nome
        FROM mensalidades
        JOIN alunos ON mensalidades.aluno_id = alunos.id
        WHERE mensalidades.id = ?
    """, (id, ))
    resultado_nome = cursor.fetchone()

    if not resultado_nome:
        conn.close()
        abort(500, "Erro ao obter nome do aluno.")

    nome_aluno = resultado_nome[0]

    try:
        # 5) Voltar status para pendente
        cursor.execute("""
            UPDATE mensalidades
            SET status = 'pendente',
                data_pagamento = NULL,
                metodo_pagamento = NULL,
                conta_bancaria_id = NULL
            WHERE id = ?
        """, (id, ))

        # 6) Registrar a movimentação do Estorno
        cursor.execute("""
            INSERT INTO movimentacoes_bancarias
            (conta_bancaria_id, tipo, valor, data, origem, origem_id, descricao)
            VALUES (?, 'estorno', ?, ?, 'mensalidade', ?, ?)
        """, (
            conta_bancaria_id,
            valor,
            data_hoje,
            id,
            f"Estorno - {nome_aluno} - Parcela ID {id}"
        ))

        # 7) Reverter Saldo (entrada vira saída)
        cursor.execute("""
            UPDATE contas_bancarias
            SET saldo = saldo - ?
            WHERE id = ?
        """, (valor, conta_bancaria_id))

        conn.commit()
    
    except Exception as e:
        conn.rollback()
        print(e)
        raise

    conn.close()

    return redirect(url_for("financeiro"))

@app.route("/mensalidade/remover/<int:id>", methods=["POST"])
@login_required
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
@login_required
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
@login_required
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
@login_required
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
            fornecedores.nome AS fornecedor,
            contas_pagar.plano_conta_id,
            contas_pagar.fornecedor_id
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
        id, descricao, valor, vencimento, status, plano_conta, fornecedor, plano_conta_id, forncedor_id = c

        dias_atraso = 0

        if status == 'Vencido':
            vencimento_data = date.fromisoformat(vencimento)
            dias_atraso = (date.today() - vencimento_data).days
        
        contas_com_atraso.append(
            (id, descricao, valor, vencimento, status, plano_conta, fornecedor, dias_atraso, plano_conta_id, forncedor_id)
        )

    contas = contas_com_atraso

    cursor.execute("SELECT id, nome FROM categorias_plano_contas ORDER BY nome")
    categorias = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM plano_contas ORDER BY nome")
    planos = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM fornecedores ORDER BY nome")
    fornecedores = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM contas_bancarias WHERE ativo = 1 ORDER BY nome")
    contas_banco = cursor.fetchall()

    conn.close()

    return render_template("contas_pagar.html", contas=contas, categorias=categorias, planos=planos, fornecedores=fornecedores, today=today, contas_banco=contas_banco)

# Atualização Individual
@app.route("/contas_pagar/atualizar/<int:id>", methods=["POST"])
@login_required
def atualizar_conta_pagar(id):
    conn = get_db()
    cursor = conn.cursor()

    descricao = request.form.get("descricao")
    valor = request.form.get("valor")
    data_vencimento = request.form.get("data_vencimento")
    plano_conta_id = request.form.get("plano_conta_id")
    fornecedor_id = request.form.get("fornecedor_id")

    if not descricao or not valor or not data_vencimento or not plano_conta_id or not fornecedor_id:
        conn.close()
        abort(400, "Todos os campos são obrigatórios.")

    try:
        valor = float(valor)
    except (TypeError, ValueError):
        conn.close()
        abort(400, "Valor inválido.")

    if valor <= 0:
        conn.close()
        abort(400, "Valor deve ser maior que zero.")

    try:
        datetime.strptime(data_vencimento, "%Y-%m-%d")
    except ValueError:
        conn.close()
        abort(400, "Data de vencimento inválida.")

    try:
        plano_conta_id = int(plano_conta_id)
        fornecedor_id = int(fornecedor_id)
    except (TypeError, ValueError):
        conn.close()
        abort(400, "Plano de conta ou fornecedor inválido.")

    cursor.execute("SELECT status FROM contas_pagar WHERE id = ?", (id,))
    conta = cursor.fetchone()

    if not conta:
        conn.close()
        abort(404)

    if conta[0] != "pendente":
        conn.close()
        abort(400, "Só é possível editar contas pendentes.")

    cursor.execute("SELECT id FROM plano_contas WHERE id = ?", (plano_conta_id,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Plano de conta não encontrado.")

    cursor.execute("SELECT id FROM fornecedores WHERE id = ?", (fornecedor_id,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Fornecedor não encontrado.")

    try:
        cursor.execute("""
            UPDATE contas_pagar
            SET descricao = ?,
                valor = ?,
                data_vencimento = ?,
                plano_conta_id = ?,
                fornecedor_id = ?
            WHERE id = ?
              AND status = 'pendente'
        """, (descricao, valor, data_vencimento, plano_conta_id, fornecedor_id, id))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return redirect(url_for("contas_pagar"))

# Atualização em lote: Listar grupos de parcelas
@app.route("/contas_pagar/grupos")
@login_required
def listar_grupos_contas_pagar():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            cp.grupo_parcela_id,

            CASE
                WHEN COUNT(DISTINCT cp.descricao) > 1 THEN MIN(cp.descricao) || ' (e outras)'
                ELSE MIN(cp.descricao)
            END AS descricao,

            CASE
                WHEN COUNT(DISTINCT pc.nome) > 1 THEN MIN(pc.nome) || ' (e outros)'
                ELSE MIN(pc.nome)
            END AS plano_conta,

            CASE
                WHEN COUNT(DISTINCT f.nome) > 1 THEN MIN(f.nome) || ' (e outros)'
                ELSE MIN(f.nome)
            END AS fornecedor,

            COUNT(*) AS total_parcelas,
            SUM(CASE WHEN cp.status = 'pago' THEN 1 ELSE 0 END) AS parcelas_pagas,
            SUM(CASE WHEN cp.status = 'pendente' THEN 1 ELSE 0 END) AS parcelas_pendentes,
            MIN(cp.data_vencimento) AS primeiro_vencimento,
            MAX(cp.data_vencimento) AS ultimo_vencimento,
            SUM(CASE WHEN cp.status = 'pendente' THEN cp.valor ELSE 0 END) AS total_em_aberto
        FROM contas_pagar cp
        LEFT JOIN plano_contas pc ON cp.plano_conta_id = pc.id
        LEFT JOIN fornecedores f ON cp.fornecedor_id = f.id
        WHERE cp.grupo_parcela_id IS NOT NULL
        GROUP BY cp.grupo_parcela_id
        HAVING COUNT(*) > 1
        ORDER BY primeiro_vencimento ASC
    """)


    grupos = cursor.fetchall()
    conn.close()

    return render_template("contas_pagar_grupos.html", grupos=grupos)

# Atualização em lote: Detalhar um grupo de parcelas
@app.route("/contas_pagar/grupo/<int:grupo_id>")
@login_required
def detalhar_grupo_conta_pagar(grupo_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            cp.id,
            cp.descricao,
            cp.valor,
            cp.data_vencimento,
            cp.status,
            cp.plano_conta_id,
            cp.fornecedor_id,
            pc.nome AS plano_conta,
            f.nome AS fornecedor,
            cp.grupo_parcela_id
        FROM contas_pagar cp
        LEFT JOIN plano_contas pc ON cp.plano_conta_id = pc.id
        LEFT JOIN fornecedores f ON cp.fornecedor_id = f.id
        WHERE cp.grupo_parcela_id = ?
        ORDER BY cp.data_vencimento ASC, cp.id ASC
    """, (grupo_id,))
    parcelas = cursor.fetchall()

    if not parcelas:
        conn.close()
        abort(404)

    primeira_pendente = None
    for p in parcelas:
        if p[4] == "pendente":
            primeira_pendente = p[3]
            break

    parcelas_pendentes = [p for p in parcelas if p[4] == "pendente"]
    parcelas_pagas = [p for p in parcelas if p[4] == "pago"]

    cursor.execute("SELECT id, nome FROM plano_contas ORDER BY nome")
    planos = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM fornecedores ORDER BY nome")
    fornecedores = cursor.fetchall()

    conn.close()
    return render_template(
        "conta_pagar_grupo.html",
        grupo_id=grupo_id,
        parcelas=parcelas,
        primeira_pendente=primeira_pendente,
        parcelas_pendentes=parcelas_pendentes,
        parcelas_pagas=parcelas_pagas,
        descricao_grupo=parcelas[0][1],
        plano_conta_nome=parcelas[0][7],
        fornecedor_nome=parcelas[0][8],
        planos=planos,
        fornecedores=fornecedores
    )

# Atualização em lote: atualizar várias parcelas de um grupo
@app.route("/contas_pagar/grupo/<int:grupo_id>/atualizar_valor", methods=["POST"])
@login_required
def atualizar_grupo_conta_pagar(grupo_id):
    conn = get_db()
    cursor = conn.cursor()

    data_inicial = request.form.get("data_vencimento_inicial")
    nova_descricao = (request.form.get("nova_descricao") or "").strip()
    novo_valor = request.form.get("novo_valor")
    novo_plano_conta_id = request.form.get("novo_plano_conta_id")
    novo_fornecedor_id = request.form.get("novo_fornecedor_id")

    if not data_inicial:
        conn.close()
        abort(400, "A data inicial é obrigatória.")

    try:
        datetime.strptime(data_inicial, "%Y-%m-%d")
    except ValueError:
        conn.close()
        abort(400, "Data de vencimento inválida.")

    if not nova_descricao and not novo_valor and not novo_plano_conta_id and not novo_fornecedor_id:
        conn.close()
        abort(400, "Informe pelo menos um campo para atualizar.")

    novo_valor_float = None
    if novo_valor:
        try:
            novo_valor_float = float(novo_valor)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Novo valor inválido.")

        if novo_valor_float <= 0:
            conn.close()
            abort(400, "O novo valor deve ser maior que zero.")

    novo_plano_conta_id_int = None
    if novo_plano_conta_id:
        try:
            novo_plano_conta_id_int = int(novo_plano_conta_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Plano de conta inválido.")

        cursor.execute("SELECT id FROM plano_contas WHERE id = ?", (novo_plano_conta_id_int,))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Plano de conta não encontrado.")

    novo_fornecedor_id_int = None
    if novo_fornecedor_id:
        try:
            novo_fornecedor_id_int = int(novo_fornecedor_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Fornecedor inválido.")

        cursor.execute("SELECT id FROM fornecedores WHERE id = ?", (novo_fornecedor_id_int,))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Fornecedor não encontrado.")

    cursor.execute("SELECT id FROM contas_pagar WHERE grupo_parcela_id = ?", (grupo_id,))
    if not cursor.fetchone():
        conn.close()
        abort(404)

    cursor.execute("""
        SELECT COUNT(*)
        FROM contas_pagar
        WHERE grupo_parcela_id = ?
          AND status = 'pendente'
          AND date(data_vencimento) >= date(?)
    """, (grupo_id, data_inicial))
    total_editaveis = cursor.fetchone()[0]

    if total_editaveis == 0:
        conn.close()
        abort(400, "Não existem contas pendentes para atualizar a partir desta data.")

    try:
        cursor.execute("""
            UPDATE contas_pagar
            SET descricao = COALESCE(?, descricao),
                valor = COALESCE(?, valor),
                plano_conta_id = COALESCE(?, plano_conta_id),
                fornecedor_id = COALESCE(?, fornecedor_id)
            WHERE grupo_parcela_id = ?
              AND status = 'pendente'
              AND date(data_vencimento) >= date(?)
        """, (
            nova_descricao or None,
            novo_valor_float,
            novo_plano_conta_id_int,
            novo_fornecedor_id_int,
            grupo_id,
            data_inicial
        ))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return redirect(url_for("detalhar_grupo_conta_pagar", grupo_id=grupo_id))

# Atualizar uma parcela do grupo:
@app.route("/contas_pagar/grupo/<int:grupo_id>/parcela/<int:id>/atualizar", methods=["POST"])
@login_required
def atualizar_conta_pagar_no_grupo(grupo_id, id):
    conn = get_db()
    cursor = conn.cursor()

    descricao = (request.form.get("descricao") or "").strip()
    valor = request.form.get("valor")
    data_vencimento = request.form.get("data_vencimento")
    plano_conta_id = request.form.get("plano_conta_id")
    fornecedor_id = request.form.get("fornecedor_id")

    if not descricao or not valor or not data_vencimento or not plano_conta_id or not fornecedor_id:
        conn.close()
        abort(400, "Todos os campos são obrigatórios.")

    valor_float = None
    if valor:
        try:
            valor_float = float(valor)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Valor inválido.")
        if valor_float <= 0:
            conn.close()
            abort(400, "Valor deve ser maior que zero.")

    if data_vencimento:
        try:
            datetime.strptime(data_vencimento, "%Y-%m-%d")
        except ValueError:
            conn.close()
            abort(400, "Data de vencimento inválida.")

    plano_conta_id_int = None
    if plano_conta_id:
        try:
            plano_conta_id_int = int(plano_conta_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Plano de conta inválido.")

        cursor.execute("SELECT id FROM plano_contas WHERE id = ?", (plano_conta_id_int,))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Plano de conta não encontrado.")

    fornecedor_id_int = None
    if fornecedor_id:
        try:
            fornecedor_id_int = int(fornecedor_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Fornecedor inválido.")

        cursor.execute("SELECT id FROM fornecedores WHERE id = ?", (fornecedor_id_int,))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Fornecedor não encontrado.")

    cursor.execute("""
        SELECT id, status, grupo_parcela_id
        FROM contas_pagar
        WHERE id = ?
    """, (id,))
    conta = cursor.fetchone()

    if not conta:
        conn.close()
        abort(404)

    _, status, grupo_parcela_id = conta

    if grupo_parcela_id != grupo_id:
        conn.close()
        abort(400, "Esta conta não pertence ao grupo informado.")

    if status != "pendente":
        conn.close()
        abort(400, "Só é possível editar contas pendentes.")

    try:
        cursor.execute("""
            UPDATE contas_pagar
            SET descricao = ?,
                valor = ?,
                data_vencimento = ?,
                plano_conta_id = ?,
                fornecedor_id = ?
            WHERE id = ?
            AND grupo_parcela_id = ?
            AND status = 'pendente'
        """, (descricao, valor_float, data_vencimento, plano_conta_id_int, fornecedor_id_int, id, grupo_id))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return redirect(url_for("detalhar_grupo_conta_pagar", grupo_id=grupo_id))

@app.route("/contas_pagar/pagar/<int:id>", methods=["POST"])
@login_required
def registrar_conta(id):

    data_pagamento = request.form.get("data_pagamento")
    metodo_pagamento = request.form.get("metodo_pagamento")
    conta_bancaria_id = request.form.get("conta_bancaria_id")
    valor_pago = request.form.get("valor_pago")
    nova_descricao = request.form.get("descricao")

    if not data_pagamento or not metodo_pagamento or not conta_bancaria_id:
        abort(400, "Todos os dados são obrigatórios.")

    conn = get_db()
    cursor = conn.cursor()

    # 1) Verifica se a conta bancária existe:
    cursor.execute("SELECT id FROM contas_bancarias WHERE id = ?", (conta_bancaria_id, ))
    conta_bancaria = cursor.fetchone()

    if not conta_bancaria:
        conn.close()
        abort(400, "Conta bancária inválida, pagamento não registrado.")

    # 2) Verificar se conta existe:
    cursor.execute("SELECT id FROM contas_pagar WHERE id = ?", (id, ))
    conta = cursor.fetchone()

    if not conta:
        conn.close()
        abort(404)

    # 3) Verificar se conta já está paga:
    cursor.execute("SELECT status FROM contas_pagar WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Conta já está paga.")

    # 4) Segurança: conferir valor da conta para pagar:
    cursor.execute("SELECT descricao, valor FROM contas_pagar WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if not resultado:
        conn.close()
        abort(404)

    descricao, valor_original = resultado

    if valor_pago is not None and valor_pago != "":
        try:
            valor = float(valor_pago)
        except ValueError:
            conn.close()
            abort(400, "Valor pago inválido.")
    else:
        valor = valor_original

    if valor <= 0:
        conn.close()
        abort(400, "Valor deve ser maior que zero.")

    if nova_descricao and nova_descricao.strip():
        nova_descricao = nova_descricao.strip()
    else:
        nova_descricao = descricao

    try:
        # 5) Registrar o pagamento da conta:
        cursor.execute("""
            UPDATE contas_pagar
                       SET status = 'pago',
                       data_pagamento = ?,
                       metodo_pagamento = ?,
                       conta_bancaria_id = ?,
                       descricao = ?
                       WHERE id = ?""",
            (data_pagamento, metodo_pagamento, conta_bancaria_id, nova_descricao, id)
        )

        # 6) Atualizar tabela movimentacoes_bancarias:
        cursor.execute("""
            INSERT INTO movimentacoes_bancarias
                (conta_bancaria_id, tipo, valor, data, origem, origem_id, descricao)
                VALUES (?, 'saida', ?, ?, 'contas_pagar', ?, ?)
        """, (
            conta_bancaria_id,
            valor,
            data_pagamento,
            id,
            f"Pagamento - {nova_descricao} (ID {id})"
        ))

        # 7) Atualizar saldo da conta bancária:
        cursor.execute("""
            UPDATE contas_bancarias
            SET saldo = saldo - ?
            WHERE id = ?
        """, (valor, conta_bancaria_id))

        conn.commit()
    
    except Exception as e:
        conn.rollback()
        print(e)
        raise
    
    conn.close()

    return redirect(url_for("contas_pagar"))

@app.route("/contas_pagar/estornar/<int:id>", methods=["POST"])
@login_required
def estornar_contas_pagar(id):

    # 0) Data da movimentação:
    data_hoje = date.today().strftime("%Y-%m-%d")

    conn = get_db()
    cursor = conn.cursor()

    # 1) Verifica se existe
    cursor.execute("SELECT descricao, status, valor, conta_bancaria_id FROM contas_pagar WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if not resultado:
        conn.close()
        abort(404)

    descricao, status, valor, conta_bancaria_id = resultado

    # 2) Segurança: Verifica se está pago
    if status != 'pago':
        conn.close()
        abort(400, "Só é possível estornar contas pagas.")

    # 3) Segurança: verifica se tem conta bancária:
    if not conta_bancaria_id:
        conn.close()
        abort(400, "Conta não possui conta bancária vinculada.")

    try:
        # 4) Voltar status para pendente
        cursor.execute("""
            UPDATE contas_pagar
            SET status = 'pendente',
                data_pagamento = NULL,
                metodo_pagamento = NULL,
                conta_bancaria_id = NULL
            WHERE id = ?
        """, (id, ))

        # 5) Registrar a movimentação do Estorno
        cursor.execute("""
            INSERT INTO movimentacoes_bancarias
            (conta_bancaria_id, tipo, valor, data, origem, origem_id, descricao)
            VALUES (?, 'estorno', ?, ?, 'contas_pagar', ?, ?)
        """, (
            conta_bancaria_id,
            valor,
            data_hoje,
            id,
            f"Estorno - {descricao} (ID {id})"
        ))

        # 6) Reverter Saldo (entrada vira saída)
        cursor.execute("""
            UPDATE contas_bancarias
            SET saldo = saldo + ?
            WHERE id = ?
        """, (valor, conta_bancaria_id))

        conn.commit()
    
    except Exception as e:
        conn.rollback()
        print(e)
        raise

    conn.close()

    return redirect(url_for("contas_pagar"))

@app.route("/contas_pagar/remover/<int:id>", methods=["POST"])
@login_required
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
@login_required
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
@login_required
def contas_receber():

    # Filtro para dados
    mes = request.args.get("mes") or None
    ano = request.args.get("ano") or None
    data_inicio = request.args.get("data_inicio") or None
    data_fim = request.args.get("data_fim") or None

    filtro_sql = ""
    parametros = ()

    if data_inicio and data_fim:
        filtro_sql = "WHERE date(contas_receber.data_vencimento) BETWEEN date(?) AND date(?)"
        parametros = (data_inicio, data_fim)
        
        mes1 = meses[data_inicio[5:7]]
        mes2 = meses[data_fim[5:7]]

        periodo_formatado = (
            f"{data_inicio[8:10]} {mes1[:3]} {data_inicio[0:4]} "
            f"até {data_fim[8:10]} {mes2[:3]} {data_fim[0:4]}"
        )

    elif ano:
        filtro_sql = "WHERE strftime('%Y', contas_receber.data_vencimento) = ?"
        parametros = (ano, )
        periodo_formatado = f"Ano de {ano}"

    else:
        if not mes:
            mes = date.today().strftime("%Y-%m")
            
        filtro_sql = "WHERE strftime('%Y-%m', contas_receber.data_vencimento) = ?"
        parametros = (mes, )
        periodo_formatado = f"{meses[mes[5:7]]}/{mes[0:4]}"

    conn = get_db()
    cursor = conn.cursor()

    query = f"""
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
            fornecedores.nome AS fornecedor,
            contas_receber.plano_conta_id,
            contas_receber.fornecedor_id
        FROM contas_receber
        LEFT JOIN plano_contas
            ON contas_receber.plano_conta_id = plano_contas.id
        LEFT JOIN fornecedores
            ON contas_receber.fornecedor_id = fornecedores.id
        {filtro_sql}
        ORDER BY
            CASE
                WHEN contas_receber.status = 'pendente'
                    AND date(contas_receber.data_vencimento) < date('now') THEN 0
                WHEN contas_receber.status = 'pendente' THEN 1
                ELSE 2
            END,
            contas_receber.data_vencimento ASC
                
    """
    cursor.execute(query, parametros)
    
    receitas = cursor.fetchall()

    receitas_com_atraso = []
    for r in receitas:
        id, descricao, valor, vencimento, status, plano_conta, fornecedor, plano_conta_id, fornecedor_id = r

        dias_atraso = 0

        if status == 'Vencido':
            vencimento_data = date.fromisoformat(vencimento)
            dias_atraso = (date.today() - vencimento_data).days
        
        receitas_com_atraso.append(
            (id, descricao, valor, vencimento, status, plano_conta, fornecedor, dias_atraso, plano_conta_id, fornecedor_id)
        )

    receitas = receitas_com_atraso

    # Preparação dos filtros para queries agregadas:
    filtro_receber = filtro_sql
    filtro_mensalidades = filtro_sql.replace("contas_receber", "mensalidades")
    filtro_pagar = filtro_sql.replace("contas_receber", "contas_pagar")

    filtro_receber_status = aplicar_condicao(filtro_receber, "status = 'pendente'")
    filtro_receber_vencidas = aplicar_condicao(filtro_receber, "status = 'pendente' AND date(data_vencimento) < date('now')")
    filtro_receber_pago = aplicar_condicao(filtro_receber, "status = 'pago'")

    # Gráfico do Dashboard
    # Receitas e Mensalidades
    cursor.execute(f"""
    SELECT SUM(valor)
    FROM contas_receber
    {filtro_receber}
    """, parametros)
    resultado_c_receber = cursor.fetchone()
    total_contas_receber = resultado_c_receber[0] if resultado_c_receber and resultado_c_receber[0] else 0.0
    total_receitas = total_contas_receber

    cursor.execute(f"""
    SELECT SUM(valor)
    FROM mensalidades
    {filtro_mensalidades}
    """, parametros)
    resultado_mensalidades = cursor.fetchone()
    total_contas_mensalidades = resultado_mensalidades[0] if resultado_mensalidades and resultado_mensalidades[0] else 0.0
    total_mensalidades = total_contas_mensalidades

    receita_total = total_receitas + total_mensalidades

    # Despesas
    cursor.execute(f"""
    SELECT SUM(valor)
    FROM contas_pagar
    {filtro_pagar}
    """, parametros)
    resultado_c_pagar = cursor.fetchone()
    total_despesas = resultado_c_pagar[0] if resultado_c_pagar and resultado_c_pagar[0] else 0.0

    despesa_total = total_despesas

    # Soldo Projetado
    saldo_total = receita_total - despesa_total

    # Índices do Dashboard (de acordo com o filtro solicitado)
    # Contas a receber pendentes que estão vencidas
    cursor.execute(f"""
    SELECT COUNT(*)
    FROM contas_receber
    {filtro_receber_vencidas}
    """, parametros)
    resultado_qtdd_vencidas = cursor.fetchone()
    total_vencidas = resultado_qtdd_vencidas[0] if resultado_qtdd_vencidas and resultado_qtdd_vencidas[0] else 0
    parcelas_vencidas = total_vencidas

    # Contas a receber pendentes (ainda não vencidas)
    cursor.execute(f"""
    SELECT COUNT(*)
    FROM contas_receber
    {filtro_receber_status}
    """, parametros)
    resultado_qtdd_pendentes = cursor.fetchone()
    total_pendentes = resultado_qtdd_pendentes[0] if resultado_qtdd_pendentes and resultado_qtdd_pendentes[0] else 0
    parcelas_pendentes = total_pendentes - total_vencidas

    # Contas a receber pagas
    cursor.execute(f"""
    SELECT COUNT(*)
    FROM contas_receber
    {filtro_receber_pago}
    """, parametros)
    resultado_qtdd_pagas = cursor.fetchone()
    total_pagas = resultado_qtdd_pagas[0] if resultado_qtdd_pagas and resultado_qtdd_pagas[0] else 0
    parcelas_pagas = total_pagas

    # Retorna o valor total vencido e pendente (Valor total em aberto)
    cursor.execute(f"""
    SELECT SUM(valor)
    FROM contas_receber
    {filtro_receber_status}
    """, parametros)
    resultado_receitas_pendente = cursor.fetchone()
    total_receitas_pendentes = resultado_receitas_pendente[0] if resultado_receitas_pendente and resultado_receitas_pendente[0] else 0.0 # Se for None, retorna 0.0
    total_aberto = total_receitas_pendentes
        

    cursor.execute("SELECT id, nome FROM categorias_plano_contas ORDER BY nome")
    categorias = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM plano_contas ORDER BY nome")
    planos = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM fornecedores ORDER BY nome")
    fornecedores = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM contas_bancarias WHERE ativo = 1 ORDER BY nome")
    contas_banco = cursor.fetchall()

    conn.close()

    return render_template("contas_receber.html",
        mes=mes,
        periodo_formatado=periodo_formatado,
        receitas=receitas,
        receita_total=receita_total,
        despesa_total=despesa_total,
        saldo_total=saldo_total,
        parcelas_vencidas=parcelas_vencidas,
        parcelas_pendentes=parcelas_pendentes,
        parcelas_pagas=parcelas_pagas,
        total_aberto=total_aberto,
        categorias=categorias,
        planos=planos,
        today=today,
        fornecedores=fornecedores,
        contas_banco=contas_banco
    )

@app.route("/contas_receber/nova", methods=["POST"])
@login_required
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

@app.route("/contas_receber/atualizar/<int:id>", methods=["POST"])
@login_required
def atualizar_conta_receber(id):
    conn = get_db()
    cursor = conn.cursor()

    descricao = (request.form.get("descricao") or "").strip()
    valor = request.form.get("valor")
    data_vencimento = request.form.get("data_vencimento")
    plano_conta_id = request.form.get("plano_conta_id")
    fornecedor_id = request.form.get("fornecedor_id")
    evento_id = request.form.get("evento_id")

    if not descricao or not valor or not data_vencimento or not plano_conta_id or not fornecedor_id:
        conn.close()
        abort(400, "Todos os campos são obrigatórios.")

    try:
        valor = float(valor)
    except (TypeError, ValueError):
        conn.close()
        abort(400, "Valor inválido.")

    if valor <= 0:
        conn.close()
        abort(400, "Valor deve ser maior que zero.")

    try:
        datetime.strptime(data_vencimento, "%Y-%m-%d")
    except ValueError:
        conn.close()
        abort(400, "Data de vencimento inválida.")

    try:
        plano_conta_id = int(plano_conta_id)
        fornecedor_id = int(fornecedor_id)
    except (TypeError, ValueError):
        conn.close()
        abort(400, "Plano de conta ou fornecedor inválido.")

    if evento_id:
        try:
            evento_id = int(evento_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Evento inválido.")

        cursor.execute("SELECT id FROM eventos WHERE id = ?", (evento_id, ))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Evento não encontrado.")
        
    else:
        evento_id = None

    cursor.execute("SELECT status FROM contas_receber WHERE id = ?", (id,))
    conta = cursor.fetchone()

    if not conta:
        conn.close()
        abort(404)

    status = conta[0]

    if status != "pendente":
        conn.close()
        abort(400, "Só é possível editar contas pendentes.")

    cursor.execute("SELECT id FROM plano_contas WHERE id = ?", (plano_conta_id,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Plano de conta não encontrado.")

    cursor.execute("SELECT id FROM fornecedores WHERE id = ?", (fornecedor_id,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Fornecedor não encontrado.")

    try:
        cursor.execute("""
            UPDATE contas_receber
            SET descricao = ?,
                valor = ?,
                data_vencimento = ?,
                plano_conta_id = ?,
                fornecedor_id = ?,
                evento_id = ?
            WHERE id = ?
              AND status = 'pendente'
        """, (descricao, valor, data_vencimento, plano_conta_id, fornecedor_id, evento_id, id))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return redirect(url_for("contas_receber"))

# Listar grupos de parcelas a receber:
@app.route("/contas_receber/grupos")
@login_required
def listar_grupos_contas_receber():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            cr.grupo_parcela_id,

            CASE
                WHEN COUNT(DISTINCT cr.descricao) > 1 THEN MIN(cr.descricao) || ' (e outras)'
                ELSE MIN(cr.descricao)
            END AS descricao,

            CASE
                WHEN COUNT(DISTINCT pc.nome) > 1 THEN MIN(pc.nome) || ' (e outros)'
                ELSE MIN(pc.nome)
            END AS plano_conta,

            CASE
                WHEN COUNT(DISTINCT f.nome) > 1 THEN MIN(f.nome) || ' (e outros)'
                ELSE MIN(f.nome)
            END AS cliente,

            COUNT(*) AS total_parcelas,
            SUM(CASE WHEN cr.status = 'pago' THEN 1 ELSE 0 END) AS parcelas_pagas,
            SUM(CASE WHEN cr.status = 'pendente' THEN 1 ELSE 0 END) AS parcelas_pendentes,
            MIN(cr.data_vencimento) AS primeiro_vencimento,
            MAX(cr.data_vencimento) AS ultimo_vencimento,
            SUM(CASE WHEN cr.status = 'pendente' THEN cr.valor ELSE 0 END) AS total_em_aberto
        FROM contas_receber cr
        LEFT JOIN plano_contas pc ON cr.plano_conta_id = pc.id
        LEFT JOIN fornecedores f ON cr.fornecedor_id = f.id
        WHERE cr.grupo_parcela_id IS NOT NULL
        GROUP BY cr.grupo_parcela_id
        HAVING COUNT(*) > 1
        ORDER BY primeiro_vencimento ASC
    """)


    grupos = cursor.fetchall()
    conn.close()

    return render_template("contas_receber_grupos.html", grupos=grupos)

# Detalhar um grupo de parcelas:
@app.route("/contas_receber/grupo/<int:grupo_id>")
@login_required
def detalhar_grupo_conta_receber(grupo_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            cr.id,
            cr.descricao,
            cr.valor,
            cr.data_vencimento,
            cr.status,
            cr.plano_conta_id,
            cr.fornecedor_id,
            pc.nome AS plano_conta,
            f.nome AS cliente,
            cr.grupo_parcela_id
        FROM contas_receber cr
        LEFT JOIN plano_contas pc ON cr.plano_conta_id = pc.id
        LEFT JOIN fornecedores f ON cr.fornecedor_id = f.id
        WHERE cr.grupo_parcela_id = ?
        ORDER BY cr.data_vencimento ASC, cr.id ASC
    """, (grupo_id,))
    parcelas = cursor.fetchall()

    if not parcelas:
        conn.close()
        abort(404)

    primeira_pendente = None
    for p in parcelas:
        if p[4] == "pendente":
            primeira_pendente = p[3]
            break

    parcelas_pendentes = [p for p in parcelas if p[4] == "pendente"]
    parcelas_pagas = [p for p in parcelas if p[4] == "pago"]

    cursor.execute("SELECT id, nome FROM plano_contas ORDER BY nome")
    planos = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM fornecedores ORDER BY nome")
    fornecedores = cursor.fetchall()

    conn.close()
    return render_template(
        "conta_receber_grupo.html",
        grupo_id=grupo_id,
        parcelas=parcelas,
        primeira_pendente=primeira_pendente,
        parcelas_pendentes=parcelas_pendentes,
        parcelas_pagas=parcelas_pagas,
        descricao_grupo=parcelas[0][1],
        plano_conta_nome=parcelas[0][7],
        cliente_nome=parcelas[0][8],
        planos=planos,
        fornecedores=fornecedores
    )

# Atualizar um grupo de parcelas em lote:
@app.route("/contas_receber/grupo/<int:grupo_id>/atualizar_valor", methods=["POST"])
@login_required
def atualizar_grupo_conta_receber(grupo_id):
    conn = get_db()
    cursor = conn.cursor()

    data_inicial = request.form.get("data_vencimento_inicial")
    nova_descricao = (request.form.get("nova_descricao") or "").strip()
    novo_valor = request.form.get("novo_valor")
    novo_plano_conta_id = request.form.get("novo_plano_conta_id")
    novo_fornecedor_id = request.form.get("novo_fornecedor_id")

    if not data_inicial:
        conn.close()
        abort(400, "A data inicial é obrigatória.")

    try:
        datetime.strptime(data_inicial, "%Y-%m-%d")
    except ValueError:
        conn.close()
        abort(400, "Data de vencimento inválida.")

    if not nova_descricao and not novo_valor and not novo_plano_conta_id and not novo_fornecedor_id:
        conn.close()
        abort(400, "Informe pelo menos um campo para atualizar.")

    novo_valor_float = None
    if novo_valor:
        try:
            novo_valor_float = float(novo_valor)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Novo valor inválido.")

        if novo_valor_float <= 0:
            conn.close()
            abort(400, "O novo valor deve ser maior que zero.")

    novo_plano_conta_id_int = None
    if novo_plano_conta_id:
        try:
            novo_plano_conta_id_int = int(novo_plano_conta_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Plano de conta inválido.")

        cursor.execute("SELECT id FROM plano_contas WHERE id = ?", (novo_plano_conta_id_int,))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Plano de conta não encontrado.")

    novo_fornecedor_id_int = None
    if novo_fornecedor_id:
        try:
            novo_fornecedor_id_int = int(novo_fornecedor_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Cliente inválido.")

        cursor.execute("SELECT id FROM fornecedores WHERE id = ?", (novo_fornecedor_id_int,))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Cliente não encontrado.")

    cursor.execute("SELECT id FROM contas_receber WHERE grupo_parcela_id = ?", (grupo_id,))
    if not cursor.fetchone():
        conn.close()
        abort(404)

    cursor.execute("""
        SELECT COUNT(*)
        FROM contas_receber
        WHERE grupo_parcela_id = ?
          AND status = 'pendente'
          AND date(data_vencimento) >= date(?)
    """, (grupo_id, data_inicial))
    total_editaveis = cursor.fetchone()[0]

    if total_editaveis == 0:
        conn.close()
        abort(400, "Não existem recebimentos pendentes para atualizar a partir desta data.")

    try:
        cursor.execute("""
            UPDATE contas_receber
            SET descricao = COALESCE(?, descricao),
                valor = COALESCE(?, valor),
                plano_conta_id = COALESCE(?, plano_conta_id),
                fornecedor_id = COALESCE(?, fornecedor_id)
            WHERE grupo_parcela_id = ?
              AND status = 'pendente'
              AND date(data_vencimento) >= date(?)
        """, (
            nova_descricao or None,
            novo_valor_float,
            novo_plano_conta_id_int,
            novo_fornecedor_id_int,
            grupo_id,
            data_inicial
        ))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return redirect(url_for("detalhar_grupo_conta_receber", grupo_id=grupo_id))

# Atualizar uma parcela individual dentro de um grupo:
@app.route("/contas_receber/grupo/<int:grupo_id>/parcela/<int:id>/atualizar", methods=["POST"])
@login_required
def atualizar_conta_receber_no_grupo(grupo_id, id):
    conn = get_db()
    cursor = conn.cursor()

    descricao = (request.form.get("descricao") or "").strip()
    valor = request.form.get("valor")
    data_vencimento = request.form.get("data_vencimento")
    plano_conta_id = request.form.get("plano_conta_id")
    fornecedor_id = request.form.get("fornecedor_id")

    if not descricao or not valor or not data_vencimento or not plano_conta_id or not fornecedor_id:
        conn.close()
        abort(400, "Todos os campos são obrigatórios.")

    try:
        valor_float = float(valor)
    except (TypeError, ValueError):
        conn.close()
        abort(400, "Valor inválido.")

    if valor_float <= 0:
        conn.close()
        abort(400, "Valor deve ser maior que zero.")

    try:
        datetime.strptime(data_vencimento, "%Y-%m-%d")
    except ValueError:
        conn.close()
        abort(400, "Data de vencimento inválida.")

    try:
        plano_conta_id_int = int(plano_conta_id)
        fornecedor_id_int = int(fornecedor_id)
    except (TypeError, ValueError):
        conn.close()
        abort(400, "Plano de conta ou cliente inválido.")

    cursor.execute("SELECT id FROM plano_contas WHERE id = ?", (plano_conta_id_int,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Plano de conta não encontrado.")

    cursor.execute("SELECT id FROM fornecedores WHERE id = ?", (fornecedor_id_int,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Cliente não encontrado.")

    cursor.execute("""
        SELECT id, status, grupo_parcela_id
        FROM contas_receber
        WHERE id = ?
    """, (id,))
    conta = cursor.fetchone()

    if not conta:
        conn.close()
        abort(404)

    _, status, grupo_parcela_id = conta

    if grupo_parcela_id != grupo_id:
        conn.close()
        abort(400, "Este recebimento não pertence ao grupo informado.")

    if status != "pendente":
        conn.close()
        abort(400, "Só é possível editar recebimentos pendentes.")

    try:
        cursor.execute("""
            UPDATE contas_receber
            SET descricao = ?,
                valor = ?,
                data_vencimento = ?,
                plano_conta_id = ?,
                fornecedor_id = ?
            WHERE id = ?
              AND grupo_parcela_id = ?
              AND status = 'pendente'
        """, (descricao, valor_float, data_vencimento, plano_conta_id_int, fornecedor_id_int, id, grupo_id))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return redirect(url_for("detalhar_grupo_conta_receber", grupo_id=grupo_id))

@app.route("/contas_receber/receber/<int:id>", methods=["POST"])
@login_required
def registrar_receita(id):

    data_pagamento = request.form.get("data_pagamento")
    metodo_pagamento = request.form.get("metodo_pagamento")
    conta_bancaria_id = request.form.get("conta_bancaria_id")
    valor_pago = request.form.get("valor_pago")

    if not data_pagamento or not metodo_pagamento or not conta_bancaria_id:
        abort(400, "Todos os dados são obrigatórios.")

    conn = get_db()
    cursor = conn.cursor()

    # 1) Verifica conta bancária:
    cursor.execute("SELECT id FROM contas_bancarias WHERE id = ?", (conta_bancaria_id, ))
    conta_bancaria = cursor.fetchone()

    if not conta_bancaria:
        conn.close()
        abort(400, "Conta bancária inválida.")

    # 2) Verificar se conta existe:
    cursor.execute("SELECT id FROM contas_receber WHERE id = ?", (id, ))
    receita = cursor.fetchone()

    if not receita:
        conn.close()
        abort(404)

    # 3) Verificar se conta já está paga:
    cursor.execute("SELECT status FROM contas_receber WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Recebimento já está pago.")

    # 4) Segurança: conferir descrição e valor da conta para recebimento:
    cursor.execute("SELECT descricao, valor FROM contas_receber WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if not resultado:
        conn.close()
        abort(404)

    descricao, valor_original = resultado

    if valor_pago is not None and valor_pago != "":
        try:
            valor = float(valor_pago)
        except ValueError:
            conn.close()
            abort(400, "Valor pago inválido.")
    else:
        valor = valor_original

    if valor <= 0:
        conn.close()
        abort(400, "Valor deve ser maior que zero.")

    try:
        # 5) Existe a conta, seguir com o pagamento:
        cursor.execute("""UPDATE contas_receber SET status = 'pago', data_pagamento = ?, metodo_pagamento = ?, conta_bancaria_id = ? WHERE id = ?""",
            (data_pagamento, metodo_pagamento, conta_bancaria_id, id))

        # 6) Atualizar tabela movimentacoes_bancarias:
        cursor.execute("""
            INSERT INTO movimentacoes_bancarias
                    (conta_bancaria_id, tipo, valor, data, origem, origem_id, descricao)
                    VALUES (?, 'entrada', ?, ?, 'contas_receber', ?, ?)
        """, (
            conta_bancaria_id,
            valor,
            data_pagamento,
            id,
            f"Recebimento - {descricao} (ID {id})"
        ))

        # 7) Atualizar saldo da conta bancária:
        cursor.execute("""
            UPDATE contas_bancarias
            SET saldo = saldo + ?
            WHERE id = ?
        """, (valor, conta_bancaria_id))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        raise

    conn.close()

    return redirect(url_for("contas_receber"))

@app.route("/contas_receber/estornar/<int:id>", methods=["POST"])
@login_required
def estornar_contas_receber(id):

    # 0) Data da movimentação:
    data_hoje = date.today().strftime("%Y-%m-%d")

    conn = get_db()
    cursor = conn.cursor()

    # 1) Verifica se existe
    cursor.execute("SELECT descricao, status, valor, conta_bancaria_id FROM contas_receber WHERE id = ?", (id, ))
    resultado = cursor.fetchone()

    if not resultado:
        conn.close()
        abort(404)

    descricao, status, valor, conta_bancaria_id = resultado

    # 2) Segurança: Verifica se está pago
    if status != 'pago':
        conn.close()
        abort(400, "Só é possível estornar contas pagas.")

    # 3) Segurança: verifica se tem conta bancária:
    if not conta_bancaria_id:
        conn.close()
        abort(400, "Conta não possui conta bancária vinculada.")

    try:
        # 4) Voltar status para pendente
        cursor.execute("""
            UPDATE contas_receber
            SET status = 'pendente',
                data_pagamento = NULL,
                metodo_pagamento = NULL,
                conta_bancaria_id = NULL
            WHERE id = ?
        """, (id, ))

        # 5) Registrar a movimentação do Estorno
        cursor.execute("""
            INSERT INTO movimentacoes_bancarias
            (conta_bancaria_id, tipo, valor, data, origem, origem_id, descricao)
            VALUES (?, 'estorno', ?, ?, 'contas_receber', ?, ?)
        """, (
            conta_bancaria_id,
            valor,
            data_hoje,
            id,
            f"Estorno - {descricao} (ID {id})"
        ))

        # 6) Reverter Saldo (entrada vira saída)
        cursor.execute("""
            UPDATE contas_bancarias
            SET saldo = saldo - ?
            WHERE id = ?
        """, (valor, conta_bancaria_id))

        conn.commit()
    
    except Exception as e:
        conn.rollback()
        print(e)
        raise

    conn.close()

    return redirect(url_for("contas_receber"))

@app.route("/contas_receber/remover/<int:id>", methods=["POST"])
@login_required
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
@login_required
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
@login_required
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
@login_required
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

@app.route("/extrato")
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
    
@app.route("/fornecedores")
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

@app.route("/fornecedores/novo", methods=["POST"])
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

    cursor.execute("SELECT nome FROM fornecedores WHERE nome = ?", (nome, ))
    nome_existente = cursor.fetchone()

    if nome_existente:
        conn.close()
        abort(400, "Este fornecedor já foi registrado em nosso sistema.") 

    try:
        cursor.execute(
            "INSERT INTO fornecedores (nome, telefone, email, CPF, CNPJ) VALUES (?, ?, ?, ?, ?)",
            (nome, telefone, email, cpf, cnpj)
        )

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        abort(500, "Erro ao criar fornecedor.")

    conn.close()

    return redirect(url_for("fornecedores"))

@app.route("/fornecedores/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_fornecedor(id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, nome, telefone, email, cpf, cnpj FROM fornecedores WHERE id = ?",
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
                SET nome = ?, telefone = ?, email = ?, CPF = ?, CNPJ = ?
                WHERE id = ?
                """,
                (nome, telefone, email, cpf, cnpj, id)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(e)
            abort(500, "Erro ao atualizar fornecedor.")

        conn.close()
        return redirect(url_for("fornecedores"))
    
    conn.close()

    return render_template("fornecedor_editar.html", fornecedor=fornecedor)

@app.route("/fornecedores/remover/<int:id>", methods=["POST"])
@login_required
def remover_fornecedor(id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM fornecedores WHERE id = ?", (id,))
    fornecedor = cursor.fetchone()

    if not fornecedor:
        conn.close()
        abort(400, "Esse fornecedor não existe, portanto não pode ser excluído.")

    cursor.execute("SELECT id FROM contas_pagar WHERE fornecedor_id = ?", (id,))
    conta_pagar = cursor.fetchone()

    if conta_pagar:
        conn.close()
        abort(400, "Não é possível excluir fornecedor que está vinculado com contas a pagar.")

    cursor.execute("SELECT id FROM contas_receber WHERE fornecedor_id = ?", (id,))
    conta_receber = cursor.fetchone()

    if conta_receber:
        conn.close()
        abort(400, "Não é possível excluir fornecedor que está vinculado com contas a receber.")

    try:
        cursor.execute("DELETE FROM fornecedores WHERE id = ?", (id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        abort(500, "Erro ao remover fornecedor.")

    conn.close()
    return redirect(url_for("fornecedores"))

@app.route("/plano_contas")
@login_required
def plano_contas():

    categoria_editar_id = request.args.get("categoria_editar")
    plano_editar_id = request.args.get("plano_editar")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, codigo, nome, tipo
        FROM categorias_plano_contas
        ORDER BY codigo
    """)
    categorias = cursor.fetchall()

    cursor.execute("""
        SELECT id, codigo, nome, categoria_id
        FROM plano_contas
        ORDER BY codigo
    """)
    planos = cursor.fetchall()

    categoria_em_edicao = None
    if categoria_editar_id:

        try:
            categoria_editar_id = int(categoria_editar_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Categoria inválida.")
        
        cursor.execute("""
            SELECT id, codigo, nome, tipo
            FROM categorias_plano_contas
            WHERE id = ?
        """, (categoria_editar_id, ))
        categoria_em_edicao = cursor.fetchone()
    
    plano_em_edicao = None
    if plano_editar_id:
        try:
            plano_editar_id = int(plano_editar_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Plano de contas inválido.")
        
        cursor.execute("""
            SELECT id, codigo, nome, categoria_id
            FROM plano_contas
            WHERE id = ?
        """, (plano_editar_id, ))

        plano_em_edicao = cursor.fetchone()


    conn.close()

    return render_template(
        "plano_contas.html",
        categorias=categorias,
        planos=planos,
        categoria_em_edicao=categoria_em_edicao,
        plano_em_edicao=plano_em_edicao
    )

@app.route("/plano_contas/categoria/nova", methods=["POST"])
@login_required
def nova_categoria_plano_conta():

    codigo = (request.form.get("codigo") or "").strip()
    nome = (request.form.get("nome") or "").strip()
    tipo = (request.form.get("tipo") or "").strip()

    if not codigo or not nome or not tipo:
        abort(400, "Todos os campos são obrigatórios.")

    TIPOS_VALIDOS = ("receita", "despesa", "transferencia")

    if tipo not in TIPOS_VALIDOS:
        abort(400, "Tipo inválido.")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM categorias_plano_contas WHERE codigo = ?", (codigo,))
    if cursor.fetchone():
        conn.close()
        abort(400, "Já existe uma categoria com este código.")

    try:
        cursor.execute("""
            INSERT INTO categorias_plano_contas (codigo, nome, tipo)
            VALUES (?, ?, ?)
        """, (codigo, nome, tipo))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        abort(500, "Erro ao criar categoria.")

    conn.close()

    return redirect(url_for("plano_contas"))


# Novo endpoint para criar plano de contas
@app.route("/plano_contas/novo", methods=["POST"])
@login_required
def novo_plano_conta():

    codigo = (request.form.get("codigo") or "").strip()
    nome = (request.form.get("nome") or "").strip()
    categoria_id = request.form.get("categoria_id")

    if not codigo or not nome or not categoria_id:
        abort(400, "Todos os campos são obrigatórios.")

    try:
        categoria_id = int(categoria_id)
    except (TypeError, ValueError):
        abort(400, "Categoria inválida.")

    conn = get_db()
    cursor = conn.cursor()

    # Verifica se a categoria existe
    cursor.execute("SELECT id FROM categorias_plano_contas WHERE id = ?", (categoria_id,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Categoria não encontrada.")

    # Código único
    cursor.execute("SELECT id FROM plano_contas WHERE codigo = ?", (codigo,))
    if cursor.fetchone():
        conn.close()
        abort(400, "Já existe um plano de contas com este código.")

    try:
        cursor.execute("""
            INSERT INTO plano_contas (codigo, nome, categoria_id)
            VALUES (?, ?, ?)
        """, (codigo, nome, categoria_id))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        abort(500, "Erro ao criar plano de contas.")

    conn.close()

    return redirect(url_for("plano_contas"))

# EDITAR CATEGORIA
@app.route("/plano_contas/categoria/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_categoria_plano_conta(id):

    if request.method == "GET":

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id, codigo, nome, tipo FROM categorias_plano_contas WHERE id = ?", (id, ))
        categoria = cursor.fetchone()

        if not categoria:
            conn.close()
            abort(404, "Categoria não encontrada.")
        
        conn.close()
        return redirect(url_for("plano_contas", categoria_editar=id))

    if request.method == "POST":

        codigo = (request.form.get("codigo") or "").strip()
        nome = (request.form.get("nome") or "").strip()
        tipo = (request.form.get("tipo") or "").strip()

        if not codigo or not nome or not tipo:
            abort(400, "Todos os campos são obrigatórios.")

        TIPOS_VALIDOS = ("receita", "despesa", "transferencia")

        if tipo not in TIPOS_VALIDOS:
            abort(400, "Tipo inválido.")

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM categorias_plano_contas WHERE id = ?", (id,))
        if not cursor.fetchone():
            conn.close()
            abort(404, "Categoria não encontrada.")

        cursor.execute("SELECT id FROM categorias_plano_contas WHERE codigo = ? AND id != ?", (codigo, id))
        if cursor.fetchone():
            conn.close()
            abort(400, "Já existe outra categoria com este código.")

        try:
            cursor.execute("""
                UPDATE categorias_plano_contas
                SET codigo = ?, nome = ?, tipo = ?
                WHERE id = ?
            """, (codigo, nome, tipo, id))

            conn.commit()

        except Exception as e:
            conn.rollback()
            print(e)
            abort(500, "Erro ao atualizar categoria.")

        conn.close()

    return redirect(url_for("plano_contas"))

# REMOVER CATEGORIA
@app.route("/plano_contas/categoria/remover/<int:id>", methods=["POST"])
@login_required
def remover_categoria_plano_conta(id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM categorias_plano_contas WHERE id = ?", (id,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Categoria não existe.")

    # Segurança: não permitir se houver planos vinculados
    cursor.execute("SELECT id FROM plano_contas WHERE categoria_id = ? LIMIT 1", (id,))
    if cursor.fetchone():
        conn.close()
        abort(400, "Categoria possui planos vinculados.")

    try:
        cursor.execute("DELETE FROM categorias_plano_contas WHERE id = ?", (id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        abort(500, "Erro ao remover categoria.")

    conn.close()

    return redirect(url_for("plano_contas"))

# EDITAR PLANO
@app.route("/plano_contas/plano/editar/<int:id>", methods=["GET","POST"])
@login_required
def editar_plano_conta(id):

    if request.method == "GET":

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, codigo, nome, categoria_id
            FROM plano_contas
            WHERE id = ?
        """, (id, ))
        plano = cursor.fetchone()

        if not plano:
            conn.close()
            abort(404, "Plano não encontrado.")
        
        conn.close()
        return redirect(url_for("plano_contas", plano_editar=id))        
        
    if request.method == "POST":

        codigo = (request.form.get("codigo") or "").strip()
        nome = (request.form.get("nome") or "").strip()
        categoria_id = request.form.get("categoria_id")

        if not codigo or not nome or not categoria_id:
            abort(400, "Todos os campos são obrigatórios.")

        try:
            categoria_id = int(categoria_id)
        except (TypeError, ValueError):
            abort(400, "Categoria inválida.")

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM plano_contas WHERE id = ?", (id,))
        if not cursor.fetchone():
            conn.close()
            abort(404, "Plano não encontrado.")

        cursor.execute("SELECT id FROM categorias_plano_contas WHERE id = ?", (categoria_id,))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Categoria não encontrada.")

        cursor.execute("SELECT id FROM plano_contas WHERE codigo = ? AND id != ?", (codigo, id))
        if cursor.fetchone():
            conn.close()
            abort(400, "Já existe outro plano com este código.")

        try:
            cursor.execute("""
                UPDATE plano_contas
                SET codigo = ?, nome = ?, categoria_id = ?
                WHERE id = ?
            """, (codigo, nome, categoria_id, id))

            conn.commit()

        except Exception as e:
            conn.rollback()
            print(e)
            abort(500, "Erro ao atualizar plano.")

        conn.close()

    return redirect(url_for("plano_contas"))

# REMOVER PLANO
@app.route("/plano_contas/plano/remover/<int:id>", methods=["POST"])
@login_required
def remover_plano_conta(id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM plano_contas WHERE id = ?", (id,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Plano não existe.")

    # Segurança: verificar vínculos
    cursor.execute("SELECT id FROM contas_pagar WHERE plano_conta_id = ? LIMIT 1", (id,))
    if cursor.fetchone():
        conn.close()
        abort(400, "Plano vinculado a contas a pagar.")

    cursor.execute("SELECT id FROM contas_receber WHERE plano_conta_id = ? LIMIT 1", (id,))
    if cursor.fetchone():
        conn.close()
        abort(400, "Plano vinculado a contas a receber.")

    try:
        cursor.execute("DELETE FROM plano_contas WHERE id = ?", (id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        abort(500, "Erro ao remover plano.")

    conn.close()

    return redirect(url_for("plano_contas"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").lower().strip()
        senha = request.form.get("senha")

        if not email or not senha:
            return "Email e senha são obrigatórios", 400

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id, senha_hash FROM usuarios WHERE email = ? AND ativo = 1", (email, ))
        usuario = cursor.fetchone()

        conn.close()

        if usuario:
            senha_hash = usuario[1]
            if check_password_hash(senha_hash, senha):
                session["usuario_id"] = usuario[0]
                return redirect(url_for("home"))
        else:
            return "Email ou senha inválidos", 400
    
    return render_template("login.html", erro="Email ou senha inválidos")

@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


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
            grupo_parcela_id INTEGER,
            conta_bancaria_id INTEGER,
            FOREIGN KEY (aluno_id) REFERENCES alunos(id),
            FOREIGN KEY (conta_bancaria_id) REFERENCES contas_bancarias(id)
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movimentacoes_bancarias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conta_bancaria_id INTEGER NOT NULL,
            tipo TEXT CHECK(tipo IN ('entrada', 'saida', 'estorno')) NOT NULL,
            valor REAL NOT NULL,
            data TEXT NOT NULL,
            origem TEXT,
            origem_id INTEGER,
            descricao TEXT,
            transferencia_id INTEGER,
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
# backup_banco()

if __name__ == '__main__':
    app.run(debug=False)
