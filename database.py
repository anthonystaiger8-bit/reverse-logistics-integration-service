"""
Devolve Aki - Cérebro
Conexão e inicialização do banco de dados SQLite.
"""
import sqlite3
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
