import json
import sqlite3

import telebot

import server_services


def build_bot(token):
    bot = telebot.TeleBot(token)

    @bot.message_handler(func=lambda message: True)
    def reply_hi(message):
        result = server_services.generate(message.text)
        bot.reply_to(message, json.dumps(result))

    return bot


def return_token():
    return '8907184614:AAFnacPSofvc7YeiBhgO8I34JAiajOF3wgw' # token aqui


server_services.configure_llm()

server_services.create_db()
conn = sqlite3.connect(server_services.db_path())
results = conn.execute("SELECT * from produtos").fetchall()
print(results)

server_services.generate("qual o departamento do sabonete?")

bot = build_bot(return_token())
bot.polling()
