"""Send results back to the user: Telegram / Rubika."""
import os

import requests


# ---------- Telegram ----------
def tg_text(token, chat_id, text):
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                  json={"chat_id": chat_id, "text": text}, timeout=30)


def tg_photo(token, chat_id, path, caption, as_document=False):
    method, field = ("sendDocument", "document") if as_document else ("sendPhoto", "photo")
    with open(path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}",
                          data={"chat_id": chat_id, "caption": caption[:1000]},
                          files={field: f}, timeout=120)
    r.raise_for_status()


def tg_download(token, file_id):
    r = requests.get(f"https://api.telegram.org/bot{token}/getFile", params={"file_id": file_id}, timeout=30)
    r.raise_for_status()
    path = r.json()["result"]["file_path"]
    f = requests.get(f"https://api.telegram.org/file/bot{token}/{path}", timeout=60)
    f.raise_for_status()
    return f.content


# ---------- Rubika (Bot API v3) ----------
def _rb(token, method, payload):
    r = requests.post(f"https://botapi.rubika.ir/v3/{token}/{method}", json=payload, timeout=60)
    r.raise_for_status()
    return r.json()


def rubika_text(token, chat_id, text):
    _rb(token, "sendMessage", {"chat_id": chat_id, "text": text})


def rubika_photo(token, chat_id, path, caption):
    up = _rb(token, "requestSendFile", {"type": "Image"})
    url = up["data"]["upload_url"]
    with open(path, "rb") as f:
        r = requests.post(url, files={"file": (os.path.basename(path), f, "image/jpeg")}, timeout=120)
    r.raise_for_status()
    file_id = r.json()["data"]["file_id"]
    _rb(token, "sendFile", {"chat_id": chat_id, "file_id": file_id, "text": caption})


# ---------- unified ----------
def send_text(platform, chat_id, text):
    if not chat_id:
        return
    if platform == "telegram" and os.environ.get("TELEGRAM_BOT_TOKEN"):
        tg_text(os.environ["TELEGRAM_BOT_TOKEN"], chat_id, text)
    elif platform == "rubika" and os.environ.get("RUBIKA_BOT_TOKEN"):
        rubika_text(os.environ["RUBIKA_BOT_TOKEN"], chat_id, text)


def send_image(platform, chat_id, path, caption, also_document=False):
    if not chat_id:
        return
    if platform == "telegram" and os.environ.get("TELEGRAM_BOT_TOKEN"):
        t = os.environ["TELEGRAM_BOT_TOKEN"]
        tg_photo(t, chat_id, path, caption)
        if also_document:
            tg_photo(t, chat_id, path, "فایل اصلی", as_document=True)
    elif platform == "rubika" and os.environ.get("RUBIKA_BOT_TOKEN"):
        rubika_photo(os.environ["RUBIKA_BOT_TOKEN"], chat_id, path, caption)
