from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    abort
)
from database.connection import get_db
from utils.auth import login_required
from utils.datas import adicionar_meses

from datetime import datetime, date
from decimal import Decimal

mensalidades_bp = Blueprint('mensalidades', __name__)

@mensalidades_bp.route("/financeiro")
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
        filtro_sql = "WHERE date(mensalidades.data_vencimento) BETWEEN date(%s) AND date(%s)"
        parametros = (data_inicio, data_fim)
    elif ano:
        filtro_sql = "WHERE TO_CHAR(mensalidades.data_vencimento, 'YYYY') = %s"
        parametros = (ano, )
    else:
        if not mes:
            mes = date.today().strftime("%Y-%m")
            
        filtro_sql = "WHERE TO_CHAR(mensalidades.data_vencimento, 'YYYY-MM') = %s"
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
                        AND date(mensalidades.data_vencimento) < CURRENT_DATE
                    THEN 'Vencido'
                    ELSE 'Pendente'
                END AS status
            FROM mensalidades
            LEFT JOIN alunos ON mensalidades.aluno_id = alunos.id
            {filtro_sql}
            ORDER BY
                CASE 
                    WHEN mensalidades.status = 'pendente'
                        AND date(mensalidades.data_vencimento) < CURRENT_DATE THEN 0 
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
            vencimento_data = vencimento
            dias_atraso = (date.today() - vencimento_data).days

        mensalidades_com_atraso.append(
            (id, nome, valor, vencimento, status, dias_atraso)
        )
    mensalidades = mensalidades_com_atraso

    cursor.execute("""
    SELECT COUNT(*)
    FROM mensalidades
    WHERE status = 'pendente'
    AND data_vencimento >= CURRENT_DATE
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
    AND data_vencimento < CURRENT_DATE
    """)
    vencidas = cursor.fetchone()[0]

    # Calcula qual o valor total vencido e pendente (ou seja, o valor total em aberto)
    cursor.execute("""
    SELECT SUM(valor)
    FROM mensalidades
    WHERE status = 'pendente'
    """)
    resultado = cursor.fetchone()
    total_aberto = resultado[0] if resultado[0] else Decimal('0')  # Se for None, retorna 0.0

    # Calculo de Receita Prevista para Dashboard Financeiro
    cursor.execute("""
    SELECT SUM(valor)
        FROM mensalidades WHERE status = 'pendente' AND TO_CHAR(data_vencimento, 'YYYY-MM') = %s
    """, (mes, ))

    resultado = cursor.fetchone()
    receita_prevista = resultado[0] if resultado[0] else Decimal('0')

    # Calculo de Despesa Prevista para Dashboard Financeiro
    cursor.execute("""
    SELECT SUM(valor)
        FROM contas_pagar WHERE status = 'pendente' AND TO_CHAR(data_vencimento, 'YYYY-MM') = %s
    """, (mes, ))

    resultado = cursor.fetchone()
    despesa_prevista = resultado[0] if resultado[0] else Decimal('0')

    # Saldo Projetado
    saldo_projetado = receita_prevista - despesa_prevista

    # Contas Bancárias
    cursor.execute("SELECT id, nome FROM contas_bancarias WHERE ativo = TRUE")
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

@mensalidades_bp.route("/mensalidade/nova", methods=["POST"])
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

    cursor.execute("SELECT id FROM alunos WHERE id = %s", (aluno_id, ))
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
                "INSERT INTO mensalidades (aluno_id, valor, data_vencimento, grupo_parcela_id) VALUES (%s, %s, %s, %s)",
                (aluno_id, valor, data_parcela, grupo_parcela_id)
            )
        conn.commit()
        conn.close()
        return redirect(url_for("mensalidades.financeiro"))
    
    conn.close()
    abort(400, "Todos os campos são obrigatórios.")

# Rotas para atualização de valores: (1 - Mens individual, 2 - tela de grupos de parcelas, 3 - tela de um grupo de parcelas, 4 - edição de parcelas de um grupo em lote)
# 1
@mensalidades_bp.route("/mensalidade/atualizar_valor/<int:id>", methods=["POST"])
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
        WHERE id = %s
    """, (id,))
    mensalidade = cursor.fetchone()

    if not mensalidade:
        conn.close()
        abort(404)

    _, aluno_id, status = mensalidade

    if status != "pendente":
        conn.close()
        abort(400, "Só é possível editar mensalidades pendentes.")

    cursor.execute("SELECT id FROM alunos WHERE id = %s", (aluno_id,))
    aluno = cursor.fetchone()

    if not aluno:
        conn.close()
        abort(400, "Aluno vinculado à mensalidade não foi encontrado.")

    try:
        cursor.execute("""
            UPDATE mensalidades
            SET valor = %s
            WHERE id = %s
              AND status = 'pendente'
        """, (novo_valor, id))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return redirect(url_for("mensalidades.financeiro"))

# 2
@mensalidades_bp.route("/mensalidade/grupos")
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
@mensalidades_bp.route("/mensalidade/grupo/<int:grupo_id>")
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
        WHERE m.grupo_parcela_id = %s
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
@mensalidades_bp.route("/mensalidade/grupo/<int:grupo_id>/atualizar_valor", methods=["POST"])
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
        WHERE grupo_parcela_id = %s
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

    cursor.execute("SELECT id FROM mensalidades WHERE grupo_parcela_id = %s", (grupo_id,))
    if not cursor.fetchone():
        conn.close()
        abort(404)

    # Buscar a primeira data de parcela pendente no banco:
    cursor.execute("""
        SELECT MIN(data_vencimento)
        FROM mensalidades
        WHERE grupo_parcela_id = %s
        AND status = 'pendente'
    """, (grupo_id,))
    resultado = cursor.fetchone()
    primeira_pendente = resultado[0] if resultado and resultado[0] else None

    # transformar data de string para data:
    data_inicial_date = datetime.strptime(data_inicial, "%Y-%m-%d").date()
    if primeira_pendente:
        primeira_pendente_date = primeira_pendente

        if primeira_pendente and data_inicial_date < primeira_pendente_date:
            data_inicial = primeira_pendente

    cursor.execute("""
        SELECT COUNT(*)
        FROM mensalidades
        WHERE grupo_parcela_id = %s
          AND status = 'pendente'
          AND data_vencimento >= %s
    """, (grupo_id, data_inicial))
    total_editaveis = cursor.fetchone()[0]

    if total_editaveis == 0:
        conn.close()
        abort(400, "Não existem parcelas pendentes para atualizar a partir desta data.")

    try:
        cursor.execute("""
            UPDATE mensalidades
            SET valor = %s
            WHERE grupo_parcela_id = %s
              AND status = 'pendente'
              AND data_vencimento >= %s
        """, (novo_valor, grupo_id, data_inicial))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return redirect(url_for("mensalidades.detalhar_grupo_mensalidade", grupo_id=grupo_id))

# Edição individual de parcelas no grupo
@mensalidades_bp.route("/mensalidade/grupo/<int:grupo_id>/parcela/<int:id>/atualizar_valor", methods=["POST"])
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
        WHERE id=%s
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

    cursor.execute("SELECT id FROM alunos WHERE id=%s", (aluno_id, ))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Aluno vinculado à mensalidade não foi encontrado.")

    try:
        cursor.execute("""
            UPDATE mensalidades
            SET valor = %s
            WHERE id = %s
                AND grupo_parcela_id = %s
                AND status = 'pendente'
        """, (novo_valor, id, grupo_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return (redirect(url_for("mensalidades.detalhar_grupo_mensalidade", grupo_id=grupo_id)))

@mensalidades_bp.route("/pagar/<int:id>", methods=["POST"])
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
    cursor.execute("SELECT id FROM contas_bancarias WHERE id = %s", (conta_bancaria_id, ))
    conta_bancaria = cursor.fetchone()

    if not conta_bancaria:
        conn.close()
        abort(400, "Uma conta bancária inválida foi selecionada.")

    # Segundo: verificar se a mensalidade existe
    cursor.execute("SELECT id FROM mensalidades WHERE id = %s", (id, ))
    mensalidade = cursor.fetchone()

    if not mensalidade:
        conn.close()
        abort(404)

    # Terceiro: verificar se a mensalidade ainda não foi paga
    cursor.execute("SELECT status FROM mensalidades WHERE id = %s", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Não é possível registrar o pagamento, a mensalidade já havia sido paga.")
    
    # 4) Segurança: conferir o valor da mensalidade:
    cursor.execute("SELECT valor FROM mensalidades WHERE id = %s", (id, ))
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
        cursor.execute("""UPDATE mensalidades SET status = 'pago', data_pagamento = %s, metodo_pagamento = %s, conta_bancaria_id = %s WHERE id = %s""",
            (data_pagamento, metodo_pagamento, conta_bancaria_id, id))

        # 6) Atualizar tabela movimentacoes_bancarias:
        cursor.execute("""
            SELECT alunos.nome
            FROM mensalidades
            JOIN alunos ON mensalidades.aluno_id = alunos.id
            WHERE mensalidades.id = %s
        """, (id, ))
        resultado_nome = cursor.fetchone()

        if not resultado_nome:
            conn.rollback()
            abort(500, "Erro ao obter nome do aluno.")

        nome_aluno = resultado_nome[0]

        cursor.execute("""
            INSERT INTO movimentacoes_bancarias
                       (conta_bancaria_id, tipo, valor, data, origem, origem_id, descricao)
                       VALUES (%s, 'entrada', %s, %s, 'mensalidade', %s, %s)
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
            SET saldo = saldo + %s
            WHERE id = %s
        """, (valor, conta_bancaria_id))
        
        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        raise
    
    conn.close()

    return redirect(url_for("mensalidades.financeiro"))

@mensalidades_bp.route("/mensalidade/estornar/<int:id>", methods=["POST"])
@login_required
def estornar_mensalidade(id):

    # 0) Data da movimentação:
    data_hoje = date.today()

    conn = get_db()
    cursor = conn.cursor()

    # 1) Verifica se existe
    cursor.execute("SELECT status, conta_bancaria_id FROM mensalidades WHERE id = %s", (id, ))
    resultado = cursor.fetchone()

    if not resultado:
        conn.close()
        abort(404)

    status, conta_bancaria_id = resultado

    # 1.1) Verificar o valor:
    cursor.execute("""
        SELECT valor
        FROM movimentacoes_bancarias
        WHERE origem = 'mensalidade'
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
        WHERE mensalidades.id = %s
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
            WHERE id = %s
        """, (id, ))

        # 6) Registrar a movimentação do Estorno
        cursor.execute("""
            INSERT INTO movimentacoes_bancarias
            (conta_bancaria_id, tipo, valor, data, origem, origem_id, descricao)
            VALUES (%s, 'estorno', %s, %s, 'mensalidade', %s, %s)
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
            SET saldo = saldo - %s
            WHERE id = %s
        """, (valor, conta_bancaria_id))

        conn.commit()
    
    except Exception as e:
        conn.rollback()
        print(e)
        raise

    conn.close()

    return redirect(url_for("mensalidades.financeiro"))

@mensalidades_bp.route("/mensalidade/remover/<int:id>", methods=["POST"])
@login_required
def remover_mensalidade(id):
    conn = get_db()
    cursor = conn.cursor()

    # Verificar se mensalidade existe
    cursor.execute("SELECT id FROM mensalidades WHERE id = %s", (id, ))
    mensalidade = cursor.fetchone()

    if not mensalidade:
        conn.close()
        abort(404)

    # Verficar se mensalidade ainda não foi paga
    cursor.execute("SELECT status FROM mensalidades WHERE id = %s", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Não é possível excluir uma mensalidade que já foi registrada como paga.")

    cursor.execute("DELETE FROM mensalidades WHERE id = %s", (id, ))

    conn.commit()
    conn.close()

    return redirect(url_for("mensalidades.financeiro"))

@mensalidades_bp.route("/mensalidade/remover_grupo/<int:grupo_id>", methods = ['POST'])
@login_required
def remover_grupo_mensalidade(grupo_id):

    conn = get_db()
    cursor = conn.cursor()

    # Verificar se o grupo existe
    cursor.execute("SELECT grupo_parcela_id FROM mensalidades WHERE grupo_parcela_id = %s", (grupo_id, ))
    grupo = cursor.fetchone()

    if not grupo:
        conn.close()
        abort(400, "Este grupo de parcelas não existe, portanto nenhuma mensalidade foi excluída.")

    # Verificar se existe alguma mensalidade paga no grupo
    cursor.execute("""SELECT status FROM mensalidades WHERE grupo_parcela_id = %s AND status = 'pago'""", (grupo_id, ))
    existe_pago = cursor.fetchone()

    if existe_pago:
        conn.close()
        abort(400, "Não é possível excluir um grupo com mensalidades já pagas.")

    cursor.execute("DELETE FROM mensalidades WHERE grupo_parcela_id = %s", (grupo_id, ))

    conn.commit()
    conn.close()

    return redirect(url_for("mensalidades.financeiro"))