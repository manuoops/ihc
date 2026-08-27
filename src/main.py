import sqlite3
import config
import db_services
import sql_services
import bot_services
import token_return

config.configure_llm()

db_services.create_db()
conn = sqlite3.connect(db_services.db_path())
results = conn.execute("SELECT * from produtos").fetchall()
print(results)

sql_services.generate("qual o departamento do sabonete?")

bot = bot_services.build_bot(token_return.return_token())
bot.polling()