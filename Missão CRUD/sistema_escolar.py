import json

def salvar_alunos():
    with open("alunos.json", "w") as arquivo:
        json.dump(alunos, arquivo, indent=4)

def carregar_alunos():
    try:
        with open("alunos.json", "r") as arquivo:
            return json.load(arquivo)
    except FileNotFoundError:
        return []

alunos = carregar_alunos()

def cadastrar_aluno():
    nome = input("Nome do aluno: ")
    idade = input("Idade: ")
    turma = input("Turma: ")

    aluno = {"nome": nome, "idade": idade, "turma": turma}
    alunos.append(aluno)
    salvar_alunos()
    print("✅ Aluno cadastrado!")

def listar_alunos():
    print("\n📋 LISTA DE ALUNOS")
    for i, aluno in enumerate(alunos):
        print(f"{i} - {aluno['nome']} | {aluno['idade']} anos | {aluno['turma']}")

def editar_aluno():
    listar_alunos()
    indice = int(input("Número do aluno para editar: "))

    if 0 <= indice < len(alunos):
        nome = input("Novo nome: ")
        idade = input("Nova idade: ")
        turma = input("Nova turma: ")

        alunos[indice] = {"nome": nome, "idade": idade, "turma": turma}
        salvar_alunos()
        print("✅ Aluno atualizado!")
    else:
        print("❌ Índice inválido!")

def remover_aluno():
    listar_alunos()
    indice = int(input("Digite o número do aluno que deseja remover:"))

    if 0 <= indice < len(alunos):
        removido = alunos.pop(indice)
        salvar_alunos()
        print(f"✅ Aluno {removido['nome']} removido!")
    else:
        print("❌ Índice inválido!")

while True:
    print("\n=== SISTEMA ESCOLAR ===")
    print("1 - Cadastrar aluno")
    print("2 - Listar alunos")
    print("3 - Editar aluno")
    print("4 - Remover aluno")
    print("5 - Sair")

    opcao = input("Escolha uma opção: ")

    if opcao == "1":
        cadastrar_aluno()
    elif opcao == "2":
        listar_alunos()
    elif opcao == "3":
        editar_aluno()
    elif opcao == "4":
        remover_aluno()
    elif opcao == "5":
        print("Encerrando sistema...")
        break
    else:
        print("❌ Opção Inválida")




