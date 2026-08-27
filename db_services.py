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
                produto TEXT, 
                departamento TEXT,
                id INT,
                data_fabri DATE,
                data_venc DATE,
                custos FLOAT,
                fornecedor TEXT
            )""")

  c.executemany("INSERT INTO produtos VALUES (?, ?, ?, ?, ?, ?, ?)", [
    ("sabonete", "higiene", 123, "2026-04-21", "2027-08-21", 23.50, "john"),
    ("agua", "bebidas", 234, "2026-04-22", "2029-08-22", 3.50, "lennon"),
    ("coca", "bebidas", 123, "2026-05-03", "2027-04-12", 7.00, "WOAH")
  ])

  conn.commit()
  conn.close()

