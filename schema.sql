-- Devolve Aki - Cérebro (Central)
-- Estrutura do banco de dados

-- 1. Entregadores (dados sensíveis - tratar com cuidado extra)
CREATE TABLE IF NOT EXISTS entregadores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    endereco TEXT NOT NULL,
    telefone TEXT NOT NULL,
    documento TEXT NOT NULL,       -- CPF/RG
    cnh TEXT NOT NULL,
    placa_moto TEXT NOT NULL,
    conta_repasse TEXT NOT NULL,   -- dados bancários para repasse
    online INTEGER NOT NULL DEFAULT 0,  -- 0 = offline, 1 = online
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 2. Clientes
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    telefone TEXT NOT NULL,
    endereco TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 3. Autenticação (separada dos dados pessoais)
CREATE TABLE IF NOT EXISTS autenticacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL CHECK (tipo IN ('entregador', 'cliente')),
    referencia_id INTEGER NOT NULL,  -- id do entregador ou cliente
    usuario TEXT NOT NULL UNIQUE,    -- telefone ou e-mail
    senha_hash TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 4. Coletas
CREATE TABLE IF NOT EXISTS coletas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    entregador_id INTEGER,  -- vazio até alguém aceitar
    endereco_coleta TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    tamanho_pacote TEXT,
    peso_aproximado REAL,
    embalado_corretamente INTEGER,  -- 0 = não, 1 = sim
    foto_pacote TEXT,               -- caminho/URL da foto
    status TEXT NOT NULL DEFAULT 'aguardando',
    -- status possíveis: aguardando, aceita, a_caminho, cliente_confirmou,
    --                    coletado, entregue, cancelada
    valor_corrida REAL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (cliente_id) REFERENCES clientes(id),
    FOREIGN KEY (entregador_id) REFERENCES entregadores(id)
);

-- 5. Histórico de status (cada mudança vira um registro)
CREATE TABLE IF NOT EXISTS historico_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coleta_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (coleta_id) REFERENCES coletas(id)
);

-- 6. Lacres (adesivos com QR code)
CREATE TABLE IF NOT EXISTS lacres (
    numero_serie TEXT PRIMARY KEY,
    coleta_id INTEGER,
    escaneado_coleta_em TEXT,
    escaneado_coleta_lat REAL,
    escaneado_coleta_lng REAL,
    escaneado_entrega_em TEXT,
    escaneado_entrega_lat REAL,
    escaneado_entrega_lng REAL,
    FOREIGN KEY (coleta_id) REFERENCES coletas(id)
);

-- 7. Posições de GPS
CREATE TABLE IF NOT EXISTS posicoes_gps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entregador_id INTEGER NOT NULL,
    coleta_id INTEGER,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (entregador_id) REFERENCES entregadores(id),
    FOREIGN KEY (coleta_id) REFERENCES coletas(id)
);

-- 8. Pagamentos
CREATE TABLE IF NOT EXISTS pagamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coleta_id INTEGER NOT NULL,
    valor REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente',  -- pendente, pago, cancelado
    forma_pagamento TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (coleta_id) REFERENCES coletas(id)
);
