import argparse, json, logging, os, openai, requests
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackContext, filters

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN') or exit("🚨Error: TELEGRAM_TOKEN is not set.")
openai.api_key = os.getenv('OPENAI_API_KEY') or exit("🚨Error: OPENAI_API_KEY is not set.")
SESSION_DATA = {}

def load_configuration():
    with open('configuration.json', 'r') as file:
        return json.load(file)

def get_session_id(func):
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        session_id = str(update.effective_chat.id if update.effective_chat.type in ['group', 'supergroup'] else update.effective_user.id)
        return await func(update, context, session_id, *args, **kwargs)
    return wrapper

def initialize_session_data(func):
    async def wrapper(update: Update, context: CallbackContext, session_id, *args, **kwargs):
        if session_id not in SESSION_DATA:
            SESSION_DATA[session_id] = load_configuration()['default_session_values']
        return await func(update, context, session_id, *args, **kwargs)
    return wrapper

def check_api_key(func):
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if not openai.api_key:
            await update.message.reply_text("⚠️ Please set your OpenAI API key: /set openai_api_key YOUR_KEY")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def relay_errors(func):
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {e}")
    return wrapper

CONFIGURATION = load_configuration()
VISION_MODELS = CONFIGURATION.get('vision_models', [])
VALID_MODELS = CONFIGURATION.get('VALID_MODELS', {})

@relay_errors
@get_session_id
@initialize_session_data
@check_api_key
async def handle_message(update: Update, context: CallbackContext, session_id):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    session_data = SESSION_DATA[session_id]

    if update.message.photo and session_data['model'] in VISION_MODELS:
        photo = update.message.photo[-1]
        photo_file = await context.bot.get_file(photo.file_id)
        photo_url = photo_file.file_path
        caption = update.message.caption or "Describe this image."
        session_data['chat_history'].append({
            "role": "user",
            "content": [
                {"type": "text", "text": caption},
                {"type": "image_url", "image_url": {"url": photo_url}}
            ]
        })
    else:
        user_message = update.message.text
        session_data['chat_history'].append({
            "role": "user",
            "content": user_message
        })

    messages_for_api = session_data['chat_history']
    response = await response_from_openai(
        session_data['model'],
        messages_for_api,
        session_data['temperature'],
        session_data['max_tokens']
    )
    session_data['chat_history'].append({'role': 'assistant', 'content': response})
    await update.message.reply_markdown(response)

async def response_from_openai(model, messages, temperature, max_tokens):
    try:
        result = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return result.choices[0].message['content']
    except Exception as e:
        return f"Error from OpenAI: {e}"

# All other commands (start, reset, set, help, etc.) stay unchanged
# Just keep the rest of your code as-is

def register_handlers(application):
    application.add_handlers(handlers={ 
        -1: [
            CommandHandler('start', command_start),
            CommandHandler('reset', command_reset),
            CommandHandler('clear', command_clear),
            CommandHandler('set', command_set),
            CommandHandler('show', command_show),
            CommandHandler('help', command_help)
        ],
        1: [MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)]
    })

def railway_dns_workaround():
    from time import sleep
    sleep(1.3)
    for _ in range(3):
        try:
            if requests.get("https://api.telegram.org", timeout=3).status_code == 200:
                print("✅ Telegram API reachable")
                return
        except:
            print(f"🔁 Retry {_+1}")
    print("❌ Could not reach Telegram API.")

def main():
    parser = argparse.ArgumentParser(description="Run the Telegram bot.")
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.disable(logging.WARNING)

    railway_dns_workaround()
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(application)

    try:
        print("✅ Bot running...")
        application.run_polling()
    except Exception as e:
        logging.error(f"Fatal error: {e}")

if __name__ == '__main__':
    main()
