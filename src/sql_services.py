"""
Camada de servico (orquestracao).

Este modulo nao gera SQL sozinho (isso e' o dominio) e nao sabe como o
banco e' criado por dentro (isso e' dados). Ele so orquestra o fluxo:
pergunta -> gera SQL (dominio) -> executa SQL (dados) -> resultado.

E' a antiga funcao generate() de bot_services.py, agora sem a definicao
da classe geradora misturada no mesmo arquivo.
"""

import sqlite3

import db_services
from text_to_sql import ReliableSQLGenerator


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

    if not result["success"]:
        print(f"[erro na geracao/validacao] {result['error']}")
        return {"success": False, "error": result["error"], "results": None}

    try:
        conn = sqlite3.connect(db_services.db_path())
        results = conn.execute(result["sql_query"]).fetchall()
        conn.close()
    except sqlite3.Error as e:
        print(f"[erro ao executar no banco real] {e}")
        return {"success": False, "error": f"Erro ao executar: {e}", "results": None}

    return {"success": True, "error": None, "results": results}