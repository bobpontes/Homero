from flask import Flask, request, render_template, redirect, url_for, abort, Response, session
from datetime import datetime, timedelta, date
from werkzeug.security import check_password_hash
# from functools import wraps
import shutil
import os
import csv
from decimal import Decimal

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_key")

# Data de hoje
today = date.today()

# Login Required:
from utils.auth import login_required

# Utilidades de datas:
from utils.datas import adicionar_meses, MESES

# função para chamar o banco de dados:
from database.connection import get_db

# helper para aplicação de filtro no sql:
from utils.sql import aplicar_condicao


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
        filtro_sql = "WHERE DATE(contas_receber.data_vencimento) BETWEEN DATE(%s) AND DATE(%s)"
        parametros = (data_inicio, data_fim)
        
        mes1 = MESES[data_inicio[5:7]]
        mes2 = MESES[data_fim[5:7]]

        periodo_formatado = (
            f"{data_inicio[8:10]} {mes1[:3]} {data_inicio[0:4]} "
            f"até {data_fim[8:10]} {mes2[:3]} {data_fim[0:4]}"
        )

    elif ano:
        filtro_sql = "WHERE TO_CHAR(contas_receber.data_vencimento, 'YYYY') = %s"
        parametros = (ano, )
        periodo_formatado = f"Ano de {ano}"

    else:
        if not mes:
            mes = date.today().strftime("%Y-%m")
            
        filtro_sql = "WHERE TO_CHAR(contas_receber.data_vencimento, 'YYYY-MM') = %s"
        parametros = (mes, )
        periodo_formatado = f"{MESES[mes[5:7]]}/{mes[0:4]}"

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
                    AND date(contas_receber.data_vencimento) < CURRENT_DATE
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
                    AND date(contas_receber.data_vencimento) < CURRENT_DATE THEN 0
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
            vencimento_data = vencimento
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
    filtro_receber_vencidas = aplicar_condicao(filtro_receber, "status = 'pendente' AND data_vencimento < CURRENT_DATE")
    filtro_receber_pago = aplicar_condicao(filtro_receber, "status = 'pago'")

    # Gráfico do Dashboard
    # Receitas e Mensalidades
    cursor.execute(f"""
    SELECT SUM(valor)
    FROM contas_receber
    {filtro_receber}
    """, parametros)
    resultado_c_receber = cursor.fetchone()
    total_contas_receber = resultado_c_receber[0] if resultado_c_receber and resultado_c_receber[0] else Decimal('0')
    total_receitas = total_contas_receber

    cursor.execute(f"""
    SELECT SUM(valor)
    FROM mensalidades
    {filtro_mensalidades}
    """, parametros)
    resultado_mensalidades = cursor.fetchone()
    total_contas_mensalidades = resultado_mensalidades[0] if resultado_mensalidades and resultado_mensalidades[0] else Decimal('0')
    total_mensalidades = total_contas_mensalidades

    receita_total = total_receitas + total_mensalidades

    # Despesas
    cursor.execute(f"""
    SELECT SUM(valor)
    FROM contas_pagar
    {filtro_pagar}
    """, parametros)
    resultado_c_pagar = cursor.fetchone()
    total_despesas = resultado_c_pagar[0] if resultado_c_pagar and resultado_c_pagar[0] else Decimal('0')

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
    total_receitas_pendentes = resultado_receitas_pendente[0] if resultado_receitas_pendente and resultado_receitas_pendente[0] else Decimal('0')  # Se for None, retorna 0.0
    total_aberto = total_receitas_pendentes
        

    cursor.execute("SELECT id, nome FROM categorias_plano_contas ORDER BY nome")
    categorias = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM plano_contas ORDER BY nome")
    planos = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM fornecedores ORDER BY nome")
    fornecedores = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM contas_bancarias WHERE ativo = TRUE ORDER BY nome")
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

    cursor.execute("SELECT id FROM plano_contas WHERE id = %s", (plano_conta_id, ))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Plano de conta não encontrado.")

    cursor.execute("SELECT id FROM fornecedores WHERE id = %s", (fornecedor_id, ))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Fornecedor não encontrado.")

    if evento_id:
        try:
            evento_id = int(evento_id)
        except (TypeError, ValueError):
            conn.close()
            abort(400, "Evento inválido.")

        cursor.execute("SELECT id FROM eventos WHERE id = %s", (evento_id, ))
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
            "INSERT INTO contas_receber (descricao, valor, data_vencimento, plano_conta_id, grupo_parcela_id, fornecedor_id, evento_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (descricao, valor, data_parcela, plano_conta_id, grupo_parcela_id, fornecedor_id, evento_id)
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

        cursor.execute("SELECT id FROM eventos WHERE id = %s", (evento_id, ))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Evento não encontrado.")
        
    else:
        evento_id = None

    cursor.execute("SELECT status FROM contas_receber WHERE id = %s", (id,))
    conta = cursor.fetchone()

    if not conta:
        conn.close()
        abort(404)

    status = conta[0]

    if status != "pendente":
        conn.close()
        abort(400, "Só é possível editar contas pendentes.")

    cursor.execute("SELECT id FROM plano_contas WHERE id = %s", (plano_conta_id,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Plano de conta não encontrado.")

    cursor.execute("SELECT id FROM fornecedores WHERE id = %s", (fornecedor_id,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Fornecedor não encontrado.")

    try:
        cursor.execute("""
            UPDATE contas_receber
            SET descricao = %s,
                valor = %s,
                data_vencimento = %s,
                plano_conta_id = %s,
                fornecedor_id = %s,
                evento_id = %s
            WHERE id = %s
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
        WHERE cr.grupo_parcela_id = %s
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

        cursor.execute("SELECT id FROM plano_contas WHERE id = %s", (novo_plano_conta_id_int,))
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

        cursor.execute("SELECT id FROM fornecedores WHERE id = %s", (novo_fornecedor_id_int,))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Cliente não encontrado.")

    cursor.execute("SELECT id FROM contas_receber WHERE grupo_parcela_id = %s", (grupo_id,))
    if not cursor.fetchone():
        conn.close()
        abort(404)

    cursor.execute("""
        SELECT COUNT(*)
        FROM contas_receber
        WHERE grupo_parcela_id = %s
          AND status = 'pendente'
          AND data_vencimento >= date(%s)
    """, (grupo_id, data_inicial))
    total_editaveis = cursor.fetchone()[0]

    if total_editaveis == 0:
        conn.close()
        abort(400, "Não existem recebimentos pendentes para atualizar a partir desta data.")

    try:
        cursor.execute("""
            UPDATE contas_receber
            SET descricao = COALESCE(%s, descricao),
                valor = COALESCE(%s, valor),
                plano_conta_id = COALESCE(%s, plano_conta_id),
                fornecedor_id = COALESCE(%s, fornecedor_id)
            WHERE grupo_parcela_id = %s
              AND status = 'pendente'
              AND data_vencimento >= %s
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

    cursor.execute("SELECT id FROM plano_contas WHERE id = %s", (plano_conta_id_int,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Plano de conta não encontrado.")

    cursor.execute("SELECT id FROM fornecedores WHERE id = %s", (fornecedor_id_int,))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Cliente não encontrado.")

    cursor.execute("""
        SELECT id, status, grupo_parcela_id
        FROM contas_receber
        WHERE id = %s
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
            SET descricao = %s,
                valor = %s,
                data_vencimento = %s,
                plano_conta_id = %s,
                fornecedor_id = %s
            WHERE id = %s
              AND grupo_parcela_id = %s
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
    cursor.execute("SELECT id FROM contas_bancarias WHERE id = %s", (conta_bancaria_id, ))
    conta_bancaria = cursor.fetchone()

    if not conta_bancaria:
        conn.close()
        abort(400, "Conta bancária inválida.")

    # 2) Verificar se conta existe:
    cursor.execute("SELECT id FROM contas_receber WHERE id = %s", (id, ))
    receita = cursor.fetchone()

    if not receita:
        conn.close()
        abort(404)

    # 3) Verificar se conta já está paga:
    cursor.execute("SELECT status FROM contas_receber WHERE id = %s", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Recebimento já está pago.")

    # 4) Segurança: conferir descrição e valor da conta para recebimento:
    cursor.execute("SELECT descricao, valor FROM contas_receber WHERE id = %s", (id, ))
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
        cursor.execute("""UPDATE contas_receber SET status = 'pago', data_pagamento = %s, metodo_pagamento = %s, conta_bancaria_id = %s WHERE id = %s""",
            (data_pagamento, metodo_pagamento, conta_bancaria_id, id))

        # 6) Atualizar tabela movimentacoes_bancarias:
        cursor.execute("""
            INSERT INTO movimentacoes_bancarias
                    (conta_bancaria_id, tipo, valor, data, origem, origem_id, descricao)
                    VALUES (%s, 'entrada', %s, %s, 'contas_receber', %s, %s)
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
            SET saldo = saldo + %s
            WHERE id = %s
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
    data_hoje = date.today()

    conn = get_db()
    cursor = conn.cursor()

    # 1) Verifica se existe
    cursor.execute("SELECT descricao, status, conta_bancaria_id FROM contas_receber WHERE id = %s", (id, ))
    resultado = cursor.fetchone()

    if not resultado:
        conn.close()
        abort(404)

    descricao, status, conta_bancaria_id = resultado

    # 1.1) Verificar valor:
    cursor.execute("""
        SELECT valor
        FROM movimentacoes_bancarias
        WHERE origem = 'contas_receber'
        AND origem_id = %s
        AND tipo = 'entrada'
        ORDER BY id DESC
        LIMIT 1
    """, (id, ))

    resultado_mov = cursor.fetchone()

    if not resultado_mov:
        conn.close()
        abort(400, "Movimentação bancária original não encontrada.")

    valor = resultado_mov[0]

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
            WHERE id = %s
        """, (id, ))

        # 5) Registrar a movimentação do Estorno
        cursor.execute("""
            INSERT INTO movimentacoes_bancarias
            (conta_bancaria_id, tipo, valor, data, origem, origem_id, descricao)
            VALUES (%s, 'estorno', %s, %s, 'contas_receber', %s, %s)
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
            SET saldo = saldo - %s
            WHERE id = %s
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

    cursor.execute("SELECT id FROM contas_receber WHERE id = %s", (id, ))
    receita = cursor.fetchone()

    if not receita:
        conn.close()
        abort(400, "Esse recebimento não existe, portanto não pode ser excluída.")

    cursor.execute("SELECT status FROM contas_receber WHERE id = %s", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Não é possível excluir recebimento já pago.")

    cursor.execute("DELETE FROM contas_receber WHERE id = %s", (id, ))

    conn.commit()
    conn.close()

    return redirect(url_for("contas_receber"))

@app.route("/contas_receber/remover_grupo/<int:grupo_id>", methods=["POST"])
@login_required
def remover_grupo_receita(grupo_id):

    conn = get_db()
    cursor = conn.cursor()

    # Verificar se existe o grupo
    cursor.execute("SELECT grupo_parcela_id FROM contas_receber WHERE grupo_parcela_id = %s", (grupo_id, ))
    grupo = cursor.fetchone()

    if not grupo:
        conn.close()
        abort(400, "Este grupo de parcelas não existe, portanto nenhum recebimento foi excluído.")

    # Verificar se já existe conta paga no grupo
    cursor.execute("""SELECT status FROM contas_receber WHERE grupo_parcela_id = %s AND status = 'pago'""", (grupo_id, ))
    existe_pago = cursor.fetchone()

    if existe_pago:
        conn.close()
        abort(400, "Não é possível excluir um grupo com recebimentos já pagos.")

    cursor.execute("DELETE FROM contas_receber WHERE grupo_parcela_id = %s", (grupo_id, ))

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
    app.run(debug=False)
