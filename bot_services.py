import dspy
import sqlite3
import db_services

class TextToSQL(dspy.Signature):
    """Generate SQL from natural language.

        Database schema:
          - produtos: nome, departamento
    """
    dbschema = dspy.InputField(desc="Databases schema")
    question = dspy.InputField(desc="Natural language question")

    sql_query = dspy.OutputField(desc="Valid SQL query")

class ReliableSQLGenerator(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_sql = dspy.ChainOfThought(TextToSQL)

    def forward(self, schema, question):
        pred = self.generate_sql(schema=schema, question=question)
        return pred
    

def generate(question):
    schema = """
    CREATE TABLE produtos (
      nome VARCHAR(50),
      departmento VARCHAR(50),
    );
    """
    generator = ReliableSQLGenerator()
    sql = generator.forward(schema, question)
    print(sql)
    conn = sqlite3.connect(db_services.db_path())
    print(sql.sql_query)
    results = conn.execute(sql.sql_query).fetchall()
    return results