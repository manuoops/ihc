import dspy
import telebot 
import json
import bot_services
import db_services
import token_return
import sqlite3


lm = dspy.LM('openai/gemma-4-E2B-it-IQ4_XS', api_base='http://localhost:1337/v1', api_key='not-needed')
dspy.configure(lm=lm)

question = "qual o departamento do sabonete?"

db_services.create_db()
conn = sqlite3.connect(db_services.db_path())
results = conn.execute("SELECT * from produtos").fetchall()
print(results)
bot_services.generate(question)

bot = telebot.TeleBot(token_return.return_token())

@bot.message_handler(func=lambda message: True)
def reply_hi(message):
  result = bot_services.generate(message.text)
  bot.reply_to(message, json.dumps(result))

bot.polling()