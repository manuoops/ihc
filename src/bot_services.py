import json
import os
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

import telebot
import whisper
import server_services


def _transcribe_voice(bot, message):
    configured_url = os.getenv(
        "VOICE_TRANSCRIPTION_URL",
        "http://localhost:1337/v1/audio/transcriptions",
    )
    model = os.getenv("VOICE_TRANSCRIPTION_MODEL", "whisper-1")
    file_info = bot.get_file(message.voice.file_id)
    audio = bot.download_file(file_info.file_path)
    boundary = uuid.uuid4().hex
    filename = Path(file_info.file_path).name or "voice.ogg"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="model"\r\n\r\n{model}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: audio/ogg\r\n\r\n"
    ).encode("utf-8") + audio + f"\r\n--{boundary}--\r\n".encode("utf-8")
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    api_key = os.getenv("VOICE_TRANSCRIPTION_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(
        configured_url,
        data=body,
        headers=headers,
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    transcript = payload.get("text", "").strip()
    if not transcript:
        raise ValueError("A transcrição não retornou texto.")
    return transcript


def _format_result(result):
    if not result.get("success"):
        return result.get("error", "Não consegui consultar o estoque.")
    rows = result.get("results", [])
    return "\n".join(" • ".join(str(value) for value in row.values()) for row in rows)


def build_bot(token):
    bot = telebot.TeleBot(token)

    @bot.message_handler(content_types=["text", "voice"])
    def reply_to_question(message):
        try:
            question = message.text.strip() if message.text else ""
            if message.voice:
                question = _transcribe_voice(bot, message)
            if not question:
                bot.reply_to(message, "Envie uma pergunta por texto ou voz.")
                return
            result = server_services.generate(question)
            bot.reply_to(message, _format_result(result)[:4000])
        except Exception:
            bot.reply_to(message, "Não foi possível processar sua mensagem. Tente novamente.")

    return bot


def main():
    server_services.load_env_file()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Defina TELEGRAM_BOT_TOKEN no arquivo .env.")
    server_services.initialize_services()
    build_bot(token).infinity_polling()


if __name__ == "__main__":
    main()
