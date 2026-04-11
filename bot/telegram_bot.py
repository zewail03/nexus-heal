import os
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)
from telegram.request import HTTPXRequest
from config import TELEGRAM_BOT_TOKEN, FASTAPI_HOST, FASTAPI_PORT

FASTAPI_URL = os.getenv("FASTAPI_URL", f"http://127.0.0.1:{FASTAPI_PORT}")


# ── COMMANDS ──


async def start(update: Update, context):
    """/start — welcome message with usage instructions."""
    await update.message.reply_text(
        "*NEXUS-HEAL Bot Active*\n\n"
        "Commands:\n"
        "`/alert <description>` - analyze an alert\n"
        "`/demo` - run a demo alert\n"
        "`/status` - system health status\n\n"
        "Example:\n"
        "`/alert CPU usage 98% on api-gateway-prod, OOM errors in logs`",
        parse_mode="Markdown",
    )


async def handle_alert(update: Update, context):
    """/alert <text> — sends alert to NEXUS-HEAL API, shows diagnosis."""
    alert_text = " ".join(context.args) if context.args else ""
    if not alert_text:
        await update.message.reply_text("Usage: `/alert <alert description>`", parse_mode="Markdown")
        return

    # Show processing message
    msg = await update.message.reply_text(
        "Running NEXUS-HEAL pipeline...\n"
        "Sentinel classifying..."
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{FASTAPI_URL}/analyze",
                json={
                    "alert_id": f"TG-{update.message.message_id}",
                    "alert_text": alert_text,
                    "source": "telegram",
                },
                timeout=60,
            )
        result = response.json()
    except Exception as e:
        await msg.edit_text(f"Error contacting NEXUS-HEAL API: {e}")
        return

    # Severity emoji mapping
    severity_emoji = {
        "CRITICAL": "\U0001f534",  # red circle
        "HIGH": "\U0001f7e0",      # orange circle
        "MEDIUM": "\U0001f7e1",    # yellow circle
        "LOW": "\U0001f7e2",       # green circle
    }
    emoji = severity_emoji.get(result.get("severity", ""), "\u26aa")

    # Format fix plan steps
    fix_steps = "\n".join(
        f"{i+1}. {step}" for i, step in enumerate(result.get("fix_plan", []))
    )

    diagnosis_text = (
        f"{emoji} *Alert Diagnosed*\n\n"
        f"*Type:* `{result.get('alert_type', 'N/A')}`\n"
        f"*Severity:* `{result.get('severity', 'N/A')}`\n"
        f"*Confidence:* `{int(float(result.get('confidence', 0)) * 100)}%`\n\n"
        f"*Root Cause:*\n{result.get('root_cause', 'N/A')}\n\n"
        f"*Diagnosis:*\n{result.get('diagnosis', 'N/A')}\n\n"
        f"*Fix Plan:*\n{fix_steps}\n\n"
        f"*Estimated Time:* {result.get('estimated_time', '5 minutes')}"
    )

    # Approve/Reject buttons
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Approve & Execute",
                    callback_data=f"approve_{result.get('alert_id', '')}",
                ),
                InlineKeyboardButton(
                    "Reject & Escalate",
                    callback_data=f"reject_{result.get('alert_id', '')}",
                ),
            ]
        ]
    )

    await msg.edit_text(diagnosis_text, parse_mode="Markdown", reply_markup=keyboard)


async def handle_approval(update: Update, context):
    """Handles Approve/Reject button taps."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    action, alert_id = data.split("_", 1)
    approved = action == "approve"

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{FASTAPI_URL}/approve/{alert_id}",
                params={"approved": str(approved).lower()},
                timeout=30,
            )
    except Exception as e:
        await query.edit_message_text(f"Error calling approve endpoint: {e}")
        return

    # Remove the inline keyboard buttons
    await query.edit_message_reply_markup(reply_markup=None)

    # Send a new follow-up message (avoids Markdown parse errors from the original)
    if approved:
        await query.message.reply_text(
            "\u2705 *Fix approved and executed!*\nWatcher agent is monitoring...",
            parse_mode="Markdown",
        )
    else:
        await query.message.reply_text(
            "\u26a0\ufe0f *Fix rejected. Escalated to senior engineer.*",
            parse_mode="Markdown",
        )


async def demo(update: Update, context):
    """/demo — runs a pre-built demo alert so professor can see it live."""
    context.args = [
        "CPU", "usage", "98.7%", "on", "api-gateway-prod,",
        "OOM", "killer", "active,", "connection", "pool", "exhausted",
    ]
    await handle_alert(update, context)


async def status(update: Update, context):
    """/status — check system health."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{FASTAPI_URL}/health", timeout=10)
        data = response.json()
        text = f"*System Status:* `{data.get('status', 'unknown')}`\n*Service:* `{data.get('service', 'unknown')}`"
    except Exception:
        text = "*System Status:* `offline`\nFastAPI server is not reachable."

    await update.message.reply_text(text, parse_mode="Markdown")


# ── BUILD APP ──


def create_bot():
    """Creates and returns the Telegram bot Application."""
    request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0, write_timeout=60.0)
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("alert", handle_alert))
    app.add_handler(CommandHandler("demo", demo))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CallbackQueryHandler(handle_approval))
    return app
