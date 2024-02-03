import asyncio
import html
import json
import logging
import os
import re
import time
import traceback
from datetime import datetime, timedelta
from io import BytesIO
from random import random
from typing import List, Optional
from uuid import uuid4

import aiohttp
from admin_commands import (
    add_to_white_list,
    cancel_command,
    clear_spam_cache,
    delete_all_students,
    download_this_file,
    exec_command,
    get_all_subjects,
    get_from_db_by_student_id,
    get_from_db_by_subject,
    get_public_message,
    get_total_users,
    remove_white_list,
    send_db_backup,
    send_db_now,
    send_message,
    update_database,
)
from helpers import (
    DEV_ID,
    SPAM_CACHE,
    check_and_insert_user,
    get_session,
    init_database,
    parse_marks_to_text,
    verify_blocked_user,
)
from html_parser import (
    extract_data,
    get_rows_lenght,
    html_maker,
)
from models import Student
from queries import (
    get_student,
    get_user_from_db,
)
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    InlineQueryHandler,
    MessageHandler,
    filters,
)
from web_scrapper import multi_async_request, one_req

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

DANGER_TIME_DURATION = 60


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

    await context.bot.send_document(DEV_ID, bytes_io.getvalue(), filename="logs.html")
    try:
        await context.bot.send_message(
            chat_id=DEV_ID, text=message, parse_mode=ParseMode.HTML
        )
    except Exception:
        pass


def validate_input(numbers: List[str]) -> bool:
    for number in numbers:
        if not (number.isdigit() and 1 <= int(number) <= 100000):
            return False
    return True


@verify_blocked_user
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query.query
    if not query:
        return
    query = query.split()[0]
    if not validate_input([query]):
        return

    output = await inline_responser(update, context, query)
    results = [
        InlineQueryResultArticle(
            id=str(uuid4()),
            title="إظهار النتيجة ",
            description="يسمح بإدخال رقم جامعي واحد فقط",
            input_message_content=InputTextMessageContent(
                message_text=output, parse_mode=ParseMode.MARKDOWN_V2
            ),
        )
    ]
    await update.inline_query.answer(results)


async def inline_responser(update, context, number):
    async with aiohttp.ClientSession() as session:
        response = await one_req(number, session, 2)
    Session = get_session(context)
    with Session() as conn:
        student = extract_data(conn, response)
        conn.commit()

    output = parse_marks_to_text(student, True)

    return output if output else "الرقم الامتحاني خاطئ"


async def responser(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    numbers=(),
    html_bl=False,
    caption="",
):
    query = update.callback_query
    user_id = query.from_user.id if query else update.message.from_user.id
    user = check_and_insert_user(update, context)
    if SPAM_CACHE.get(user_id):
        output = "يرجى الانتظار حتى انتهاء طلبك السابق"
        if query:
            await query.answer(output)
        else:
            await update.message.reply_text(output, quote=True)
        return

    recurse_limit = 15 if user.is_whitelisted else 3
    if not numbers:
        if context.args:
            numbers = context.args
        elif query:
            numbers = (query.data,)
        else:
            numbers = update.message.text.split()

        if len(numbers) > 10 and not user.is_whitelisted and user.telegram_id != DEV_ID:
            await update.message.reply_text("يمكنك ادخال 10 ارقام كحد أقصى", quote=True)
            return
        isvalid = validate_input(numbers)
        if not isvalid:
            return await update.message.reply_text("أدخل أرقام صحيحة ...")

    if query or len(numbers) > 10:
        context.application.create_task(
            doing_the_work(
                update,
                context,
                user_id,
                numbers,
                html_bl,
                caption,
                user_msg_id=query.message.id if query else None,
                recurse_limit=recurse_limit,
            )
        )
        if query:
            await query.answer()
    else:
        context.application.create_task(get_stored_marks(update, context, numbers))


async def get_stored_marks(
    update: Update, context: ContextTypes.DEFAULT_TYPE, numbers: List[int]
):
    query = update.callback_query
    user_id = query.from_user.id if query else update.message.from_user.id
    outputs_coroutines = []
    unsaved_numbers = []
    with get_session(context).begin() as session:
        for number in numbers:
            student = get_student(session, int(number))
            if student and len(student.subjects_marks):
                keyboard = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🌐 جلب العلامات من الموقع",
                                callback_data=str(student.university_number),
                            )
                        ]
                    ]
                )
                message = update.message.reply_text(
                    parse_marks_to_text(student),
                    ParseMode.MARKDOWN_V2,
                    reply_markup=keyboard,
                )
                outputs_coroutines.append(message)
            else:
                # handel it
                unsaved_numbers.append(number)

    if unsaved_numbers:
        await doing_the_work(update, context, user_id, unsaved_numbers)

    for i, output_coro in enumerate(outputs_coroutines):
        if i and i % 5 == 0:
            await asyncio.sleep(1)
        await output_coro


async def doing_the_work(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    numbers: list[int],
    html_bl: Optional[bool] = False,
    caption: Optional[str] = None,
    user_msg_id: int | None = None,
    recurse_limit=2,
):
    SPAM_CACHE[user_id] = True
    message = await context.bot.send_message(
        user_id, "⏳ يتم جلب المعلومات من الموقع ...", reply_to_message_id=user_msg_id
    )
    try:
        gathered_results = await multi_async_request(numbers, recurse_limit)
        Session = get_session(context)
        with Session() as session:
            students_data = [
                extract_data(session, student_res) for student_res in gathered_results
            ]
            session.commit()

        if len(numbers) <= 5 and not html_bl:
            await send_txt_results(
                update,
                context,
                user_id,
                students_data,
                reply_to_msg=user_msg_id,
            )
        else:
            await message.edit_text("⌛️ يتم التحويل إلى ملف html ...")
            html_filename = html_maker(students_data)
            filename = "marks_" + str(int(random() * 100000)) + ".html"
            if not caption:
                with open("config.json", "r", encoding="utf-8") as f:
                    caption = json.load(f).get("caption")
            caption += "\n{} \\- {}".format(numbers[0], numbers[-1])
            await context.bot.send_document(
                user_id,
                html_filename,
                caption=caption,
                filename=filename,
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    except Exception:
        logger.exception("Error:")
        await context.bot.send_message(
            user_id,
            "يوجد مشكلة حاليا, يرجى إعادة المحاولة",
            reply_to_message_id=user_msg_id,
        )
    finally:
        SPAM_CACHE[user_id] = False
        await message.delete()


async def send_txt_results(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    students: List[Student],
    reply_to_msg: int | None = None,
):
    query = update.callback_query if update else None
    outputs_coroutines = []

    for student in students:
        output = parse_marks_to_text(student, True)
        if student.name == "NULL":
            coro = context.bot.send_message(
                user_id,
                f"الرقم الامتحاني {student.university_number} خاطئ",
                reply_to_message_id=reply_to_msg,
            )
        elif not output:
            coro = context.bot.send_message(
                user_id,
                "لا يوجد علامات لهذا الطالب حاليا....",
                reply_to_message_id=reply_to_msg,
            )
        elif query:
            coro = query.edit_message_text(output, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            coro = context.bot.send_message(
                user_id, output, parse_mode=ParseMode.MARKDOWN_V2
            )
        outputs_coroutines.append(coro)

    for i, coro in enumerate(outputs_coroutines):
        if i and i % 5 == 0:
            await asyncio.sleep(1)
        await coro


# some redirecting functions
@verify_blocked_user
async def html_it(*args):
    await responser(*args, html_bl=True)


@verify_blocked_user
async def danger_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = check_and_insert_user(update, context)
    if (not user.is_whitelisted) and user_id != DEV_ID:
        await update.message.reply_text("تم إيقاف هذه الميزة بسبب الضغط", quote=True)
        return

    stored_start_time: datetime | None = context.user_data.get("start_time")
    if stored_start_time and datetime.now() - stored_start_time <= timedelta(
        minutes=DANGER_TIME_DURATION
    ):
        output = "لقد قمت بتفعيل وضع الخطر بالفعل, تبقى `{}` دقيقة لانتهاء مدة التأهّب"
        output += "\nللالغاء إضغط على الأمر /cancel\\_danger"
        diff_time = timedelta(minutes=DANGER_TIME_DURATION) - (
            datetime.now() - stored_start_time
        )

        await update.message.reply_text(
            output.format(diff_time.seconds // 60),
            parse_mode=ParseMode.MARKDOWN_V2,
            quote=True,
        )
        return
    if not context.args:
        await update.message.reply_text(
            "أدخل الرقم بعد كتابة الأمر مثال:\n /danger 3227", quote=True
        )
        return
    elif validate_input([context.args[0]]):
        await update.message.reply_text("أدخل أرقام صحيحة فقط", quote=True)
        return

    number = int(context.args[0])

    try:
        gathered_results = await multi_async_request([number], 6)
        last_lenght = get_rows_lenght(gathered_results[0].html_page)
    except Exception:
        last_lenght = 0
    output = (
        "سيقوم بالبوت في انتظار قدوم علامات جديدة لمدة `{}`".format(
            DANGER_TIME_DURATION
        )
        + " دقيقة، في حال وصول علامات جديدة سيتم إرسالها فورا\n"
        + "للإلغاء إضغط على /cancel\\_danger"
    )
    await update.message.reply_text(output, ParseMode.MARKDOWN_V2, quote=True)
    user_id = update.message.from_user.id

    task = context.application.create_task(
        new_update_checker(context, user_id, last_lenght, number)
    )
    context.user_data["stored_task"] = task


async def new_update_checker(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, last_length: int, number: int
):
    start_time = datetime.now()
    context.user_data["start_time"] = start_time
    while datetime.now() - start_time < timedelta(minutes=DANGER_TIME_DURATION):
        await asyncio.sleep(10)
        gathered_results = await multi_async_request([number])
        if last_length != get_rows_lenght(gathered_results[0].html_page):
            Session = get_session(context)
            with Session() as session:
                student = extract_data(session, gathered_results[0])
                await send_txt_results(None, context, user_id, student)
                session.commit()

            context.user_data["stored_task"] = None
            break
    else:
        await context.bot.send_message(
            user_id, "لم يتم إصدار أي علامات خلال فترة التأهب..."
        )


@verify_blocked_user
async def cancel_danger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task = context.user_data.get("stored_task")
    if isinstance(task, asyncio.Task):
        task.cancel()
        context.user_data["start_time"] = None
        await update.message.reply_text("تم الإلغاء بنجاح !", quote=True)
    else:
        await update.message.reply_text("لا يوجد شيء قيد العمل حاليا...", quote=True)


async def in_range(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = get_user_from_db(get_session(context), user_id)
    if (user_id == DEV_ID) or (user and user.is_whitelisted):
        start_number, end_number = map(int, context.args)
        return await responser(
            update, context, [i for i in range(start_number, end_number + 1)], True
        )


async def lazy_in_range(
    update: Update, context: ContextTypes.DEFAULT_TYPE, caption: str = ""
):
    user_id = update.message.from_user.id

    user = get_user_from_db(get_session(context), user_id)
    if not ((user_id == DEV_ID) or (user and user.is_whitelisted)):
        return

    unsaved_numbers = []
    start_number, end_number, time_offset = map(int, context.args)
    numbers = [i for i in range(start_number, end_number + 1)]

    all_students = []
    Session = get_session(context)
    start = time.time()
    with Session() as session:
        for number in numbers:
            student = get_student(session, int(number))
            if student and (
                datetime.utcnow() - student.last_update
                <= timedelta(minutes=time_offset)
            ):
                session.refresh(student, ["subjects_marks"])
                all_students.append(student)
            else:
                unsaved_numbers.append(number)
        session.commit()
    await update.message.reply_text(
        "there is {} from {} has been retrived from db, time taken: {}".format(
            len(all_students), len(numbers), time.time() - start
        )
    )

    if unsaved_numbers:
        start = time.time()
        responses = await multi_async_request(unsaved_numbers, 15)
        all_students.extend([extract_data(session, response) for response in responses])
        await update.message.reply_text(
            "there's {} fethed from the website, time taken: {}".format(
                len(unsaved_numbers), time.time() - start
            )
        )
    start = time.time()
    await update.message.reply_text("generating html file...")
    html_filename = html_maker(all_students)
    await update.message.reply_text("done, time taken: {}".format(time.time() - start))
    filename = "marks_" + str(int(random() * 100000)) + ".html"
    if not caption:
        with open("config.json", "r", encoding="utf-8") as f:
            caption = json.load(f).get("caption")
    caption += "\n{} \\- {}".format(numbers[0], numbers[-1])
    await context.bot.send_document(
        user_id,
        html_filename,
        caption=caption,
        filename=filename,
        parse_mode=ParseMode.MARKDOWN_V2,
    )


@verify_blocked_user
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    check_and_insert_user(update, context)
    with open("config.json", "r", encoding="utf-8") as f:
        output = json.load(f)["start"]
    await update.message.reply_text(
        output, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True
    )


def get_token() -> str:
    if os.getenv("BOT_TOKEN"):
        return os.getenv("BOT_TOKEN")
    filename = "config.json"
    if not os.path.exists(filename):
        init_config_file()

    with open(filename, "r") as file:
        config = json.load(file)
    token = config["BOT_TOKEN"]
    if token == "0000000:aaaaaaaaaaaaaaaaaaaa":
        raise Exception("Please add your bot token, get it from https://t.me/botfather")
    return token


def init_config_file():
    token = input("Please input your bot token (get it from @Botfather):\n")
    with open("config.json", "w") as f:
        json.dump(
            {
                "BOT_TOKEN": token,
                "start": "Hello",
            },
            f,
        )


def main() -> None:
    token = get_token()
    application = Application.builder().token(token).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("send_message", send_message)],
        states={
            1: [MessageHandler(~filters.COMMAND, get_public_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )
    application.add_handler(conv_handler)
    application.add_handlers(
        [
            CommandHandler(["start", "help"], start),
            CommandHandler("html", html_it),
            CommandHandler("send_db_backup", send_db_now),
            CommandHandler("danger", danger_mode),
            CommandHandler("cancel_danger", cancel_danger),
            CommandHandler("clear_spam_cache", clear_spam_cache),
            CommandHandler("in_range", in_range),
            CommandHandler("lazy_in_range", lazy_in_range),
            CommandHandler("exec", exec_command),
            CommandHandler("get_db_len", get_total_users),
            CommandHandler("update_database", update_database),
            CommandHandler("add_white_list", add_to_white_list),
            CommandHandler("remove_white_list", remove_white_list),
            CommandHandler("get_from_db_by_student_id", get_from_db_by_student_id),
            CommandHandler("get_from_db_by_subject", get_from_db_by_subject),
            CommandHandler("download_this_file", download_this_file),
            CommandHandler("get_all_subjects", get_all_subjects),
            CommandHandler("delete_all_students", delete_all_students),
            InlineQueryHandler(inline_query),
            MessageHandler(filters.TEXT & ~filters.COMMAND, callback=responser),
            CallbackQueryHandler(responser, pattern=re.compile(r"^\d{1,5}$")),
        ]
    )
    application.add_error_handler(error_handler)
    init_database(application.bot_data)
    application.job_queue.run_repeating(
        send_db_backup,
        timedelta(hours=6),
        timedelta(seconds=20),
    )
    application.run_polling()


if __name__ == "__main__":
    main()
