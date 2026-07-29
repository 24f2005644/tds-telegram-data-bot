# bot.py — Data Analyst Telegram Bot (webhook-based, no asyncio)
# Uses Flask + direct Telegram API calls — works on Python 3.12, 3.13, 3.14
import os, json, logging, re, requests
from datetime import datetime
from flask import Flask, request

# ── Config ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
AIPIPE_TOKEN       = os.environ["AIPIPE_TOKEN"]
GITHUB_TOKEN       = os.environ["GITHUB_TOKEN"]
GIST_ID            = os.environ["GIST_ID"]
LOG_URL            = os.environ["LOG_URL"]
# Your Render service URL, e.g. https://tds-data-bot.onrender.com
RENDER_URL         = os.environ.get("RENDER_URL", "").rstrip("/")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
AIPIPE_URL   = "https://aipipe.org/openrouter/v1/chat/completions"
MODEL        = "openai/gpt-4.1-nano"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)

# ── In-memory stores ─────────────────────────────────────────────────────────
run_log: list[dict] = []
user_histories: dict[int, list[dict]] = {}

# ── Helpers ──────────────────────────────────────────────────────────────────
def send_message(chat_id: int, text: str):
    """Send a plain text message back to the user via Telegram API."""
    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
    except Exception as e:
        log.error(f"Failed to send message: {e}")


def append_log(entry: dict):
    """Append one entry to the run log and sync it to the GitHub Gist."""
    run_log.append(entry)
    jsonl_content = "\n".join(json.dumps(e) for e in run_log)
    try:
        requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={"files": {"run.jsonl": {"content": jsonl_content}}},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"Gist update failed: {e}")


def ask_llm(messages: list[dict]) -> str:
    """Call the AIPipe LLM and return the reply text."""
    resp = requests.post(
        AIPIPE_URL,
        headers={
            "Authorization": f"Bearer {AIPIPE_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"model": MODEL, "messages": messages, "temperature": 0},
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def extract_json(text: str) -> str:
    """Pull the first {...} block out of the LLM's reply."""
    # Check for ```json ... ``` fences
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # Fallback: find the outermost { ... }
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return text


SYSTEM_PROMPT = f"""You are a data analyst assistant.
The user will send you a data-analysis question.

IMPORTANT RULES:
1. Reply with ONLY a JSON object — no extra text, no markdown, no explanation.
2. The JSON must contain exactly two keys:
   - "answer": the answer shaped EXACTLY as the question specifies
   - "log_url": "{LOG_URL}"
3. For public datasets (MOSPI and similar), use your training knowledge to answer.
4. If data is embedded in the message, analyse it directly.
5. Match the exact JSON shape the question asks for (e.g. {{"state": "<name>"}}).

Reply with ONLY the JSON object. Nothing else."""


# ── Flask routes ─────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    """Telegram sends every incoming message here as JSON."""
    data = request.get_json(silent=True) or {}

    # Accept both new messages and edited messages
    msg = data.get("message") or data.get("edited_message")
    if not msg or "text" not in msg:
        return "ok", 200

    chat_id   = msg["chat"]["id"]
    user_text = msg["text"].strip()
    log.info(f"[{chat_id}] ← {user_text[:100]}")

    # Build conversation history (handles multi-turn questions)
    history = user_histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    # Call LLM
    try:
        raw_reply = ask_llm(messages)
        log.info(f"[{chat_id}] LLM → {raw_reply[:200]}")
    except requests.exceptions.HTTPError as e:
        body = ""
        try:
            body = e.response.text[:300]
        except Exception:
            pass
        log.error(f"LLM HTTP error: {e} | response body: {body}")
        send_message(chat_id, json.dumps({"answer": f"LLM error: {e} | {body}", "log_url": LOG_URL}))
        return "ok", 200
    except Exception as e:
        log.error(f"LLM error: {e}")
        send_message(chat_id, json.dumps({"answer": f"LLM error: {e}", "log_url": LOG_URL}))
        return "ok", 200

    history.append({"role": "assistant", "content": raw_reply})

    # Extract and validate JSON
    clean_json = extract_json(raw_reply)
    try:
        parsed = json.loads(clean_json)
        if "log_url" not in parsed:
            parsed["log_url"] = LOG_URL
        final_reply = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    except json.JSONDecodeError:
        log.warning("LLM returned invalid JSON — wrapping manually")
        final_reply = json.dumps({"answer": clean_json, "log_url": LOG_URL})

    # Save to run log
    append_log({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "chat_id": chat_id,
        "question": user_text,
        "raw_llm": raw_reply,
        "final_reply": final_reply,
    })

    send_message(chat_id, final_reply)
    log.info(f"[{chat_id}] → {final_reply[:200]}")
    return "ok", 200


@app.route("/")
def health():
    """Health check — also displayed by UptimeRobot pings."""
    return "✅ Data Analyst Bot is running!", 200


@app.route("/set_webhook")
def set_webhook():
    """Visit this URL once after deploying to register the webhook with Telegram."""
    if not RENDER_URL:
        return "❌ Set the RENDER_URL environment variable first.", 400
    webhook_url = f"{RENDER_URL}/webhook"
    resp = requests.post(
        f"{TELEGRAM_API}/setWebhook",
        json={"url": webhook_url, "allowed_updates": ["message", "edited_message"]},
        timeout=10,
    )
    result = resp.json()
    log.info(f"setWebhook result: {result}")
    if result.get("ok"):
        return f"✅ Webhook set to: {webhook_url}", 200
    return f"❌ Failed: {result}", 500


@app.route("/status")
def status():
    """Shows current webhook info from Telegram."""
    resp = requests.get(f"{TELEGRAM_API}/getWebhookInfo", timeout=10)
    return resp.json(), 200


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    log.info(f"Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port)
