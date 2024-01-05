import html
from io import BytesIO
import json
import logging
import asyncio
import os
import traceback
import aiohttp
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import (
    Application,
    filters,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
)
from telegram.constants import ParseMode

from html_parser import html_maker, parse_to_text
from uuid import uuid4
from random import random

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    tb_list = traceback.format_exception(
        None, context.error, context.error.__traceback__
    )
    tb_string = "".join(tb_list)
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )
    bytes_io = BytesIO()
    bytes_io.write(message.encode())

    try:
        with open("config.json", "r") as file:
            config = json.load(file)
        DEVELOPER_USER_ID = config["DEVELOPER_USER_ID"]
        await context.bot.send_document(
            DEVELOPER_USER_ID, bytes_io.getvalue(), filename="logs.html"
        )
        await context.bot.send_message(
            chat_id=DEVELOPER_USER_ID, text=message, parse_mode=ParseMode.HTML
        )
    except Exception:
        pass


spam_cache = {}


def validate_input(numbers) -> bool:
    for number in numbers:
        if number.isdigit() and 1 <= int(number) <= 100000:
            return True
    return False


async def not_valid_input(update: Update):
    await update.message.reply_text("أدخل أرقام صحيحة ...")


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query.query.split()
    if not query:
        return
    query = query[0]
    if not validate_input([query]):
        return
    output = await inline_responser(update, context, query)
    results = [
        InlineQueryResultArticle(
            id=str(uuid4()),
            title="إظهار النتيجة",
            description="يسمح بإدخال رقم جامعي واحد فقط",
            input_message_content=InputTextMessageContent(
                message_text=output, parse_mode="MarkdownV2"
            ),
        )
    ]
    await update.inline_query.answer(results)


async def inline_responser(update, context, number):
    async with aiohttp.ClientSession() as session:
        response = await one_req(number, session)
    output = parse_to_text(response["html"], response["number"])
    return output if output else "الرقم الامتحاني خاطئ"


async def responser(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    numbers=(),
    html_bl=False,
    caption="",
):
    if not numbers:
        numbers = context.args if context.args else update.message.text.split()
        if len(numbers) > 10:
            await update.message.reply_text(
                "يمكنك ادخال 10 ارقام ك حد أقصى", quote=True
            )
            return
        isvalid = validate_input(numbers)
        if not isvalid:
            return await not_valid_input(update)
    user_id = update.message.from_user.id
    global spam_cache
    if spam_cache.get(user_id):
        await update.message.reply_text(
            "يرجى الانتظار حتى انتهاء طلبك السابق", quote=True
        )
        return
    spam_cache[user_id] = True
    context.application.create_task(doing_the_work(update, numbers, html_bl, caption))


async def doing_the_work(update: Update, numbers, html_bl, caption):
    message = await update.message.reply_text("⏳ يتم جلب المعلومات من الموقع ...")
    user_id = update.message.from_user.id

    try:
        async with aiohttp.ClientSession() as session:
            tasks = [
                asyncio.create_task(one_req(number, session)) for number in numbers
            ]
            gathered = await asyncio.gather(*tasks)
        if len(numbers) <= 5 and not html_bl:
            await send_txt_results(update, gathered)
        else:
            await message.edit_text("⌛️ يتم التحويل إلى ملف html ...")
            html_filename = html_maker(gathered)
            filename = "marks_" + str(int(random() * 100000)) + ".html"
            if not caption:
                with open("config.json", "r", encoding="utf-8") as f:
                    caption = json.load(f).get("caption")
            await update.message.reply_document(
                html_filename,
                caption=caption,
                filename=filename,
                parse_mode="MarkdownV2",
            )

    except Exception as exp:
        print(exp)
        await update.message.reply_text(
            "يوجد مشكلة حاليا, يرجى إعادة المحاولة", quote=True
        )
        for task in tasks:
            task.cancel()
    finally:
        spam_cache[user_id] = False
        await message.delete()


async def one_req(number, session: aiohttp.ClientSession, recurse=0) -> dict:
    if recurse > 10:
        raise Exception("uncompleted request, try again later")

    try:
        url = "https://exam.albaath-univ.edu.sy/exam-it/re.php"
        async with session.post(url, data={"number1": number}) as req:
            res_data = await req.read()
        if req.status != 200:
            await asyncio.sleep(0.5)
            return await one_req(number, session, recurse + 1)
        return {"html": res_data, "number": number}
    except:
        await asyncio.sleep(0.5)
        return await one_req(number, session, recurse + 1)


async def send_txt_results(update: Update, students):
    for student in students:
        output = parse_to_text(student["html"], student["number"])
        if not output:
            await update.message.reply_text(
                f"الرقم الامتحاني {student['number']} خاطئ", quote=True
            )
        else:
            await update.message.reply_text(output, parse_mode="MarkdownV2")


# some redirecting functions
async def html_it(*args):
    await responser(*args, html_bl=True)


async def start(update: Update, context) -> None:
    with open("config.json", "r", encoding="utf-8") as f:
        output = json.load(f)["start"]
    await update.message.reply_text(
        output, parse_mode="MarkdownV2", disable_web_page_preview=True
    )


def check_environment_variables():
    with open("config.json") as f:
        config = json.load(f)

    variables = ["BOT_TOKEN", "start", "caption", "HTML_sign", "DEVELOPER_USER_ID"]

    for variable in variables:
        if os.getenv(variable):
            config[variable] = os.getenv(variable)

    with open("config.json", "w") as f:
        json.dump(config, f)


def get_token() -> str:
    filename = "config.json"
    if not os.path.exists(filename):
        init_config_file()
    check_environment_variables()
    with open(filename, "r") as file:
        config = json.load(file)
    token = config["BOT_TOKEN"]
    if token == "0000000:aaaaaaaaaaaaaaaaaaaa":
        raise Exception("Please add your bot token, get it from https://t.me/botfather")
    return token


def init_config_file():
    token = input("Please input your bot token (get it from @Botfather):\n")
    with open("config.json", "w") as f:
        json.dump({"BOT_TOKEN": token, "start": "Hello"}, f)


def main() -> None:
    token = get_token()
    application = Application.builder().token(token).build()
    application.add_handlers(
        [
            CommandHandler(["start", "help"], start),
            CommandHandler("html", html_it),
            InlineQueryHandler(inline_query),
            MessageHandler(filters.TEXT & ~filters.COMMAND, callback=responser),
        ]
    )
    application.add_error_handler(error_handler)
    application.run_polling()


if __name__ == "__main__":
    main()
