"""Telegram bot — primary chat interface (allowlist + commands + approvals).

`python-telegram-bot` is imported lazily so the backend boots without it. The bot
only starts when TELEGRAM_ENABLED=true and a token is set. Every update is
checked against the user-ID allowlist before any work is done.
"""
from __future__ import annotations

import logging

from app.agents.orchestrator import Orchestrator
from app.config import Settings
from app.services.container import Brain

logger = logging.getLogger("jarvis.telegram")

HELP_TEXT = (
    "JARVIS commands:\n"
    "/start - register\n/status - system status\n/tasks - recent tasks\n"
    "/approve <id> - approve\n/deny <id> - deny\n/mode <name> - set mode\n"
    "/models - list models\n/agents - list agents\n/memory - memory stats\n"
    "/screenshot - latest screenshot\n/help - this help\n"
    "Send any message to give JARVIS a command."
)


class JarvisTelegramBot:
    enabled = True

    def __init__(self, brain: Brain, settings: Settings) -> None:
        self.brain = brain
        self.settings = settings
        self.allowed = set(settings.telegram_allowed_user_ids)
        self.orch = Orchestrator(brain)
        self._app = None
        self._mode_override = None

    def _authorized(self, user_id: int) -> bool:
        ok = user_id in self.allowed
        if not ok:
            self.brain.audit.record(
                agent="telegram", tool="auth",
                output_summary=f"Rejected unauthorized telegram user {user_id}",
                risk="medium", approval_status="denied",
            )
        return ok

    async def start(self) -> None:  # pragma: no cover - requires network + token
        try:
            from telegram import Update
            from telegram.ext import (
                ApplicationBuilder,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError("python-telegram-bot is not installed.") from exc

        app = ApplicationBuilder().token(self.settings.telegram_bot_token).build()

        async def guard(update: Update) -> bool:
            uid = update.effective_user.id if update.effective_user else -1
            if not self._authorized(uid):
                await update.message.reply_text("Unauthorized.")
                return False
            return True

        async def cmd_start(update, ctx):  # noqa: ANN001
            if await guard(update):
                await update.message.reply_text(f"JARVIS online.\n{HELP_TEXT}")

        async def cmd_help(update, ctx):  # noqa: ANN001
            if await guard(update):
                await update.message.reply_text(HELP_TEXT)

        async def cmd_status(update, ctx):  # noqa: ANN001
            if await guard(update):
                await update.message.reply_text(
                    f"Models:{len(self.brain.registry.enabled())} "
                    f"Tasks:{len(self.brain.tasks.all())} "
                    f"Pending approvals:{len(self.brain.approvals.pending())} "
                    f"E-STOP:{self.brain.emergency_stop}"
                )

        async def cmd_models(update, ctx):  # noqa: ANN001
            if await guard(update):
                names = "\n".join(s.key for s in self.brain.registry.enabled())
                await update.message.reply_text(names or "No enabled models.")

        async def cmd_agents(update, ctx):  # noqa: ANN001
            if await guard(update):
                await update.message.reply_text("\n".join(self.brain.agents.keys()))

        async def cmd_tasks(update, ctx):  # noqa: ANN001
            if await guard(update):
                lines = [f"{t.id}: {t.status.value} - {t.command[:40]}" for t in self.brain.tasks.all(10)]
                await update.message.reply_text("\n".join(lines) or "No tasks.")

        async def cmd_memory(update, ctx):  # noqa: ANN001
            if await guard(update):
                await update.message.reply_text(
                    f"Memory items: {self.brain.memory.count()} | {self.brain.memory.collections()}"
                )

        async def cmd_approve(update, ctx):  # noqa: ANN001
            if await guard(update) and ctx.args:
                a = self.brain.approvals.resolve(ctx.args[0], True, resolved_by="telegram")
                await update.message.reply_text(f"Approval {ctx.args[0]}: {a.status.value if a else 'not found'}")

        async def cmd_deny(update, ctx):  # noqa: ANN001
            if await guard(update) and ctx.args:
                a = self.brain.approvals.resolve(ctx.args[0], False, resolved_by="telegram")
                await update.message.reply_text(f"Approval {ctx.args[0]}: {a.status.value if a else 'not found'}")

        async def cmd_mode(update, ctx):  # noqa: ANN001
            from app.model_router.modes import Mode

            if await guard(update) and ctx.args:
                try:
                    self._mode_override = Mode(ctx.args[0].upper())
                    await update.message.reply_text(f"Mode set: {self._mode_override.value}")
                except ValueError:
                    await update.message.reply_text("Unknown mode.")

        async def on_message(update, ctx):  # noqa: ANN001
            if not await guard(update):
                return
            text = update.message.text or ""
            await update.message.reply_text("Working on it…")
            result = await self.orch.run(text, mode_override=self._mode_override)
            reply = result.answer
            if result.pending_approvals:
                reply += f"\n\n⚠️ Pending approvals: {', '.join(result.pending_approvals)}"
            await update.message.reply_text(reply[:4000])

        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("help", cmd_help))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("models", cmd_models))
        app.add_handler(CommandHandler("agents", cmd_agents))
        app.add_handler(CommandHandler("tasks", cmd_tasks))
        app.add_handler(CommandHandler("memory", cmd_memory))
        app.add_handler(CommandHandler("approve", cmd_approve))
        app.add_handler(CommandHandler("deny", cmd_deny))
        app.add_handler(CommandHandler("mode", cmd_mode))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

        self._app = app
        await app.initialize()
        await app.start()
        await app.updater.start_polling()

    async def stop(self) -> None:  # pragma: no cover
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
