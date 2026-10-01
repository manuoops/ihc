import os
import sqlite3

from fastapi import FastAPI


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "lojas.db")
SCHEMA = """CREATE TABLE produtos (
  produto VARCHAR(50), departamento VARCHAR(50), id INTEGER, data_fabri DATE,
  data_venc DATE, custos FLOAT, fornecedor VARCHAR(50)
);"""
_SCHEMA_SQL = SCHEMA.replace("CREATE TABLE produtos", "CREATE TABLE IF NOT EXISTS produtos")
_INITIAL_PRODUCTS = [
    ("sabonete", "higiene", 123, "2026-04-21", "2027-08-21", 23.50, "john"),
    ("agua", "bebidas", 234, "2026-04-22", "2029-08-22", 3.50, "lennon"),
    ("coca", "bebidas", 123, "2026-05-03", "2027-04-12", 7.00, "WOAH"),
]


def create_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_SCHEMA_SQL)
        if conn.execute("SELECT COUNT(*) FROM produtos").fetchone()[0] == 0:
            conn.executemany("INSERT INTO produtos VALUES (?, ?, ?, ?, ?, ?, ?)", _INITIAL_PRODUCTS)
        conn.commit()
    finally:
        conn.close()


def create_validation_db(include_products=False):
    conn = sqlite3.connect(":memory:")
    conn.execute(_SCHEMA_SQL)
    if include_products:
        conn.executemany("INSERT INTO produtos VALUES (?, ?, ?, ?, ?, ?, ?)", _INITIAL_PRODUCTS)
        conn.commit()
    return conn


def validate_sql(sql_query):
    sql_query = sql_query.strip()
    if not sql_query.upper().startswith("SELECT"):
        return False, "Operação negada: apenas consultas SELECT são permitidas."

    try:
        conn = create_validation_db()
        conn.execute(sql_query)
        conn.close()
        return True, None
    except sqlite3.Error as error:
        return False, f"SQL inválido: {error}"


def execute_sql(sql_query):
    try:
        conn = sqlite3.connect(DB_PATH)
        results = conn.execute(sql_query).fetchall()
        conn.close()
        return {"success": True, "error": None, "results": results}
    except sqlite3.Error as error:
        return {"success": False, "error": f"Erro ao executar: {error}", "results": None}


def query_database(question):
    import bot_services

    generated = bot_services.generate_sql(question, SCHEMA)
    if not generated["success"]:
        return {"success": False, "error": generated["error"], "results": None}

    is_valid, error = validate_sql(generated["sql_query"])
    if not is_valid:
        return {"success": False, "error": error, "results": None}

    execution = execute_sql(generated["sql_query"])
    if not execution["success"]:
        return execution

    results = execution["results"]

    if not results:
        return {"success": False, "error": "Nenhum produto encontrado.", "results": []}
    return {"success": True, "error": None, "results": results}


app = FastAPI()
create_db()


@app.get("/query")
def query_stock(question: str):
    return query_database(question)
