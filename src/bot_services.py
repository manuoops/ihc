import json
import os
import re
import sqlite3

import dspy
import telebot


def configure_llm():
    lm = dspy.LM('openai/gemma-4-E2B-it-IQ4_XS', api_base='http://localhost:1337/v1', api_key='not-needed')
    dspy.configure(lm=lm)
    return lm


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "lojas.db")
_SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS produtos (
                produto TEXT, departamento TEXT, id INT, data_fabri DATE,
                data_venc DATE, custos FLOAT, fornecedor TEXT)"""
SCHEMA = """CREATE TABLE produtos (
  produto VARCHAR(50), departamento VARCHAR(50), id INTEGER, data_fabri DATE,
  data_venc DATE, custos FLOAT, fornecedor VARCHAR(50));"""
_INITIAL_PRODUCTS = [
  ("sabonete", "higiene", 123, "2026-04-21", "2027-08-21", 23.50, "john"),
  ("agua", "bebidas", 234, "2026-04-22", "2029-08-22", 3.50, "lennon"),
  ("coca", "bebidas", 123, "2026-05-03", "2027-04-12", 7.00, "WOAH")
]
OPTIMIZED_MODEL_PATH = os.path.join(BASE_DIR, "sql_generator_optimized.json")


def db_path():
  return DB_PATH


def create_db():
  conn = sqlite3.connect(DB_PATH)
  c = conn.cursor()
  c.execute(_SCHEMA_SQL)
  c.executemany("INSERT INTO produtos VALUES (?, ?, ?, ?, ?, ?, ?)", _INITIAL_PRODUCTS)
  conn.commit()
  conn.close()


def create_in_memory_validation_db():
  conn = sqlite3.connect(":memory:")
  conn.execute(_SCHEMA_SQL)
  conn.commit()
  return conn


class TextToSQL(dspy.Signature):
    """Generate a valid SQLite SELECT query from natural language."""
    dbschema = dspy.InputField(desc="Databases schema")
    question = dspy.InputField(desc="Natural language question")
    sql_query = dspy.OutputField(desc="Valid SQL query starting with SELECT")


class ReliableSQLGenerator(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_sql = dspy.ChainOfThought(TextToSQL)

    def forward(self, schema, question):
        return self.generate_sql(dbschema=schema, question=question)


def sanitize_sql(raw_sql):
    return re.sub(r"```sql|```", "", raw_sql, flags=re.IGNORECASE).strip()


def validate_sql(sql_query):
    if not sql_query.upper().startswith("SELECT"):
        return False, "Operação negada: apenas consultas SELECT são permitidas."
    try:
        validation_conn = create_in_memory_validation_db()
        validation_conn.execute(sql_query)
        validation_conn.close()
        return True, None
    except sqlite3.Error as error:
        return False, f"SQL inválido: {error}"


def generate(question):
    try:
        prediction = generator(schema=SCHEMA, question=question)
        sql_query = sanitize_sql(prediction.sql_query)
    except Exception as error:
        return {"success": False, "error": f"Erro ao gerar SQL: {error}", "results": None}
    print(sql_query)
    is_valid, error = validate_sql(sql_query)
    if not is_valid:
        return {"success": False, "error": error, "results": None}
    try:
        conn = sqlite3.connect(db_path())
        results = conn.execute(sql_query).fetchall()
        conn.close()
    except sqlite3.Error as error:
        return {"success": False, "error": f"Erro ao executar: {error}", "results": None}
    if not results:
        return {"success": False, "error": "Nenhum produto encontrado.", "results": []}
    return {"success": True, "error": None, "results": results}


trainset = [
    dspy.Example(schema=SCHEMA, question="Qual o departamento do sabonete?", sql_query="SELECT departamento FROM produtos WHERE produto = 'sabonete';").with_inputs("schema", "question"),
    dspy.Example(schema=SCHEMA, question="Quais bebidas temos no estoque?", sql_query="SELECT * FROM produtos WHERE departamento = 'bebidas';").with_inputs("schema", "question"),
    dspy.Example(schema=SCHEMA, question="Qual é o produto mais caro?", sql_query="SELECT produto, custos FROM produtos ORDER BY custos DESC LIMIT 1;").with_inputs("schema", "question"),
    dspy.Example(schema=SCHEMA, question="Quais produtos vencem em 2027?", sql_query="SELECT * FROM produtos WHERE data_venc LIKE '2027%';").with_inputs("schema", "question"),
    dspy.Example(schema=SCHEMA, question="Quantos produtos de higiene existem?", sql_query="SELECT COUNT(*) AS total FROM produtos WHERE departamento = 'higiene';").with_inputs("schema", "question"),
]


def sql_execution_metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    pred_sql = sanitize_sql(getattr(pred, "sql_query", ""))
    if not pred_sql.upper().startswith("SELECT"):
        return dspy.Prediction(score=0.0, feedback="A query deve começar obrigatoriamente com SELECT.")
    conn = sqlite3.connect(":memory:")
    conn.execute(_SCHEMA_SQL)
    conn.executemany("INSERT INTO produtos VALUES (?, ?, ?, ?, ?, ?, ?)", _INITIAL_PRODUCTS)
    try:
        gold_results = conn.execute(gold.sql_query).fetchall()
        pred_results = conn.execute(pred_sql).fetchall()
    except sqlite3.Error as error:
        return dspy.Prediction(score=0.0, feedback=f"Erro de sintaxe SQLite ao executar a query '{pred_sql}': {error}")
    finally:
        conn.close()
    if gold_results == pred_results:
        return dspy.Prediction(score=1.0, feedback="SQL executado com sucesso e os dados retornados estão corretos.")
    return dspy.Prediction(score=0.0, feedback=f"Resultados diferentes. Esperado: {gold_results}; recebido: {pred_results}.")


def train_gepa():
    teleprompter = dspy.GEPA(metric=sql_execution_metric, reflection_lm=lm, auto="light")
    optimized_program = teleprompter.compile(student=ReliableSQLGenerator(), trainset=trainset)
    optimized_program.save(OPTIMIZED_MODEL_PATH)
    return OPTIMIZED_MODEL_PATH


def build_bot(token):
    bot = telebot.TeleBot(token)

    @bot.message_handler(func=lambda message: True)
    def reply_hi(message):
        bot.reply_to(message, json.dumps(generate(message.text)))

    return bot


def return_token():
    return os.environ["TELEGRAM_BOT_TOKEN"]


lm = configure_llm()
generator = ReliableSQLGenerator()
if os.path.exists(OPTIMIZED_MODEL_PATH):
    generator.load(OPTIMIZED_MODEL_PATH)
    print("Modelo DSPy otimizado com GEPA carregado com sucesso.")
create_db()


if __name__ == "__main__":
    bot = build_bot(return_token())
    bot.polling()
