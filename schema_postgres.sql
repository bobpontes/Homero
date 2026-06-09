CREATE TABLE alunos (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            idade INTEGER NOT NULL,
            turma TEXT NOT NULL
        );
CREATE TABLE contas_bancarias (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            tipo TEXT,
            saldo NUMERIC(10,2) DEFAULT 0,
            ativo BOOLEAN DEFAULT TRUE
        );
CREATE TABLE mensalidades (
            id SERIAL PRIMARY KEY,
            aluno_id INTEGER NOT NULL,
            valor NUMERIC(10,2),
            data_vencimento DATE,
            status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','pago')),
            data_pagamento DATE,
            metodo_pagamento TEXT,
            grupo_parcela_id INTEGER,
            conta_bancaria_id INTEGER REFERENCES contas_bancarias(id),
            FOREIGN KEY (aluno_id) REFERENCES alunos(id)
        );
CREATE TABLE categorias_plano_contas (
        id SERIAL PRIMARY KEY,
        codigo TEXT UNIQUE,
        nome TEXT NOT NULL
    , tipo TEXT);
CREATE TABLE plano_contas (
        id SERIAL PRIMARY KEY,
        codigo TEXT UNIQUE,
        nome TEXT NOT NULL,
        categoria_id INTEGER,
        FOREIGN KEY (categoria_id) REFERENCES categorias_plano_contas(id)
        );
CREATE TABLE contas_pagar (
            id SERIAL PRIMARY KEY,
            descricao TEXT NOT NULL,
            valor NUMERIC(10,2) NOT NULL,
            data_vencimento DATE,
            status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','pago')),
            data_pagamento DATE,
            plano_conta_id INTEGER,
            grupo_parcela_id INTEGER,
            fornecedor_id INTEGER,
            evento_id INTEGER,
            metodo_pagamento TEXT,
            conta_bancaria_id INTEGER,
            FOREIGN KEY (plano_conta_id) REFERENCES plano_contas(id)
        );
CREATE TABLE fornecedores (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            telefone TEXT,
            email TEXT,
            cpf TEXT,
            cnpj TEXT);
CREATE TABLE eventos (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL
    );
CREATE TABLE contas_receber (
            id SERIAL PRIMARY KEY,
            descricao TEXT NOT NULL,
            valor NUMERIC(10,2) NOT NULL,
            data_vencimento DATE,
            status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','pago')),
            data_pagamento DATE,
            plano_conta_id INTEGER,
            grupo_parcela_id INTEGER,
            fornecedor_id INTEGER,
            evento_id INTEGER,
            conta_bancaria_id INTEGER,
            metodo_pagamento TEXT,
            FOREIGN KEY (plano_conta_id) REFERENCES plano_contas(id),
            FOREIGN KEY (fornecedor_id) REFERENCES fornecedores(id),
            FOREIGN KEY (evento_id) REFERENCES eventos(id)
        );
CREATE TABLE movimentacoes_bancarias (
            id SERIAL PRIMARY KEY,
            conta_bancaria_id INTEGER NOT NULL,
            tipo TEXT CHECK(tipo IN ('entrada', 'saida', 'estorno')) NOT NULL,
            valor NUMERIC(10,2) NOT NULL,
            data DATE NOT NULL,
            origem TEXT,
            origem_id INTEGER,
            descricao TEXT,
            transferencia_id INTEGER,
            FOREIGN KEY (conta_bancaria_id) REFERENCES contas_bancarias(id)
        );
CREATE TABLE usuarios (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    ativo BOOLEAN DEFAULT TRUE,
    perfil TEXT DEFAULT 'admin',
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
