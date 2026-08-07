"""
Devolve Aki - Cérebro
Conexão e inicialização do banco de dados SQLite.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "devolve_aki.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection():
    """Abre uma conexão com o banco, retornando linhas como dicionário.

    timeout=10 faz o SQLite esperar até 10s por um lock antes de falhar
    (em vez de estourar "database is locked" na hora). O modo WAL permite
    que leituras (tipo o app do motoboy checando /coletas/disponiveis o
    tempo todo) não fiquem travando escritas (tipo o cliente criando um
    pedido novo) e vice-versa.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db_connection():
    """Abre uma conexão e GARANTE que ela feche no final, com sucesso ou com erro.

    Antes, cada rota fazia manualmente:
        conn = get_connection()
        conn.execute(...)
        conn.commit()
        conn.close()
    O problema: se o `execute` desse erro (por qualquer motivo, até um lock
    passageiro e raro), a exceção pulava direto pro FastAPI e o `commit()`/
    `close()` NUNCA rodavam. A conexão ficava presa, com uma transação aberta
    - e isso segurava o lock do SQLite pra sempre, fazendo a PRÓXIMA escrita
    (de qualquer rota) também falhar, e vazar mais uma conexão presa, num
    efeito cascata que só piorava.

    Com esse "with", o close() (e o rollback quando dá erro) rodam sempre,
    não importa o que aconteça lá dentro - a conexão nunca mais fica presa.

    Uso nas rotas:
        with db_connection() as conn:
            conn.execute(...)
            # sem precisar chamar commit() nem close() manualmente
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Colunas novas que podem faltar em um banco já existente (ex: Railway em
# produção), criado antes dessas features. Cada entrada roda um
# "ALTER TABLE ... ADD COLUMN" que é ignorado se a coluna já existir.
COLUNAS_NOVAS = [
    ("coletas", "rota_geometria", "TEXT"),
    ("coletas", "rota_distancia_km", "REAL"),
    ("coletas", "rota_tempo_estimado_min", "REAL"),
    ("coletas", "rota_calculada_em", "TEXT"),
    ("coletas", "qr_coleta_codigo", "TEXT"),
    ("coletas", "qr_coleta_escaneado_em", "TEXT"),
    ("coletas", "qr_coleta_escaneado_lat", "REAL"),
    ("coletas", "qr_coleta_escaneado_lng", "REAL"),
    # Segunda etapa do trajeto: casa do cliente -> ponto de coleta do ML
    ("coletas", "ponto_coleta_id", "INTEGER"),
    ("coletas", "rota2_geometria", "TEXT"),
    ("coletas", "rota2_distancia_km", "REAL"),
    ("coletas", "rota2_tempo_estimado_min", "REAL"),
    ("coletas", "rota2_calculada_em", "TEXT"),
]

# Endereços de teste que representam os pontos de coleta do Mercado Livre
# (o app ainda não tem uma lista oficial/atualizada, então usamos 4 lugares
# reais de Cosmópolis-SP como se fossem pontos de coleta, pra validar o
# funcionamento da segunda rota). Latitude/longitude ficam NULL aqui e são
# preenchidas automaticamente no startup do cérebro (geocodificação).
PONTOS_COLETA_SEED = [
    ("Moto Táxi Centro", "R. Antônio Carlos Nogueira, 550 - Centro, Cosmópolis - SP, 13150-000"),
    ("Cosmópolis Plaza Shopping", "Av. Saudade, 32 - Chácara Horizonte, Cosmópolis - SP, 13150-000"),
    ("OYO Hotel Cosmópolis", "Avenida da Saudade, 740 - Cosmópolis - SP, 13150-670"),
    ("Supermercado Berton", "Av. Saudade, 1847 - Parque Residencial Rossetti, Cosmópolis - SP, 13154-020"),
]


def _migrar_colunas(conn):
    """Adiciona colunas novas em bancos que já existiam antes dessas features."""
    for tabela, coluna, tipo in COLUNAS_NOVAS:
        try:
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
        except sqlite3.OperationalError as erro:
            if "duplicate column name" not in str(erro):
                raise


CRIAR_TABELA_PONTOS_COLETA = """
CREATE TABLE IF NOT EXISTS pontos_coleta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    endereco TEXT NOT NULL,
    latitude REAL,
    longitude REAL
);
"""


def _semear_pontos_coleta(conn):
    """Insere os endereços de teste na primeira vez que o banco roda (tabela
    vazia). Se alguém já cadastrou/editou pontos de coleta manualmente, não
    mexe em nada - só serve pra não começar sem nenhum ponto cadastrado."""
    total = conn.execute("SELECT COUNT(*) FROM pontos_coleta").fetchone()[0]
    if total == 0:
        conn.executemany(
            "INSERT INTO pontos_coleta (nome, endereco) VALUES (?, ?)",
            PONTOS_COLETA_SEED,
        )


def init_db():
    """Cria as tabelas caso ainda não existam e migra bancos antigos."""
    conn = get_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.executescript(CRIAR_TABELA_PONTOS_COLETA)
    _migrar_colunas(conn)
    _semear_pontos_coleta(conn)
    conn.commit()
    conn.close()
    print(f"Banco de dados pronto em: {DB_PATH}")


if __name__ == "__main__":
    init_db()
