"""
Camada de servico (orquestracao).

Este modulo nao gera SQL sozinho (isso e' o dominio) e nao sabe como o
banco e' criado por dentro (isso e' dados). Ele so orquestra o fluxo:
pergunta -> gera SQL (dominio) -> executa SQL (dados) -> resultado.

E' a antiga funcao generate() de bot_services.py, agora sem a definicao
da classe geradora misturada no mesmo arquivo.

NOTA: o schema abaixo tem "departmento" (sem o segundo "a"), igual estava
no bot_services.py original. Reparem que db_services.py cria a coluna
como "departamento" (correto). Isso e' uma inconsistencia que ja existia
no codigo original -- vale conferir com calma se ela nao esta atrapalhando
o modelo a gerar o SQL certo, ja que o schema que o LM ve nao bate 100%
com o schema real do banco. 
"""

import sqlite3

import db_services
from text_to_sql import ReliableSQLGenerator


def generate(question):
    schema = """
    CREATE TABLE produtos (
      produto VARCHAR(50),
      departamento VARCHAR(50),
    );
    """
    generator = ReliableSQLGenerator()
    sql = generator.forward(schema, question)
    print(sql)
    conn = sqlite3.connect(db_services.db_path())
    print(sql.sql_query)
    results = conn.execute(sql.sql_query).fetchall()
    return results