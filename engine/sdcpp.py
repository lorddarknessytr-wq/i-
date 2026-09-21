"""FLUX.2 klein 4B (GGUF) on CPU through stable-diffusion.cpp: text-to-image and image editing."""
import io
import os
import subprocess

from PIL import Image

WORK = "work"


def _dl(spec, root="models"):
    from huggingface_hub import hf_hub_download
    return hf_hub_download(repo_id=spec["repo"], filename=spec["file"], local_dir=root)


def ensure_models(cfg):
    return _dl(cfg["diffusion"]), _dl(cfg["llm"]), _dl(cfg["vae"])


def out_size(w, h, long_side=512):
    """Output size keeping the input's aspect ratio, multiples of 16."""
    s = long_side / max(w, h)
    return tuple(max(256, int(round(v * s / 16)) * 16) for v in (w, h))


def prep_input(data):
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((512, 512), Image.LANCZOS)
    return im


def generate(cfg, p, input_bytes=None):
    os.makedirs(WORK, exist_ok=True)
    sd_bin = os.environ.get("SD_BIN", "sdcpp-bin/sd-cli")
    diff, llm, vae = ensure_models(cfg)
    out = os.path.join(WORK, "out.png")
    if os.path.exists(out):
        os.remove(out)
    w, h = p["width"], p["height"]
    cmd = [
        sd_bin, "--diffusion-model", diff, "--vae", vae, "--llm", llm,
        "-p", p["prompt_flux"], "--cfg-scale", "1.0", "--sampling-method", "euler",
        "--steps", str(p["steps"]), "-s", str(p["seed"]),
        "--diffusion-fa", "-t", str(os.cpu_count() or 4), "-o", out,
    ]
    if input_bytes:
        ref = prep_input(input_bytes)
        w, h = out_size(*ref.size)
        ref_path = os.path.join(WORK, "ref.png")
        ref.save(ref_path)
        cmd += ["-r", ref_path]
    cmd += ["-W", str(w), "-H", str(h)]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=cfg.get("timeout_min", 100) * 60)
    print((r.stdout or "")[-2000:])
    print((r.stderr or "")[-3000:])
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(f"sd-cli failed with code {r.returncode}")
    return Image.open(out).convert("RGB")
