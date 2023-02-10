import json
import logging
import asyncio
import os
import aiohttp
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, filters, MessageHandler, CommandHandler, ContextTypes, InlineQueryHandler
from html_parser import html_maker, parse_to_text
from uuid import uuid4
from random import random

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logger = logging.getLogger(__name__)


async def error(update, context):
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def validate_input(numbers) -> bool:
    for number in numbers:
        if number.isdigit() and 1000 <= int(number) <= 6000:
            return True
    return False


async def not_valid_input(update: Update):
    await update.message.reply_text("أدخل أرقام صحيحة ...")


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query.query.split()[0]
    if not validate_input([query]):
        return
    output = await inline_responser(update, context, query)
    results = [
        InlineQueryResultArticle(
            id=str(uuid4()),
            title="إظهار النتيجة",
            description="يسمح بإدخال رقم جامعي واحد فقط",
            input_message_content=InputTextMessageContent(
                message_text=output, parse_mode="MarkdownV2")
        )
    ]
    await update.inline_query.answer(results)


async def inline_responser(update, context, number):
    async with aiohttp.ClientSession() as session:
        response = await one_req(number, session)
    output = parse_to_text(response['html'], response['number'])
    return output if output else "الرقم الامتحاني خاطئ"


async def responser(update: Update, context: ContextTypes.DEFAULT_TYPE, numbers=(), html_bl=False):
    if not numbers:
        numbers = context.args if context.args else update.message.text.split()
        isvalid = validate_input(numbers)
        if not isvalid:
            return await not_valid_input(update)

    numbers.sort()
    message = await update.message.reply_text("⏳ يتم جلب المعلومات من الموقع ...")
    try:
        async with aiohttp.ClientSession() as session:
            tasks = [asyncio.create_task(one_req(number, session))
                     for number in numbers]
            gathered = await asyncio.gather(*tasks)
        if len(numbers) <= 5 and not html_bl:
            await send_txt_results(update, gathered)
        else:
            await message.edit_text("⌛️ يتم التحويل إلى ملف html ...")
            html_filename = html_maker(gathered)
            filename = "marks_" + str(int(random() * 100000)) + '.html'
            with open('config.json', 'r') as f:
                caption = json.load(f).get('caption')
            await update.message.reply_document(html_filename, caption=caption, filename=filename)

    except Exception:
        await update.message.reply_text("يوجد مشكلة حاليا, يرجى إعادة المحاولة", quote=True)
        for task in tasks:
            task.cancel()
    finally:
        await message.delete()


async def in_range(update: Update, context: ContextTypes.DEFAULT_TYPE, args=()):
    if not args:
        args = context.args
    strt, end = int(args[0]), int(args[1])
    if strt > end:
        strt, end = end, strt
    if strt < 1000 or end > 6000:
        await update.message.reply_text("أدخل مجال صحيح")
        return
    await responser(update, context, [x for x in range(strt, end)])


async def one_req(number, session: aiohttp.ClientSession, recurse=0) -> dict[bytes, int]:
    if recurse > 10:
        raise Exception("uncompleted request, try again later")

    url = "https://exam.albaath-univ.edu.sy/exam-it/re.php"
    async with session.post(url, data={'number1': number}) as req:
        res_data = await req.read()
    if req.status != 200:
        return await one_req(number, session, recurse+1)
    return {'html': res_data, 'number': number}


async def send_txt_results(update: Update, students):
    for student in students:
        output = parse_to_text(student['html'], student['number'])
        if not output:
            await update.message.reply_text(f"الرقم الامتحاني {student['number']} خاطئ", quote=True)
        else:
            await update.message.reply_text(output, parse_mode="MarkdownV2")


# some redirecting functions
async def html_it(*args):
    await responser(*args, html_bl=True)


async def year1(*args):
    return await in_range(*args, args=(1000, 2000))


async def year2(*args):
    return await in_range(*args, args=(2000, 3000))


async def year3(*args):
    return await in_range(*args, args=(3000, 4000))


async def year4(*args):
    return await in_range(*args, args=(4000, 5000))


async def year5(*args):
    return await in_range(*args, args=(5000, 6000))


async def start(update: Update, context) -> None:

    with open('config.json', 'r', encoding='utf-8') as f:
        output = json.load(f)['start']
    await update.message.reply_text(output, parse_mode="MarkdownV2",
                                    disable_web_page_preview=True)


def get_token() -> str:
    filename = "config.json"
    if not os.path.exists(filename):
        init_config_file()

    with open(filename, "r") as file:
        config = json.load(file)
    token = config["BOT_TOKEN"]
    if token == "0000000:aaaaaaaaaaaaaaaaaaaa":
        raise Exception(
            "Please add your bot token, get it from https://t.me/botfather")
    return token


def init_config_file():
    token = input("Please input your bot token (get it from @Botfather):\n")
    with open('config.json', 'w') as f:
        json.dump({'BOT_TOKEN': token, 'start': 'Hello'}, f)


def main() -> None:
    token = get_token()
    application = Application.builder().token(token).build()
    application.add_handlers(
        [
            CommandHandler(["start", "help"], start),
            CommandHandler("in_range", in_range),
            CommandHandler("html", html_it),
            CommandHandler('year1', year1),
            CommandHandler('year2', year2),
            CommandHandler('year3', year3),
            CommandHandler('year4', year4),
            CommandHandler('year5', year5),
            InlineQueryHandler(inline_query),
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, callback=responser)
        ]
    )
    application.add_error_handler(error)
    application.run_polling()


if __name__ == "__main__":
    main()
