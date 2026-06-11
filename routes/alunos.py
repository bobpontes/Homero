from flask import (
    Blueprint,
    request,
    redirect,
    url_for,
    render_template,
    abort,
    Response
)

from database.connection import get_db

from utils.auth import login_required

alunos_bp = Blueprint(
    'alunos',
    __name__,
    url_prefix="/alunos"
)

@alunos_bp.route("/remover/<int:id>", methods=["POST"])
@login_required
def remover_aluno(id):
    conn = get_db()
    cursor = conn.cursor()


    cursor.execute("SELECT * FROM alunos WHERE id = %s", (id, ))
    aluno = cursor.fetchone()

    if aluno is None:
        conn.close()
        abort(404)

    # apagar mensalidades associadas a este aluno (antes de apagar o aluno)
    cursor.execute("DELETE FROM mensalidades WHERE aluno_id = %s", (id, ))
    # (após) apagar o aluno do banco
    cursor.execute("DELETE FROM alunos WHERE id = %s", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("home"))

@alunos_bp.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_aluno(id):

    conn = get_db()
    cursor = conn.cursor()

    # buscar aluno primeiro:
    cursor.execute("SELECT * FROM alunos WHERE id = %s", (id, ))
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
            "UPDATE alunos SET nome = %s, idade = %s, turma = %s WHERE id = %s",
            (nome, idade, turma, id)
        )

        conn.commit()
        conn.close()
        return redirect(url_for("home"))

    conn.close()
    return render_template("editar.html", aluno=aluno)

@alunos_bp.route("/exportar/alunos")
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