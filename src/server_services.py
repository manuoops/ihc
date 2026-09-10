import os
import sqlite3

import dspy
from fastapi import FastAPI


def configure_llm():
    lm = dspy.LM(
        'openai/gemma-4-E2B-it-IQ4_XS',
        api_base='http://localhost:1337/v1',
        api_key='not-needed',
    )
    dspy.configure(lm=lm)


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


class TextToSQL(dspy.Signature):
    """Generate SQL from natural language.

        Database schema:
          - produtos: produto, departamento, id, data_fabri, data_venc, custos, fornecedor
    """
    dbschema = dspy.InputField(desc="Databases schema")
    question = dspy.InputField(desc="Natural language question")

    sql_query = dspy.OutputField(desc="Valid SQL query")


class ReliableSQLGenerator(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_sql = dspy.ChainOfThought(TextToSQL)

    def forward(self, schema, question):
        try:
            pred = self.generate_sql(schema = schema, question = question)
        except Exception as e:
            return {"success": False, "sql_query": None, "error": f"Erro ao gerar SQL: {e}"}

        sql_query = pred.sql_query

        #valida o SQL gerado num banco em memoria (e não no banco real)
        try:
            validation_conn = create_in_memory_validation_db()
            validation_conn.execute(sql_query)
            validation_conn.close()
        except sqlite3.Error as e:
            return {"success": False, "sql_query": sql_query, "error": f"SQL invalido: {e}"}

        return {"success": True, "sql_query": sql_query, "error": None}


def generate(question):
    schema = """
    CREATE TABLE produtos (
      produto VARCHAR(50),
      departamento VARCHAR(50),
      id INTEGER,
      data_fabri DATE,
      data_venc DATE,
      custos FLOAT,
      fornecedor VARCHAR(50)
    );
    """

    generator = ReliableSQLGenerator()
    result = generator.forward(schema, question)

    print(result["sql_query"])

    if not result["success"]:
        print(f"[erro na geracao/validacao] {result['error']}")
        return {"success": False, "error": result["error"], "results": None}

    if "SELECT" in result["sql_query"]:
        try:
            conn = sqlite3.connect(db_path())
            results = conn.execute(result["sql_query"]).fetchall()
            conn.close()
        except sqlite3.Error as e:
            print(f"[erro ao executar no banco real] {e}")
            return {
                "success": False,
                "error": f"Erro ao executar: {e}",
                "results": None
            }
    else:
        print("Erro. Nao pode")
        return {
            "success": False,
            "error": "A consulta gerada não é um SELECT.",
            "results": None
        }

    if not results:
        return {
            "success": False,
            "error": "Nenhum produto encontrado.",
            "results": []
        }

    return {
        "success": True,
        "error": None,
        "results": results
    }


app = FastAPI()

configure_llm()
create_db()


@app.get("/query")
def query_stock(question: str):
    return generate(question)
