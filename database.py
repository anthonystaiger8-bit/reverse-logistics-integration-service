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
]


def _migrar_colunas(conn):
    """Adiciona colunas novas em bancos que já existiam antes dessas features."""
    for tabela, coluna, tipo in COLUNAS_NOVAS:
        try:
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
        except sqlite3.OperationalError as erro:
            if "duplicate column name" not in str(erro):
                raise


def init_db():
    """Cria as tabelas caso ainda não existam e migra bancos antigos."""
    conn = get_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    _migrar_colunas(conn)
    conn.commit()
    conn.close()
    print(f"Banco de dados pronto em: {DB_PATH}")


if __name__ == "__main__":
    init_db()
