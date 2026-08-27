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


def db_path():
  return DB_PATH


def create_db():
  conn = sqlite3.connect(DB_PATH)
  c = conn.cursor()

  # Create tables
  c.execute("""CREATE TABLE IF NOT EXISTS produtos (
                nome TEXT, 
                departamento TEXT
            )""")

  c.executemany("INSERT INTO produtos VALUES (?, ?)", [
    ("sabonete", "higiene"),
    ("agua", "bebidas"),
    ("coca", "bebidas"),
  ])

  conn.commit()
  conn.close()