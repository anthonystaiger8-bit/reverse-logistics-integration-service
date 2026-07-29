"""
Devolve Aki - Cérebro
Conexão e inicialização do banco de dados SQLite.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "devolve_aki.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection():
    """Abre uma conexão com o banco, retornando linhas como dicionário."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Cria as tabelas caso ainda não existam."""
    conn = get_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print(f"Banco de dados pronto em: {DB_PATH}")


if __name__ == "__main__":
    init_db()
