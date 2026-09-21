// Cloudflare Worker: always-on relay between Telegram/Rubika webhooks and GitHub Actions.
// Env vars / secrets:
//   GH_REPO       "owner/repo"
//   GH_TOKEN      fine-grained PAT for that repo (Contents: read+write is enough for repository_dispatch)
//   TG_TOKEN      Telegram bot token            (optional)
//   TG_SECRET     random string, same as setWebhook secret_token (recommended)
//   RUBIKA_TOKEN  Rubika bot token              (optional)
//   ALLOWED_IDS   comma-separated chat ids allowed to use the bot (optional; empty = everyone)
//   KV            KV namespace binding for a 1-request-per-minute limit (optional)

const HELP = `سلام! 👋
توضیح تصویر مورد نظرتون رو بنویسید (فارسی یا انگلیسی).
مثال: یک گربه فضانورد روی ماه، نورپردازی سینمایی

ویرایش تصویر: یک عکس بفرستید و در کپشن بنویسید چه تغییری بدهم.
مثال کپشن: پس‌زمینه را شب کن

گزینه‌های اختیاری (آخر متن):
--style realistic | cinematic | anime | art | 3d | pixel | fantasy
--ratio 1:1 | 3:2 | 2:3 | 16:9 | 9:16
--seed 123   --hd (بزرگ‌تر و شارپ‌تر)

ساخت هر تصویر روی سرور رایگان کند است و ممکن است ۱۰ تا ۳۰ دقیقه طول بکشد.`;

const enc = (o, status = 200) =>
  new Response(JSON.stringify(o), { status, headers: { "content-type": "application/json" } });

async function githubDispatch(env, payload) {
  const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "ai-image-relay",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ event_type: "generate", client_payload: payload }),
  });
  return r.status === 204;
}

async function tgSend(env, chatId, text) {
  await fetch(`https://api.telegram.org/bot${env.TG_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text }),
  });
}

async function rubikaSend(env, chatId, text) {
  await fetch(`https://botapi.rubika.ir/v3/${env.RUBIKA_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text }),
  });
}

async function handle(platform, chatId, text, env, inputImage = "") {
  const reply = (t) => (platform === "telegram" ? tgSend(env, chatId, t) : rubikaSend(env, chatId, t));
  const allowed = (env.ALLOWED_IDS || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (allowed.length && !allowed.includes(String(chatId))) return reply("⛔ دسترسی ندارید.");

  text = (text || "").trim();
  if (/^\/(start|help)\b/i.test(text)) return reply(HELP);
  text = text.replace(/^\/\w+(@\w+)?\s*/, ""); // allow "/img prompt"
  if (!text) return reply(HELP);
  if (text.length > 600) return reply("متن خیلی طولانی است.");

  if (env.KV) {
    const key = `rl:${platform}:${chatId}`;
    if (await env.KV.get(key)) return reply("⏱ لطفاً یک دقیقه بین درخواست‌ها صبر کنید.");
    await env.KV.put(key, "1", { expirationTtl: 60 });
  }

  const ok = await githubDispatch(env, {
    prompt: text,
    input_image: inputImage,
    chat_id: String(chatId),
    platform,
    job_id: crypto.randomUUID().slice(0, 8),
  });
  return reply(ok ? "⏳ در حال ساخت تصویر... (ممکن است ۱۰ تا ۳۰ دقیقه طول بکشد؛ خودم نتیجه را همین‌جا می‌فرستم)" : "❌ ارتباط با سرور ساخت تصویر برقرار نشد.");
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (req.method !== "POST") return new Response("ok");

    if (url.pathname === "/telegram") {
      if (env.TG_SECRET && req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TG_SECRET)
        return new Response("forbidden", { status: 403 });
      const upd = await req.json();
      const msg = upd.message;
      if (msg && msg.photo && msg.photo.length) {
        const best = msg.photo[msg.photo.length - 1]; // largest size
        if (!msg.caption) ctx.waitUntil(tgSend(env, msg.chat.id, "برای ویرایش، در کپشن عکس بنویسید چه تغییری بدهم."));
        else ctx.waitUntil(handle("telegram", msg.chat.id, msg.caption, env, "tg:" + best.file_id));
      } else if (msg && msg.text) {
        ctx.waitUntil(handle("telegram", msg.chat.id, msg.text, env));
      }
      return new Response("ok");
    }

    if (url.pathname === "/rubika") {
      // Rubika payload shape is parsed defensively (verify against the live API).
      const body = await req.json();
      const u = body.update || {};
      const inline = body.inline_message || {};
      const chatId = u.chat_id || inline.chat_id;
      const text = (u.new_message && u.new_message.text) || inline.text;
      if (chatId && text) ctx.waitUntil(handle("rubika", chatId, text, env));
      return enc({ ok: true });
    }

    return new Response("not found", { status: 404 });
  },
};
