"""Entry point used by GitHub Actions: python -m engine.run"""
import json
import os
import re
import sys
import time
import traceback

import requests

from engine import deliver, post, sdcpp
from engine.prompt import UserError, build


def write_meta(job_id, meta):
    os.makedirs("out", exist_ok=True)
    with open(f"out/{job_id}.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)


def load_input(spec):
    """INPUT_IMAGE is 'gh:inputs/<file>' (web app) or 'tg:<file_id>' (Telegram)."""
    if spec.startswith("tg:"):
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            raise UserError("توکن تلگرام تنظیم نشده است.")
        return deliver.tg_download(token, spec[3:])
    if spec.startswith("gh:"):
        path = spec[3:]
        if not re.fullmatch(r"inputs/[A-Za-z0-9._-]+", path):
            raise UserError("مسیر تصویر نامعتبر است.")
        r = requests.get(
            f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/contents/{path}?ref=results",
            headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                     "Accept": "application/vnd.github.raw+json"}, timeout=60)
        if r.status_code != 200:
            raise UserError("تصویر ورودی پیدا نشد.")
        return r.content
    raise UserError("منبع تصویر ورودی پشتیبانی نمی‌شود.")


def main():
    cfg = json.load(open("config.json", encoding="utf-8"))
    raw = os.environ.get("PROMPT", "").strip()
    job_id = os.environ.get("JOB_ID") or time.strftime("%Y%m%d%H%M%S")
    platform = os.environ.get("PLATFORM", "web")
    chat_id = os.environ.get("CHAT_ID", "")
    input_spec = os.environ.get("INPUT_IMAGE", "").strip()
    t0 = time.time()
    meta = {"job_id": job_id, "status": "error", "message": "خطای داخلی"}
    os.makedirs("out", exist_ok=True)

    try:
        input_bytes = load_input(input_spec) if input_spec else None
        p = build(raw, cfg, edit=bool(input_bytes))
        img = sdcpp.generate(cfg, p, input_bytes)
        used = "klein4b"
        if p["hd"]:
            img = post.upscale(img)
        path = f"out/{job_id}.jpg"
        img.convert("RGB").save(path, "JPEG", quality=95, optimize=True)
        meta = {
            "job_id": job_id, "status": "done", "prompt_en": p["prompt_en"], "style": p["style"],
            "model": used, "edit": bool(input_bytes), "seed": p["seed"],
            "width": img.width, "height": img.height, "seconds": round(time.time() - t0, 1),
        }
        caption = f"🎨 {used} • {p['style']} • seed {p['seed']}\n{p['prompt_en'][:300]}"
        try:
            deliver.send_image(platform, chat_id, path, caption, also_document=p["hd"])
        except Exception:
            traceback.print_exc()
    except UserError as e:
        meta = {"job_id": job_id, "status": "error", "message": str(e)}
        deliver.send_text(platform, chat_id, "⚠️ " + str(e))
    except Exception:
        traceback.print_exc()
        deliver.send_text(platform, chat_id, "⚠️ ساخت تصویر ناموفق بود. دوباره تلاش کنید.")
        write_meta(job_id, meta)
        sys.exit(1)
    write_meta(job_id, meta)


if __name__ == "__main__":
    main()
