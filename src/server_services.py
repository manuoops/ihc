from fastapi import FastAPI

import bot_services


app = FastAPI()


@app.get("/query")
def query_stock(question: str):
    return bot_services.generate(question)
