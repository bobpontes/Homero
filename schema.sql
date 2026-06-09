CREATE TABLE alunos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            idade INTEGER NOT NULL,
            turma TEXT NOT NULL
        );
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE mensalidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aluno_id INTEGER NOT NULL,
            valor REAL,
            data_vencimento TEXT,
            status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','pago')),
            data_pagamento TEXT,
            metodo_pagamento TEXT, grupo_parcela_id INTEGER, conta_bancaria_id INTEGER REFERENCES contas_bancarias(id),
            FOREIGN KEY (aluno_id) REFERENCES alunos(id)
        );
CREATE TABLE categorias_plano_contas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE,
        nome TEXT NOT NULL
    , tipo TEXT);
CREATE TABLE plano_contas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE,
        nome TEXT NOT NULL,
        categoria_id INTEGER,
        FOREIGN KEY (categoria_id) REFERENCES categorias_plano_contas(id)
        );
CREATE TABLE contas_pagar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            data_vencimento TEXT,
            status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','pago')),
            data_pagamento TEXT,
            plano_conta_id INTEGER,
            grupo_parcela_id INTEGER, fornecedor_id INTEGER, evento_id INTEGER, metodo_pagamento TEXT, conta_bancaria_id INTEGER,
            FOREIGN KEY (plano_conta_id) REFERENCES plano_contas(id)
        );
CREATE TABLE fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            email TEXT,
            CPF TEXT,
            CNPJ TEXT);
CREATE TABLE eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL
    );
CREATE TABLE contas_receber (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            data_vencimento TEXT,
            status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','pago')),
            data_pagamento TEXT,
            plano_conta_id INTEGER,
            grupo_parcela_id INTEGER,
            fornecedor_id INTEGER,
            evento_id INTEGER, conta_bancaria_id INTEGER, metodo_pagamento TEXT,
            FOREIGN KEY (plano_conta_id) REFERENCES plano_contas(id),
            FOREIGN KEY (fornecedor_id) REFERENCES fornecedores(id),
            FOREIGN KEY (evento_id) REFERENCES eventos(id)
        );
CREATE TABLE contas_bancarias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT,
            saldo REAL DEFAULT 0,
            ativo BOOLEAN DEFAULT 1
        );
CREATE TABLE movimentacoes_bancarias (
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
        );
CREATE TABLE usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    ativo INTEGER DEFAULT 1,
    perfil TEXT DEFAULT 'admin',
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);
