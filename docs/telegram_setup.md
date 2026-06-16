# Telegram Setup

Telegram is the **primary** chat interface (remote-friendly, supports text,
files, voice, buttons, screenshots, and an approval flow).

## 1. Create a bot

1. In Telegram, message **@BotFather** → `/newbot` → choose a name + username.
2. Copy the **bot token**.

## 2. Find your user ID

Message **@userinfobot** (or `@RawDataBot`) to get your numeric **user ID**.

## 3. Configure `.env`

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=123456:ABC...           # from BotFather
TELEGRAM_ALLOWED_USER_IDS=11111111,22222222 # allowlist (comma-separated)
```

Only user IDs in `TELEGRAM_ALLOWED_USER_IDS` are served. Everyone else is
ignored and the attempt is audited.

## 4. Commands

```
/start       register + welcome (allowlisted only)
/status      system + running tasks
/tasks       list recent tasks
/approve <id>  approve a pending approval
/deny <id>     deny a pending approval
/mode <name>   set execution mode (fast|deep|private|...)
/models      list registered models + health
/agents      list agents
/memory      memory stats / recent items
/screenshot  return latest desktop/browser screenshot
/help        command help
```

## 5. Inline approvals

Risky steps send an approval card with inline buttons
(**Approve once / Deny / Trust workflow**). Tapping a button resolves the
matching `approvals` row and resumes the task.

## 6. Files & voice

- Sending a document/photo uploads it to memory (`receive_telegram_file`).
- Sending a voice note triggers transcription (`transcribe_telegram_voice`,
  Phase 2 with faster-whisper) and routes the text as a command.

## 7. Modes of operation

- **Polling** (default, no public URL needed): the bot long-polls Telegram.
- **Webhook** (Phase 2+): set `TELEGRAM_WEBHOOK_URL` to a public HTTPS endpoint.

Phase 1 ships a `python-telegram-bot`-based bot scaffold that is **disabled by
default** and only runs when `TELEGRAM_ENABLED=true` and a token is present, so
the backend boots fine without Telegram configured.
