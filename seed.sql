-- =========================
-- CATEGORIAS
-- =========================
INSERT INTO categorias_plano_contas (codigo, nome, tipo) VALUES
('1', 'Receitas', 'receita'),
('2.1', 'Pessoal', 'despesa'),
('2.2', 'Materiais e Suprimentos', 'despesa'),
('2.3', 'Serviços Contratados', 'despesa'),
('2.4', 'Utilidades', 'despesa'),
('2.5', 'Marketing', 'despesa'),
('2.6', 'Eventos', 'despesa'),
('3.1', 'Investimentos / Aquisição de Itens', 'despesa'),
('3.2', 'Produtos para Venda', 'despesa'),
('4', 'Obrigações e Impostos', 'despesa'),
('5.1', 'Financeiro (Entradas)', 'receita'),
('5.2', 'Financeiro (Saídas)', 'despesa'),
('6', 'Transferências', 'transferencia');

-- =========================
-- RECEITAS
-- =========================
INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Mensalidade', id FROM categorias_plano_contas WHERE codigo = '1';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Ingressos', id FROM categorias_plano_contas WHERE codigo = '1';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Livro', id FROM categorias_plano_contas WHERE codigo = '1';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Snacks', id FROM categorias_plano_contas WHERE codigo = '1';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Aluguel de Espaço para Eventos', id FROM categorias_plano_contas WHERE codigo = '1';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Cashback', id FROM categorias_plano_contas WHERE codigo = '1';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Inscrição em Evento', id FROM categorias_plano_contas WHERE codigo = '1';

-- =========================
-- PESSOAL
-- =========================
INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Salário', id FROM categorias_plano_contas WHERE codigo = '2.1';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Vale Transporte', id FROM categorias_plano_contas WHERE codigo = '2.1';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Vale Alimentação', id FROM categorias_plano_contas WHERE codigo = '2.1';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Diarista', id FROM categorias_plano_contas WHERE codigo = '2.1';

-- =========================
-- MATERIAIS
-- =========================
INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Material de Escritório', id FROM categorias_plano_contas WHERE codigo = '2.2';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Material de Limpeza', id FROM categorias_plano_contas WHERE codigo = '2.2';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Material Pedagógico', id FROM categorias_plano_contas WHERE codigo = '2.2';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Impressões', id FROM categorias_plano_contas WHERE codigo = '2.2';

-- =========================
-- SERVIÇOS
-- =========================
INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Contabilidade', id FROM categorias_plano_contas WHERE codigo = '2.3';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Software', id FROM categorias_plano_contas WHERE codigo = '2.3';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Transporte', id FROM categorias_plano_contas WHERE codigo = '2.3';

-- =========================
-- UTILIDADES
-- =========================
INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Energia Elétrica', id FROM categorias_plano_contas WHERE codigo = '2.4';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Internet', id FROM categorias_plano_contas WHERE codigo = '2.4';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Água', id FROM categorias_plano_contas WHERE codigo = '2.4';

-- =========================
-- FINANCEIRO ENTRADAS
-- =========================

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Devolução', id FROM categorias_plano_contas WHERE codigo = '5.1';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Estorno', id FROM categorias_plano_contas WHERE codigo = '5.1';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Reembolso / Devolução', id FROM categorias_plano_contas WHERE codigo = '5.1';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Repasse', id FROM categorias_plano_contas WHERE codigo = '5.1';

-- =========================
-- FINANCEIRO SAÍDAS
-- =========================

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Devolução', id FROM categorias_plano_contas WHERE codigo = '5.2';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Estorno', id FROM categorias_plano_contas WHERE codigo = '5.2';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Reembolso / Devolução', id FROM categorias_plano_contas WHERE codigo = '5.2';

INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Repasse', id FROM categorias_plano_contas WHERE codigo = '5.2';

-- =========================
-- TRANSFERÊNCIAS
-- =========================
INSERT INTO plano_contas (nome, categoria_id)
SELECT 'Transferência entre contas', id FROM categorias_plano_contas WHERE codigo = '6';