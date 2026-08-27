"""
Camada de interface (apresentacao).

Tudo que depende do Telegram vive aqui: criar o bot e registrar o handler
de mensagem. Essa camada so conhece a camada de servico (sql_service) --
ela nao sabe como o SQL e' gerado nem como o banco e' acessado por dentro.

Movido de dentro de main.py sem alteracoes na logica.
"""

import json

import telebot

import sql_services


def build_bot(token):
    bot = telebot.TeleBot(token)

    @bot.message_handler(func=lambda message: True)
    def reply_hi(message):
        result = sql_services.generate(message.text)
        bot.reply_to(message, json.dumps(result))

    return bot