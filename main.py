import asyncio
import uvicorn
from api.server import app as fastapi_app
from bot.telegram_bot import create_bot
from rag.vectorstore import setup_vectorstore
from config import FASTAPI_HOST, FASTAPI_PORT, TELEGRAM_BOT_TOKEN


async def run_telegram_bot():
    """Run the Telegram bot using the lower-level async API."""
    bot = create_bot()

    # Retry up to 5 times — network to Telegram can be flaky
    for attempt in range(1, 6):
        print(f"[NEXUS-HEAL] Connecting to Telegram (attempt {attempt}/5)...")
        try:
            await bot.initialize()
            await bot.start()
            await bot.updater.start_polling()
            break  # success
        except Exception as e:
            print(f"[NEXUS-HEAL] Attempt {attempt} failed: {e}")
            if attempt == 5:
                print("[NEXUS-HEAL] Telegram bot could not connect after 5 attempts.")
                print("[NEXUS-HEAL] FastAPI will continue running without the bot.")
                return
            print(f"[NEXUS-HEAL] Retrying in 5 seconds...")
            await asyncio.sleep(5)

    print("[NEXUS-HEAL] Telegram bot is polling.")

    # Keep running until cancelled
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await bot.updater.stop()
        await bot.stop()
        await bot.shutdown()


async def main():
    # 1. Setup vector store (ingest knowledge base)
    print("[NEXUS-HEAL] Setting up RAG knowledge base...")
    setup_vectorstore()
    print("[NEXUS-HEAL] Knowledge base ready.\n")

    # 2. Start FastAPI server
    print(f"[NEXUS-HEAL] Starting FastAPI on {FASTAPI_HOST}:{FASTAPI_PORT}")
    config = uvicorn.Config(
        fastapi_app,
        host=FASTAPI_HOST,
        port=FASTAPI_PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)

    # 3. Optionally start Telegram bot
    if TELEGRAM_BOT_TOKEN:
        print("[NEXUS-HEAL] Starting Telegram bot...")
        await asyncio.gather(
            server.serve(),
            run_telegram_bot(),
        )
    else:
        print("[NEXUS-HEAL] TELEGRAM_BOT_TOKEN not set — running FastAPI only.")
        await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
