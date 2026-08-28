"""
Camada de dados.

Responsavel por tudo relacionado a existencia fisica do banco: caminho do
arquivo .db, criacao das tabelas e dados iniciais. Nenhuma outra camada
deveria abrir conexao sqlite3 diretamente com o schema/caminho -- so essa.

Arquivo mantido identico ao original: ja estava bem encapsulado.
"""

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "lojas.db")
_SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS produtos (
                produto TEXT,
                departamento TEXT,
                id INT,
                data_fabri DATE,
                data_venc DATE,
                custos FLOAT,
                fornecedor TEXT
            )"""

def db_path():
  return DB_PATH

def create_db():
  conn = sqlite3.connect(DB_PATH)
  c = conn.cursor()
  c.execute(_SCHEMA_SQL)
  c.executemany("INSERT INTO produtos VALUES (?, ?, ?, ?, ?, ?, ?)", [
    ("sabonete", "higiene", 123, "2026-04-21", "2027-08-21", 23.50, "john"),
    ("agua", "bebidas", 234, "2026-04-22", "2029-08-22", 3.50, "lennon"),
    ("coca", "bebidas", 123, "2026-05-03", "2027-04-12", 7.00, "WOAH")
  ])
  conn.commit()
  conn.close()

def create_in_memory_validation_db():
  #cria uma copia da estrutura do banco real (sem os dados) dentro de um Sqlite ':memory'
  #usada só pra testar  se o sql gerado pelo LLM é executável, sem tocar no banco de verdade
  conn = sqlite3.connect(":memory:")
  conn.execute(_SCHEMA_SQL)
  conn.commit()
  return conn