import json
import os
import re

import dspy
import telebot


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OPTIMIZED_MODEL_PATH = os.path.join(BASE_DIR, "sql_generator_optimized.json")
ENV_PATH = os.path.join(os.path.dirname(BASE_DIR), ".env")


def load_env():
    if not os.path.exists(ENV_PATH):
        return

    with open(ENV_PATH, encoding="utf-8") as env_file:
        for line in env_file:
            key, separator, value = line.strip().partition("=")
            if separator and key and not key.startswith("#"):
                os.environ.setdefault(key, value)


def configure_llm():
    lm = dspy.LM(
        "openai/gemma-4-E2B-it-IQ4_XS",
        api_base="http://localhost:1337/v1",
        api_key="not-needed",
    )
    dspy.configure(lm=lm)
    return lm


class TextToSQL(dspy.Signature):
    """Generate a valid SQLite SELECT query from natural language."""

    dbschema = dspy.InputField(desc="Database schema")
    question = dspy.InputField(desc="Natural language question")
    sql_query = dspy.OutputField(desc="Valid SQLite SELECT query")


class ReliableSQLGenerator(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_sql = dspy.ChainOfThought(TextToSQL)

    def forward(self, schema, question):
        return self.generate_sql(dbschema=schema, question=question)


def sanitize_sql(raw_sql):
    return re.sub(r"```sql|```", "", raw_sql, flags=re.IGNORECASE).strip()


def generate_sql(question, schema):
    try:
        prediction = generator(schema=schema, question=question)
        return {"success": True, "sql_query": sanitize_sql(prediction.sql_query), "error": None}
    except Exception as error:
        return {"success": False, "sql_query": None, "error": f"Erro ao gerar SQL: {error}"}


def create_trainset(schema):
    examples = [
        ("Qual o departamento do sabonete?", "SELECT departamento FROM produtos WHERE produto = 'sabonete';"),
        ("Quais bebidas temos no estoque?", "SELECT * FROM produtos WHERE departamento = 'bebidas';"),
        ("Qual é o produto mais caro?", "SELECT produto, custos FROM produtos ORDER BY custos DESC LIMIT 1;"),
        ("Quais produtos vencem em 2027?", "SELECT * FROM produtos WHERE data_venc LIKE '2027%';"),
        ("Quantos produtos de higiene existem?", "SELECT COUNT(*) AS total FROM produtos WHERE departamento = 'higiene';"),
    ]
    return [
        dspy.Example(dbschema=schema, question=question, sql_query=sql_query).with_inputs("dbschema", "question")
        for question, sql_query in examples
    ]


def sql_metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    import server_services

    predicted_sql = sanitize_sql(getattr(pred, "sql_query", ""))
    is_valid, error = server_services.validate_sql(predicted_sql)
    if not is_valid:
        return dspy.Prediction(score=0.0, feedback=error)

    conn = server_services.create_validation_db(include_products=True)
    try:
        expected = conn.execute(gold.sql_query).fetchall()
        received = conn.execute(predicted_sql).fetchall()
    finally:
        conn.close()

    if received == expected:
        return dspy.Prediction(score=1.0, feedback="SQL correto e com o resultado esperado.")
    return dspy.Prediction(score=0.0, feedback=f"Resultado incorreto. Esperado: {expected}; recebido: {received}.")


def train_gepa():
    import server_services

    optimizer = dspy.GEPA(metric=sql_metric, reflection_lm=lm, auto="light")
    optimized_program = optimizer.compile(
        student=ReliableSQLGenerator(),
        trainset=create_trainset(server_services.SCHEMA),
    )
    optimized_program.save(OPTIMIZED_MODEL_PATH)
    return OPTIMIZED_MODEL_PATH


def build_bot(token):
    bot = telebot.TeleBot(token)

    @bot.message_handler(func=lambda message: True)
    def reply_hi(message):
        import server_services
        bot.reply_to(message, json.dumps(server_services.query_database(message.text)))

    return bot


def run():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    build_bot(token).polling()


load_env()
lm = configure_llm()
generator = ReliableSQLGenerator()
if os.path.exists(OPTIMIZED_MODEL_PATH):
    generator.load(OPTIMIZED_MODEL_PATH)


if __name__ == "__main__":
    if "--train" in os.sys.argv:
        print(f"Modelo otimizado salvo em: {train_gepa()}")
    else:
        run()
