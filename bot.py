# bot.py — The heart of your Data Analyst Bot
import os, json, logging, re, requests
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ── Config ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
AIPIPE_TOKEN       = os.environ["AIPIPE_TOKEN"]
GITHUB_TOKEN       = os.environ["GITHUB_TOKEN"]
GIST_ID            = os.environ["GIST_ID"]
LOG_URL            = os.environ["LOG_URL"]   # raw gist URL

AIPIPE_URL = "https://aipipe.org/openrouter/v1/chat/completions"
MODEL      = "google/gemini-2.0-flash-lite-001"   # fast & free on aipipe

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── In-memory run log (per session) ─────────────────────────────────────────
run_log: list[dict] = []

def append_log(entry: dict):
    """Add one line to our in-memory JSONL log and push it to the Gist."""
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

# ── Call the LLM via AIPipe ─────────────────────────────────────────────────
def ask_llm(messages: list[dict]) -> str:
    """Send a list of {role, content} messages to the LLM and return its reply."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
    }
    resp = requests.post(
        AIPIPE_URL,
        headers={
            "Authorization": f"Bearer {AIPIPE_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()

# ── Extract JSON from LLM output ────────────────────────────────────────────
def extract_json(text: str) -> str:
    """Pull the first {...} object out of the LLM's reply."""
    # Try to find JSON in code fences first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # Otherwise find the first { ... } block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return text

# ── The System Prompt ────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a data analyst assistant. 
The user will send you a data-analysis question.

IMPORTANT RULES:
1. Always reply with ONLY a JSON object — no extra text, no markdown, no explanation.
2. The JSON must have exactly two keys:
   - "answer": the answer shaped exactly as the question asks
   - "log_url": "{log_url}"
3. If the question asks about a public dataset (like MOSPI), use your knowledge or 
   reason carefully — do NOT say you cannot access the internet. Try your best.
4. If the question embeds the data inline (e.g. a table or numbers), analyse it directly.
5. If the question specifies an exact JSON shape for the answer (like {{"state": "<name>"}}), 
   follow that shape exactly.

Reply with ONLY the JSON object. No other text.""".format(log_url=LOG_URL)

# ── Per-user conversation history (for multi-turn questions) ─────────────────
user_histories: dict[int, list[dict]] = {}

# ── Handle incoming Telegram messages ───────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id   = update.effective_chat.id
    user_text = update.message.text
    
    log.info(f"Message from {chat_id}: {user_text[:80]}...")

    # Keep conversation history (for multi-turn questions)
    history = user_histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})
    
    # Build the full message list: system + history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    # Ask the LLM
    try:
        raw_reply = ask_llm(messages)
        log.info(f"LLM raw reply: {raw_reply[:200]}")
    except Exception as e:
        log.error(f"LLM error: {e}")
        await update.message.reply_text('{"answer": "error", "log_url": "' + LOG_URL + '"}')
        return

    # Add assistant reply to history
    history.append({"role": "assistant", "content": raw_reply})

    # Extract clean JSON
    clean_json = extract_json(raw_reply)

    # Validate it's parseable JSON
    try:
        parsed = json.loads(clean_json)
        # Make sure log_url is in there
        if "log_url" not in parsed:
            parsed["log_url"] = LOG_URL
        final_reply = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    except json.JSONDecodeError:
        # If LLM gave bad JSON, wrap what we have
        log.warning("LLM didn't return valid JSON, wrapping manually")
        final_reply = json.dumps({"answer": clean_json, "log_url": LOG_URL})

    # Log this interaction
    append_log({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "chat_id": chat_id,
        "question": user_text,
        "raw_llm": raw_reply,
        "final_reply": final_reply,
    })

    # Send reply
    await update.message.reply_text(final_reply)
    log.info(f"Replied: {final_reply[:200]}")

# ── Start the bot ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    log.info("Bot is running...")
    app.run_polling()
