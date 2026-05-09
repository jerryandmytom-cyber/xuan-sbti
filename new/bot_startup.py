# ===========================================================
# bot_startup.py - 支持 webhook 和 polling 两种模式
# ===========================================================

import os
import sys
import logging
import asyncio
import threading
from flask import Flask, jsonify
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask健康检查服务器
flask_app = Flask(__name__)

@flask_app.route('/health')
def health():
    return jsonify({"status": "ok", "service": "FortuneMaster Bot"})

def run_flask():
    """运行Flask健康检查服务器"""
    port = int(os.getenv("PORT", "8443"))
    flask_app.run(host='0.0.0.0', port=port)

# 核心模块导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from fortunemaster_new import main_run, SessionManager
    from metaphysics_engine import _init_common_bazi_cache
    logger.info("✅ Core modules imported")
except ImportError as e:
    logger.error(f"❌ Import error: {e}")
    sys.exit(1)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理消息"""
    try:
        user_id = str(update.effective_chat.id)
        user_message = update.message.text if update.message else ""
        logger.info(f"[{user_id}] {user_message}")
        response = main_run(user_id, user_message)
        await update.message.reply_text(response, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        await update.message.reply_text("❌ 系统错误")


async def main():
    """启动 Bot"""
    logger.info("🚀 FortuneMaster Bot starting...")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        logger.error("❌ Missing TELEGRAM_BOT_TOKEN!")
        sys.exit(1)

    application = Application.builder().token(bot_token).build()
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_message
    ))

    SessionManager.initialize()
    _init_common_bazi_cache()
    logger.info("✅ System initialized")

    # 检查部署模式
    webhook_url = os.getenv("WEBHOOK_URL", "")
    
    if webhook_url:
        # ============ Webhook 模式 ============
        webhook_host = os.getenv("WEBHOOK_HOST", "")
        if webhook_host:
            full_url = f"https://{webhook_host}/{webhook_url}"
            await application.initialize()
            await application.bot.set_webhook(full_url)
            logger.info(f"✅ Webhook set: {full_url}")
            
            # 启动Flask健康检查
            flask_thread = threading.Thread(target=run_flask, daemon=True)
            flask_thread.start()
            
            await application.run_webhook(
                listen="0.0.0.0",
                port=int(os.getenv("PORT", "8443")),
                url_path=f"/{webhook_url}"
            )
        else:
            logger.warning("⚠️ WEBHOOK_URL set but WEBHOOK_HOST missing, switching to polling")
            await application.initialize()
            await application.run_polling(drop_pending_updates=True)
    else:
        # ============ Polling 模式 ============
        logger.info("📡 Using Polling mode")
        
        # 启动Flask健康检查
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        await application.initialize()
        await application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())