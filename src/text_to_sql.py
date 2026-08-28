import dspy
import db_services
import sqlite3

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
            validation_conn = db_services.create_in_memory_validation_db()
            validation_conn.execute(sql_query)
            validation_conn.close()
        except sqlite3.Error as e:
            return {"success": False, "sql_query": sql_query, "error": f"SQL invalido: {e}"}

        return {"success": True, "sql_query": sql_query, "error": None}