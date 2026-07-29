# 🤖 TDS Telegram Data Analyst Bot

A Telegram bot that answers data-analysis questions using AI and returns structured JSON responses. Built for the **IIT Madras Tools in Data Science (TDS)** course.

---

## ✨ Features

- Answers data-analysis questions (MOSPI, public datasets, inline data)
- Replies in **exact JSON format** as specified by the question
- Keeps **per-user conversation history** for multi-turn questions
- Logs every Q&A to a **public GitHub Gist** (JSONL format)
- Deployed on **Render.com** using Telegram webhooks (no polling)

---

## 🏗️ Architecture

```
User (Telegram)
    │  sends message
    ▼
Telegram Servers
    │  HTTP POST (webhook)
    ▼
Render.com  ──────────────►  AIPipe → OpenAI (gpt-4o-mini)
(Flask / bot.py)
    │  saves Q&A log
    ▼
GitHub Gist (public JSONL log)
    │  sends JSON reply
    ▼
User (Telegram)
```

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11 |
| Web framework | Flask |
| Hosting | Render.com (free tier) |
| Telegram integration | Webhook via Telegram Bot API |
| AI model | GPT-4o-mini via AIPipe (`/openai/v1`) |
| Logging | GitHub Gist (JSONL) |

---

## 📁 Project Structure

```
telegram-data-bot/
├── bot.py           # Main bot logic (Flask server + AI + logging)
├── requirements.txt # Python dependencies
├── runtime.txt      # Python version for Render
├── .env             # Secret keys (local only, never committed)
└── .gitignore       # Excludes .env and other local files
```

---

## ⚙️ Environment Variables

Set these in Render's **Environment** tab (or in `.env` for local testing):

| Variable | Description | Where to get it |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot identity token | [@BotFather](https://t.me/BotFather) on Telegram |
| `AIPIPE_TOKEN` | AI API access token | [aipipe.org/login](https://aipipe.org/login) |
| `GITHUB_TOKEN` | Token to update Gist | GitHub → Settings → Developer Settings → PAT |
| `GIST_ID` | ID of your log Gist | From your Gist's URL on github.com |
| `LOG_URL` | Public raw URL of the Gist | `https://gist.githubusercontent.com/<user>/<id>/raw/run.jsonl` |
| `RENDER_URL` | Your Render service URL | Your Render dashboard |

---

## 🚀 Deployment

### 1. Fork / clone this repo

```bash
git clone https://github.com/24f2005644/tds-telegram-data-bot.git
cd tds-telegram-data-bot
```

### 2. Create a Telegram bot

- Open Telegram → search **@BotFather** → `/newbot`
- Copy the **Bot Token**

### 3. Get your AIPipe token

- Go to [aipipe.org/login](https://aipipe.org/login) and sign in with your IITM Google account
- Copy the token shown on the page

### 4. Create a GitHub Gist

- Go to [gist.github.com](https://gist.github.com)
- Create a new **public** Gist with a file named `run.jsonl`, content `{}`
- Copy the Gist ID from the URL

### 5. Deploy to Render

- Connect your GitHub repo to [render.com](https://render.com)
- Set **Start Command**: `python bot.py`
- Add all environment variables in the **Environment** tab
- Deploy

### 6. Register the webhook

After deployment, visit once in your browser:
```
https://your-render-url.onrender.com/set_webhook
```
You should see: `✅ Webhook set to: https://your-render-url.onrender.com/webhook`

---

## 💬 Example Usage

**User asks:**
```
Which state has the highest maternal mortality rate based on MOSPI data?
Reply with ONLY this JSON: {"answer": {"state": "<state name>"}, "log_url": "<url>"}
```

**Bot replies:**
```json
{"answer":{"state":"Madhya Pradesh"},"log_url":"https://gist.githubusercontent.com/..."}
```

---

## 🔌 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Health check |
| `/webhook` | POST | Receives messages from Telegram |
| `/set_webhook` | GET | Registers webhook URL with Telegram |
| `/status` | GET | Shows current webhook info |

---

## 📋 Log Format (JSONL)

Each line in the Gist log is a JSON object:

```json
{
  "timestamp": "2026-07-29T14:30:00Z",
  "chat_id": 5049457606,
  "question": "Which state has the highest maternal mortality rate...",
  "raw_llm": "{\"answer\": {\"state\": \"Madhya Pradesh\"}, ...}",
  "final_reply": "{\"answer\":{\"state\":\"Madhya Pradesh\"},\"log_url\":\"...\"}"
}
```

---

## 🔑 Notes

- **AIPipe credits**: Free $1.00/week per IITM student account. Use `gpt-4o-mini` via `/openai/v1` (not `/openrouter/v1`) to avoid OpenRouter credit limits.
- **Render free tier**: Service sleeps after 15 min of inactivity. Use [UptimeRobot](https://uptimerobot.com) to ping `/` every 10 minutes.
- **Conversation memory**: Stored in RAM — resets on Render restart.
- **LOG_URL**: Use the Gist raw URL **without** a commit SHA so it always returns the latest content.

---

## 📄 License

MIT
