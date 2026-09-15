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

contas_pagar_bp = Blueprint("contas_pagar", __name__)

@contas_pagar_bp.route("/conta/nova", methods=["POST"])
@login_required
def nova_conta():
    
    descricao = (request.form.get("descricao") or "").strip()
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

    cursor.execute("SELECT id FROM plano_contas WHERE id = %s", (plano_conta_id, ))
    if not cursor.fetchone():
        conn.close()
        abort(400, "Plano de conta não encontrado.")

    cursor.execute("SELECT id FROM fornecedores WHERE id = %s", (fornecedor_id, ))
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
            "INSERT INTO contas_pagar (descricao, valor, data_vencimento, plano_conta_id, grupo_parcela_id, fornecedor_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (descricao, valor, data_parcela, plano_conta_id, grupo_parcela_id, fornecedor_id)
        )

    conn.commit()
    conn.close()

    return redirect(url_for("contas_pagar.contas_pagar"))

@contas_pagar_bp.route("/contas_pagar")
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
                    AND date(contas_pagar.data_vencimento) < CURRENT_DATE
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
                    AND date(contas_pagar.data_vencimento) < CURRENT_DATE THEN 0
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
            vencimento_data = vencimento
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

    cursor.execute("SELECT id, nome FROM contas_bancarias WHERE ativo = TRUE ORDER BY nome")
    contas_banco = cursor.fetchall()

    conn.close()

    return render_template("contas_pagar.html", contas=contas, categorias=categorias, planos=planos, fornecedores=fornecedores, today=date.today(), contas_banco=contas_banco)

# Atualização Individual
@contas_pagar_bp.route("/contas_pagar/atualizar/<int:id>", methods=["POST"])
@login_required
def atualizar_conta_pagar(id):
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

    cursor.execute("SELECT status FROM contas_pagar WHERE id = %s", (id,))
    conta = cursor.fetchone()

    if not conta:
        conn.close()
        abort(404)

    if conta[0] != "pendente":
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
            UPDATE contas_pagar
            SET descricao = %s,
                valor = %s,
                data_vencimento = %s,
                plano_conta_id = %s,
                fornecedor_id = %s
            WHERE id = %s
              AND status = 'pendente'
        """, (descricao, valor, data_vencimento, plano_conta_id, fornecedor_id, id))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
        conn.close()
        raise

    conn.close()
    return redirect(url_for("contas_pagar.contas_pagar"))

# Atualização em lote: Listar grupos de parcelas
@contas_pagar_bp.route("/contas_pagar/grupos")
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
@contas_pagar_bp.route("/contas_pagar/grupo/<int:grupo_id>")
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
        WHERE cp.grupo_parcela_id = %s
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
@contas_pagar_bp.route("/contas_pagar/grupo/<int:grupo_id>/atualizar_valor", methods=["POST"])
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
            abort(400, "Fornecedor inválido.")

        cursor.execute("SELECT id FROM fornecedores WHERE id = %s", (novo_fornecedor_id_int,))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Fornecedor não encontrado.")

    cursor.execute("SELECT id FROM contas_pagar WHERE grupo_parcela_id = %s", (grupo_id,))
    if not cursor.fetchone():
        conn.close()
        abort(404)

    cursor.execute("""
        SELECT COUNT(*)
        FROM contas_pagar
        WHERE grupo_parcela_id = %s
          AND status = 'pendente'
          AND data_vencimento >= %s
    """, (grupo_id, data_inicial))
    total_editaveis = cursor.fetchone()[0]

    if total_editaveis == 0:
        conn.close()
        abort(400, "Não existem contas pendentes para atualizar a partir desta data.")

    try:
        cursor.execute("""
            UPDATE contas_pagar
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
    return redirect(url_for("contas_pagar.detalhar_grupo_conta_pagar", grupo_id=grupo_id))

# Atualizar uma parcela do grupo:
@contas_pagar_bp.route("/contas_pagar/grupo/<int:grupo_id>/parcela/<int:id>/atualizar", methods=["POST"])
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

        cursor.execute("SELECT id FROM plano_contas WHERE id = %s", (plano_conta_id_int,))
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

        cursor.execute("SELECT id FROM fornecedores WHERE id = %s", (fornecedor_id_int,))
        if not cursor.fetchone():
            conn.close()
            abort(400, "Fornecedor não encontrado.")

    cursor.execute("""
        SELECT id, status, grupo_parcela_id
        FROM contas_pagar
        WHERE id = %s
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
    return redirect(url_for("contas_pagar.detalhar_grupo_conta_pagar", grupo_id=grupo_id))

@contas_pagar_bp.route("/contas_pagar/pagar/<int:id>", methods=["POST"])
@login_required
def registrar_conta(id):

    data_pagamento = request.form.get("data_pagamento")
    metodo_pagamento = request.form.get("metodo_pagamento")
    conta_bancaria_id = request.form.get("conta_bancaria_id")
    valor_pago = request.form.get("valor_pago")
    nova_descricao = (request.form.get("descricao") or "").strip()

    if not data_pagamento or not metodo_pagamento or not conta_bancaria_id:
        abort(400, "Todos os dados são obrigatórios.")

    conn = get_db()
    cursor = conn.cursor()

    # 1) Verifica se a conta bancária existe:
    cursor.execute("SELECT id FROM contas_bancarias WHERE id = %s", (conta_bancaria_id, ))
    conta_bancaria = cursor.fetchone()

    if not conta_bancaria:
        conn.close()
        abort(400, "Conta bancária inválida, pagamento não registrado.")

    # 2) Verificar se conta existe:
    cursor.execute("SELECT id FROM contas_pagar WHERE id = %s", (id, ))
    conta = cursor.fetchone()

    if not conta:
        conn.close()
        abort(404)

    # 3) Verificar se conta já está paga:
    cursor.execute("SELECT status FROM contas_pagar WHERE id = %s", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Conta já está paga.")

    # 4) Segurança: conferir valor da conta para pagar:
    cursor.execute("SELECT descricao, valor FROM contas_pagar WHERE id = %s", (id, ))
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
                       data_pagamento = %s,
                       metodo_pagamento = %s,
                       conta_bancaria_id = %s,
                       descricao = %s
                       WHERE id = %s""",
            (data_pagamento, metodo_pagamento, conta_bancaria_id, nova_descricao, id)
        )

        # 6) Atualizar tabela movimentacoes_bancarias:
        cursor.execute("""
            INSERT INTO movimentacoes_bancarias
                (conta_bancaria_id, tipo, valor, data, origem, origem_id, descricao)
                VALUES (%s, 'saida', %s, %s, 'contas_pagar', %s, %s)
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
            SET saldo = saldo - %s
            WHERE id = %s
        """, (valor, conta_bancaria_id))

        conn.commit()
    
    except Exception as e:
        conn.rollback()
        print(e)
        raise
    
    conn.close()

    return redirect(url_for("contas_pagar.contas_pagar"))

@contas_pagar_bp.route("/contas_pagar/estornar/<int:id>", methods=["POST"])
@login_required
def estornar_contas_pagar(id):

    # 0) Data da movimentação:
    data_hoje = date.today()

    conn = get_db()
    cursor = conn.cursor()

    # 1) Verifica se existe
    cursor.execute("SELECT descricao, status, conta_bancaria_id FROM contas_pagar WHERE id = %s", (id, ))
    resultado = cursor.fetchone()

    if not resultado:
        conn.close()
        abort(404)

    descricao, status, conta_bancaria_id = resultado

    # 1.1) Verificar o valor:
    cursor.execute("""
        SELECT valor
        FROM movimentacoes_bancarias
        WHERE origem = 'contas_pagar'
        AND origem_id = %s
        AND tipo = 'saida'
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
            UPDATE contas_pagar
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
            VALUES (%s, 'estorno', %s, %s, 'contas_pagar', %s, %s)
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
            SET saldo = saldo + %s
            WHERE id = %s
        """, (valor, conta_bancaria_id))

        conn.commit()
    
    except Exception as e:
        conn.rollback()
        print(e)
        raise

    conn.close()

    return redirect(url_for("contas_pagar.contas_pagar"))

@contas_pagar_bp.route("/contas_pagar/remover/<int:id>", methods=["POST"])
@login_required
def remover_conta(id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM contas_pagar WHERE id = %s", (id, ))
    conta = cursor.fetchone()

    if not conta:
        conn.close()
        abort(400, "Essa conta não existe, portanto não pode ser excluída.")

    cursor.execute("SELECT status FROM contas_pagar WHERE id = %s", (id, ))
    resultado = cursor.fetchone()

    if resultado and resultado[0] == 'pago':
        conn.close()
        abort(400, "Não é possível excluir conta já paga.")

    cursor.execute("DELETE FROM contas_pagar WHERE id = %s", (id, ))

    conn.commit()
    conn.close()

    return redirect(url_for("contas_pagar.contas_pagar"))

@contas_pagar_bp.route("/contas_pagar/remover_grupo/<int:grupo_id>", methods=["POST"])
@login_required
def remover_grupo_conta(grupo_id):

    conn = get_db()
    cursor = conn.cursor()

    # Verificar se existe o grupo
    cursor.execute("SELECT grupo_parcela_id FROM contas_pagar WHERE grupo_parcela_id = %s", (grupo_id, ))
    grupo = cursor.fetchone()

    if not grupo:
        conn.close()
        abort(400, "Este grupo de parcelas não existe, portanto nenhuma conta foi excluída.")

    # Verificar se já existe conta paga no grupo
    cursor.execute("""SELECT status FROM contas_pagar WHERE grupo_parcela_id = %s AND status = 'pago'""", (grupo_id, ))
    existe_pago = cursor.fetchone()

    if existe_pago:
        conn.close()
        abort(400, "Não é possível excluir um grupo com contas já pagas.")

    cursor.execute("DELETE FROM contas_pagar WHERE grupo_parcela_id = %s", (grupo_id, ))

    conn.commit()
    conn.close()

    return redirect(url_for("contas_pagar.contas_pagar"))