"""Prompt handling: inline flags, Persian detection + translation, glossary, styles, safety."""
import random
import re

PERSIAN_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
FLAG_RE = re.compile(
    r"(?:^|\s)--(style|ratio|seed|steps|hd)\b(?:[=\s]+([^\s-]\S*))?", re.I)

RATIOS = {  # ~0.26 megapixel (CPU speed), multiples of 64
    "1:1": (512, 512), "3:2": (640, 448), "2:3": (448, 640),
    "4:3": (576, 448), "3:4": (448, 576), "16:9": (704, 384), "9:16": (384, 704),
}

STYLES_FLUX = {  # natural-language suffixes (FLUX models)
    "auto": "",
    "realistic": "Photorealistic, natural lighting, sharp focus, shot on an 85mm lens, professional photography.",
    "cinematic": "Cinematic still, dramatic lighting, anamorphic lens, film grain, rich color grading.",
    "anime": "Anime style illustration, clean lineart, vibrant colors, key visual quality.",
    "art": "Detailed digital painting, concept art, intricate details.",
    "3d": "High-quality 3D render, soft studio lighting, Pixar-like style.",
    "pixel": "Pixel art, voxel style, blocky Minecraft-like look, isometric, vibrant colors.",
    "fantasy": "Epic fantasy art, magical atmosphere, dramatic lighting, intricate details.",
}

# Persian terms that translation models get wrong; replaced by precise English descriptions.
GLOSSARY = {
    "پرچم ایران": "the flag of Iran: three equal horizontal stripes, green on top, white in the middle, "
                  "red at the bottom, with a small red emblem in the center of the white stripe",
    "برج آزادی": "Azadi Tower in Tehran, a white marble monument with a large central arch",
    "برج میلاد": "Milad Tower in Tehran, a tall concrete telecommunications tower",
    "تخت جمشید": "Persepolis, the ancient Achaemenid ruins with tall carved stone columns",
    "قله دماوند": "Mount Damavand, a snow-capped conical volcano",
    "دماوند": "Mount Damavand, a snow-capped conical volcano",
    "مسجد شیخ لطف‌الله": "Sheikh Lotfollah Mosque in Isfahan with its cream-colored tiled dome",
    "فرش ایرانی": "an intricate Persian carpet with detailed floral medallion patterns",
    "گربه ایرانی": "a Persian cat with long fluffy fur and a flat face",
}

BLOCK_EN = re.compile(
    r"\b(nude|naked|nsfw|porn\w*|sex\w*|erotic\w*|topless|genital\w*|nipple\w*|hentai|lolicon|gore)\b", re.I)
BLOCK_FA = re.compile(r"(برهنه|لخت|سکس|پورن|شهوانی|عریان)")


class UserError(Exception):
    """Error whose message is safe to show to the end user (Persian)."""


def norm_fa(text):
    text = text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", "\u200c")
    return text


def parse_flags(text):
    opts = {}

    def repl(m):
        key, val = m.group(1).lower(), m.group(2)
        if key == "hd":
            opts["hd"] = True
            return " " + (val or "")
        if val:
            opts[key] = val.translate(DIGITS)
        return " "

    clean = FLAG_RE.sub(repl, text)
    return re.sub(r"\s+", " ", clean).strip(), opts


def is_blocked(text):
    return bool(BLOCK_EN.search(text) or BLOCK_FA.search(text))


_tr = None


def translate_fa_en(text, model_name):
    """Translate Persian to English with NLLB, phrase by phrase (better for prompts)."""
    global _tr
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    if _tr is None:
        tok = AutoTokenizer.from_pretrained(model_name, src_lang="pes_Arab")
        mdl = AutoModelForSeq2SeqLM.from_pretrained(model_name).eval()
        _tr = (tok, mdl)
    tok, mdl = _tr
    parts = [p.strip() for p in re.split(r"[\n.!؟?،,;؛]+", text) if p.strip()][:12]
    if not parts:
        return text
    batch = tok(parts, return_tensors="pt", padding=True, truncation=True, max_length=128)
    with torch.inference_mode():
        out = mdl.generate(
            **batch,
            forced_bos_token_id=tok.convert_tokens_to_ids("eng_Latn"),
            num_beams=4, max_new_tokens=96,
        )
    text_en = ", ".join(tok.decode(o, skip_special_tokens=True).strip(" .") for o in out)
    _tr = None  # free ~2.5 GB of RAM before the image model starts
    del tok, mdl, batch, out
    import gc
    gc.collect()
    return text_en


def to_english(text, cfg):
    if not PERSIAN_RE.search(text):
        return text
    rest = norm_fa(text)
    extras = []
    for key, val in GLOSSARY.items():
        k = norm_fa(key)
        if k in rest:
            rest = rest.replace(k, " ")
            extras.append(val)
    rest = re.sub(r"\s+", " ", rest).strip()
    en_rest = translate_fa_en(rest, cfg["translator"]) if PERSIAN_RE.search(rest) else rest
    return ", ".join([x for x in extras + [en_rest] if x])


def build(raw, cfg, edit=False):
    text, opts = parse_flags(raw)
    if not text:
        raise UserError("لطفاً توضیح تصویر را بنویسید.")
    if len(text) > cfg.get("max_prompt_chars", 500):
        raise UserError("متن خیلی طولانی است؛ کوتاه‌ترش کنید.")
    if is_blocked(text):
        raise UserError("این درخواست پشتیبانی نمی‌شود.")

    en = to_english(text, cfg)
    if is_blocked(en):
        raise UserError("این درخواست پشتیبانی نمی‌شود.")

    style = opts.get("style", "auto").lower()
    if style not in STYLES_FLUX:
        style = "auto"
    width, height = RATIOS.get(opts.get("ratio", "1:1"), RATIOS["1:1"])

    try:
        seed = int(opts["seed"]) if "seed" in opts else random.randint(0, 2**31 - 1)
    except ValueError:
        seed = random.randint(0, 2**31 - 1)
    try:
        steps = max(2, min(8, int(opts.get("steps", cfg.get("steps", 4)))))
    except ValueError:
        steps = cfg.get("steps", 4)

    suffix = "" if edit else STYLES_FLUX[style]
    return {
        "prompt_en": en,
        "prompt_flux": en + (". " + suffix if suffix else ""),
        "style": style, "width": width, "height": height,
        "seed": seed, "steps": steps, "hd": bool(opts.get("hd")),
    }
