from fastapi import FastAPI

import config
import db_services
import sql_services

app = FastAPI()

config.configure_llm()
db_services.create_db()


@app.get("/query")
def query_stock(question: str):
    return sql_services.generate(question)
