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
    lm = dspy.LM('openai/gemma-4-E2B-it-IQ4_XS', api_base='http://localhost:1337/v1', api_key='not-needed')
    dspy.configure(lm=lm)
    return lm


class TextToSQL(dspy.Signature):
    """Generate a valid SQLite SELECT query from natural language."""
    dbschema = dspy.InputField(desc="Database schema")
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


def generate_sql(question, schema):
    try:
        prediction = generator(schema=schema, question=question)
        return {"success": True, "sql_query": sanitize_sql(prediction.sql_query), "error": None}
    except Exception as error:
        return {"success": False, "sql_query": None, "error": f"Erro ao gerar SQL: {error}"}


def create_trainset(schema):
    return [
        dspy.Example(schema=schema, question="Qual o departamento do sabonete?", sql_query="SELECT departamento FROM produtos WHERE produto = 'sabonete';").with_inputs("schema", "question"),
        dspy.Example(schema=schema, question="Quais bebidas temos no estoque?", sql_query="SELECT * FROM produtos WHERE departamento = 'bebidas';").with_inputs("schema", "question"),
        dspy.Example(schema=schema, question="Qual é o produto mais caro?", sql_query="SELECT produto, custos FROM produtos ORDER BY custos DESC LIMIT 1;").with_inputs("schema", "question"),
        dspy.Example(schema=schema, question="Quais produtos vencem em 2027?", sql_query="SELECT * FROM produtos WHERE data_venc LIKE '2027%';").with_inputs("schema", "question"),
        dspy.Example(schema=schema, question="Quantos produtos de higiene existem?", sql_query="SELECT COUNT(*) AS total FROM produtos WHERE departamento = 'higiene';").with_inputs("schema", "question"),
    ]


def sql_metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    predicted_sql = sanitize_sql(getattr(pred, "sql_query", ""))
    if not predicted_sql.upper().startswith("SELECT"):
        return dspy.Prediction(score=0.0, feedback="A query deve começar obrigatoriamente com SELECT.")
    if predicted_sql.upper() == gold.sql_query.upper():
        return dspy.Prediction(score=1.0, feedback="Query SELECT correta.")
    return dspy.Prediction(score=0.0, feedback="A query não corresponde ao resultado esperado.")


def train_gepa(schema):
    optimizer = dspy.GEPA(metric=sql_metric, reflection_lm=lm, auto="light")
    optimized_program = optimizer.compile(student=ReliableSQLGenerator(), trainset=create_trainset(schema))
    optimized_program.save(OPTIMIZED_MODEL_PATH)
    return OPTIMIZED_MODEL_PATH


def build_bot(token):
    bot = telebot.TeleBot(token)

    @bot.message_handler(func=lambda message: True)
    def reply_hi(message):
        import server_services
        bot.reply_to(message, json.dumps(server_services.query_database(message.text)))

    return bot


def return_token():
    return os.environ["TELEGRAM_BOT_TOKEN"]


load_env()
lm = configure_llm()
generator = ReliableSQLGenerator()
if os.path.exists(OPTIMIZED_MODEL_PATH):
    generator.load(OPTIMIZED_MODEL_PATH)
    print("Modelo DSPy otimizado com GEPA carregado com sucesso.")


if __name__ == "__main__":
    bot = build_bot(return_token())
    bot.polling()
