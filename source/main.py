import asyncio
import html
import json
import logging
import os
import re
import time
import traceback
from datetime import datetime, timedelta, timezone
from io import BytesIO
from random import random
from typing import List, Optional
from uuid import uuid4

from admin_commands import (
    add_new_admin,
    add_new_season,
    add_to_white_list,
    admin_help_message,
    block_user,
    cancel_command,
    delete_all_students,
    download_this_file,
    exec_command,
    get_all_subjects,
    get_from_db_by_student_id,
    get_from_db_by_subject,
    get_public_message,
    get_total_users,
    remove_admin,
    remove_white_list,
    send_db_backup,
    send_db_now,
    send_message,
    unblock_user,
    update_database,
)
from concurent_update_processer import ConcurentUpdateProcessor
from constants import DANGER_TIME_DURATION, DEV_ID, FILE_CAPTION, START_MESSAGE
from helpers import (
    acquire_task_or_drop,
    check_and_insert_user,
    get_session,
    get_user_id,
    init_database,
    parse_marks_to_text_from_db,
    parse_marks_to_text_from_website,
    verify_blocked_user,
)
from html_parser import (
    extract_data,
    get_rows_lenght,
    html_maker,
)
from models import Season
from queries import (
    get_all_season,
    get_marks_by_season,
    get_season_by_id,
    get_student,
    get_students_set,
    get_students_within_range,
    get_user_from_db,
    search_by_name_db,
    update_or_insert_students_data,
)
from schemas import StudentSchema, SubjectMarkSchema
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
from telegram.helpers import escape_markdown
from web_scrapper import multi_async_request

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
async def inline_query_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.inline_query.query
    if not query:
        return
    number = query.split()[0]
    if not validate_input([number]):
        return
    with get_session(context).begin() as session:
        seasons = get_all_season(session)
        student = get_student(session, int(number))
        if student:
            marks_within_session = get_marks_by_season(session, seasons[0], student.id)
            student_data = StudentSchema.model_validate(student)
            student_data.subjects_marks = [
                SubjectMarkSchema.model_validate(mark) for mark in marks_within_session
            ]
            output = parse_marks_to_text_from_db(student_data, context, seasons[0])
            output += (
                "\n\n⚠️ *هذه العلامات مخزنة مسبقا على البوت وقد لا تكون محدّثة، "
                "للحصول على العلامات من الموقع يرجى إرسال الرقم إلى البوت مباشرة*:\n"
                f"@{escape_markdown(context.bot.username, 2)}"
            )
        else:
            output = (
                "⚠️ *الرقم الامتحاني خاطئ، أو أن العلامات لم تصدر بعد*\n\n"
                "للتأكد، يرجى إرسال الرقم للبوت مباشرة لجلب العلامات من الموقع:\n"
                f"@{escape_markdown(context.bot.username, 2)}"
            )
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


@verify_blocked_user
async def search_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_message = update.message if update.message else update.edited_message
    text_query = update_message.text.strip()
    results = search_by_name_db(get_session(context), text_query)
    if not results:
        await update_message.reply_text(
            "عذرا، لم يتم إيجاد أي طالب بهذا الاسم، يرجى التأكد والمحاولة مجددا.",
            quote=True,
        )
        return
    return await responser(update, context, [x.university_number for x in results])


@verify_blocked_user
async def responser(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    numbers=(),
    html_bl=False,
    caption="",
):
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass  # do nothing, as it's not important
    user_id = get_user_id(update)
    user = check_and_insert_user(update, context)
    recurse_limit = 15 if user.is_whitelisted else 3
    if not numbers:
        if context.args:
            numbers = context.args
        elif query:
            numbers = (query.data,)
        elif update.edited_message:
            numbers = update.edited_message.text.split()
        else:
            numbers = update.message.text.split()
        if len(numbers) > 10 and not user.is_whitelisted and user.telegram_id != DEV_ID:
            await update.message.reply_text("يمكنك ادخال 10 ارقام كحد أقصى", quote=True)
            return
        isvalid = validate_input(numbers)
        if not isvalid:
            return await update.message.reply_text("أدخل أرقام صحيحة ...")
        numbers = list(map(int, numbers))

    if query or len(numbers) > 10 or html_bl:
        task_uuid = str(uuid4())
        coro = doing_the_work(
            update,
            context,
            user_id,
            numbers,
            task_uuid,
            html_bl,
            caption,
            user_msg_id=query.message.id if query else None,
            recurse_limit=recurse_limit,
        )
        task = asyncio.Task(coro)

        context.user_data[task_uuid] = task
        await task
    else:
        await get_stored_marks(update, context, numbers)


async def get_stored_marks(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    numbers: List[int],
    season: Optional[Season] = None,
):
    user_id = get_user_id(update)
    chat_id = update.effective_chat.id
    query = update.callback_query
    outputs_coroutines = []
    unsaved_numbers = []
    fetched_students_from_db = []

    Session = get_session(context)

    with Session() as session:
        all_seasons = get_all_season(session)
        if not season:
            season = all_seasons[0]
    with Session() as session:
        fetched_students_from_db = [
            StudentSchema.model_validate(x)
            for x in get_students_set(session, numbers, season)
        ]

    for indx, element in enumerate(all_seasons):
        if element.id == season.id:
            all_seasons.pop(indx)
            break

    for student in fetched_students_from_db:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🌐 جلب العلامات من الموقع",
                        callback_data=str(student.university_number),
                    )
                ],
            ]
            + [
                [
                    InlineKeyboardButton(
                        x.season_title,
                        callback_data=f"{student.university_number} {x.id}",
                    )
                ]
                for x in all_seasons
            ]
        )
        season_title = f"📆 *{escape_markdown(season.season_title, 2)}*\n\n\n"
        marks_output = season_title + parse_marks_to_text_from_db(
            StudentSchema.model_validate(student), context, season
        )
        if not query:
            message = context.bot.send_message(
                chat_id,
                marks_output,
                ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
        else:  # if it's a season query
            outputs_coroutines.append(query.answer())
            message = query.edit_message_text(
                marks_output,
                ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
        outputs_coroutines.append(message)

    unsaved_numbers = set(numbers) - {
        x.university_number for x in fetched_students_from_db
    }
    if unsaved_numbers:
        task_uuid = str(uuid4())
        task = asyncio.Task(
            doing_the_work(update, context, user_id, unsaved_numbers, task_uuid)
        )
        context.user_data[task_uuid] = task
        try:
            await task
        except asyncio.CancelledError:
            return
    for i, output_coro in enumerate(outputs_coroutines):
        if i and i % 5 == 0:
            await asyncio.sleep(1)
        await output_coro


@verify_blocked_user
async def send_marks_by_season(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    student_number, season_id = list(map(int, query.data.split()))
    MySession = get_session(context)
    if season_id == 0:
        season = get_all_season(MySession)[0]
    else:
        season = get_season_by_id(get_session(context), season_id)
    return await get_stored_marks(update, context, [student_number], season)


@acquire_task_or_drop
async def doing_the_work(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    numbers: list[int],
    task_uuid: str,
    html_bl: Optional[bool] = False,
    caption: Optional[str] = None,
    user_msg_id: int | None = None,
    recurse_limit=2,
):
    students_data = None
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❌ إلغاء العملية",
                    callback_data=task_uuid,
                )
            ]
        ]
    )
    message = await context.bot.send_message(
        user_id,
        "⏳ يتم جلب المعلومات من الموقع ...",
        reply_to_message_id=user_msg_id,
        reply_markup=keyboard,
    )
    try:
        gathered_results = await multi_async_request(numbers, recurse_limit)
        students_data = [extract_data(x) for x in gathered_results]

        if len(numbers) <= 5 and not html_bl:
            await send_txt_results(
                update,
                context,
                user_id,
                students_data,
                is_from_website=True,
                reply_to_msg=user_msg_id,
            )
        else:
            await message.edit_text("⌛️ يتم التحويل إلى ملف html ...")
            html_filename = html_maker(students_data)
            filename = "marks_" + str(int(random() * 100000)) + ".html"
            if not caption:
                caption = FILE_CAPTION
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

    try:
        await message.delete()
        del context.user_data[task_uuid]
    except Exception:
        pass
    if students_data is not None:
        Session = get_session(context)
        with Session() as session:
            update_or_insert_students_data(session, students_data)
            # save student data


async def send_txt_results(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    students: List[StudentSchema],
    is_from_website: bool,
    reply_to_msg: int | None = None,
):
    query = update.callback_query if update else None
    outputs_coroutines = []
    seasons = get_all_season(get_session(context))

    for student in students:
        if is_from_website:
            output = parse_marks_to_text_from_website(student)
        else:
            output = parse_marks_to_text_from_db(student, context, seasons[0])
        if student.name == "NULL" and not student.subjects_marks: 
            coro = context.bot.send_message(
                user_id,
                f"الرقم الامتحاني {student.university_number} خاطئ",
                reply_to_message_id=reply_to_msg,
            )
        else:
            send_msg_kwargs = {
                "text": output,
                "parse_mode": ParseMode.MARKDOWN_V2,
            }
            if is_from_website and student.subjects_marks:
                send_msg_kwargs["reply_markup"] = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "إظهار الترتيب",
                                callback_data="{} {}".format(
                                    student.university_number,
                                    0,  # zero means get last season
                                ),
                            )
                        ]
                    ]
                )
            if query:
                coro = query.edit_message_text(**send_msg_kwargs)
            else:
                coro = context.bot.send_message(chat_id=user_id, **send_msg_kwargs)
        outputs_coroutines.append(coro)

    for i, coro in enumerate(outputs_coroutines):
        if i and i % 5 == 0:
            await asyncio.sleep(1)
        await coro


async def cancel_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        context.user_data[query.data].cancel()
        await query.message.edit_reply_markup()
        await query.answer("تم إلغاء العملية بنجاح!")
        del context.user_data[query.data]
    except Exception:
        await query.answer("لقد تم إلغاء هذه العملية مسبقا", show_alert=True)


# some redirecting functions
@verify_blocked_user
async def html_it(*args):
    await responser(*args, html_bl=True)


@verify_blocked_user
async def danger_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = get_user_id(update)
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
    elif not validate_input([context.args[0]]):
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
    user_id = get_user_id(update)

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
            student = extract_data(gathered_results[0])
            await send_txt_results(
                None, context, user_id, [student], is_from_website=True
            )

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
    user_id = get_user_id(update)
    user = get_user_from_db(get_session(context), user_id)
    if (user_id == DEV_ID) or (user and user.is_whitelisted):
        start_number, end_number = map(int, context.args)
        return await responser(
            update, context, [i for i in range(start_number, end_number + 1)], True
        )


async def lazy_in_range(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = get_user_id(update)
    user = get_user_from_db(get_session(context), user_id)
    if not ((user_id == DEV_ID) or (user and user.is_whitelisted)):
        return
    context.application.create_task(lazy_in_range_task(update, context))
    await update.message.reply_text("task has been started...")


async def lazy_in_range_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = get_user_id(update)
    start_number, end_number, time_offset = map(int, context.args)
    all_numbers = {i for i in range(start_number, end_number + 1)}
    Session = get_session(context)
    first_start = time.time()
    after_date = datetime.now(timezone.utc) - timedelta(minutes=time_offset)

    with Session() as session:
        season = get_all_season(session)[0]
        updated_students = get_students_within_range(
            session, start_number, end_number, after_date, season
        )

        await update.message.reply_text(
            "there is {} from {} has been retrived from db, time taken: {}".format(
                len(updated_students), len(all_numbers), time.time() - first_start
            )
        )
    unsaved_numbers = all_numbers - {x.university_number for x in updated_students}
    if unsaved_numbers:
        start = time.time()
        responses = await multi_async_request(unsaved_numbers, 15)
        all_students = [extract_data(x) for x in responses]
        with Session() as session:
            update_or_insert_students_data(session, all_students)  ####
        await update.message.reply_text(
            "there's {} fethed from the website, time taken: {}".format(
                len(unsaved_numbers), time.time() - start
            )
        )

    after_date = datetime.now(timezone.utc) - timedelta(
        minutes=time_offset, seconds=(time.time() - first_start) + 1
    )
    with Session() as session:
        start = time.time()
        # refetch data after updates and inserts
        all_students = [
            x
            for x in get_students_within_range(
                session,
                start_number,
                end_number,
                after_date,
                season,
            )
        ]
    await update.message.reply_text("generating html file...")
    html_filename = html_maker(all_students)
    await update.message.reply_text("done, time taken: {}".format(time.time() - start))
    filename = "marks_" + str(int(random() * 100000)) + ".html"
    caption = FILE_CAPTION
    caption += "\n{} \\- {}".format(start_number, end_number)
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
    await update.message.reply_text(
        START_MESSAGE, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True
    )


def get_token() -> str:
    # Priority to environment variables
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
    application = (
        Application.builder()
        .token(token)
        .concurrent_updates(ConcurentUpdateProcessor(256, max_updates_per_user=5))
        .build()
    )
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("send_message", send_message)],
        states={
            1: [MessageHandler(~filters.COMMAND, get_public_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )
    application.add_handler(conv_handler)
    uuid4_pattern = re.compile(
        r"^[a-f0-9]{8}-?[a-f0-9]{4}-?4[a-f0-9]{3}-?[89ab][a-f0-9]{3}-?[a-f0-9]{12}$",
        re.I,
    )
    arabic_text_pattern = re.compile(r"^[\u0621-\u064A\s]+$")
    application.add_handlers(
        [
            CommandHandler(["start", "help"], start),
            CommandHandler("html", html_it),
            CommandHandler("send_db_backup", send_db_now),
            CommandHandler("danger", danger_mode),
            CommandHandler("cancel_danger", cancel_danger),
            CommandHandler("in_range", in_range),
            CommandHandler("lazy_in_range", lazy_in_range),
            CommandHandler("exec", exec_command),
            CommandHandler("get_db_len", get_total_users),
            CommandHandler("update_database", update_database),
            CommandHandler("add_white_list", add_to_white_list),
            CommandHandler("remove_white_list", remove_white_list),
            CommandHandler("add_admin", add_new_admin),
            CommandHandler("remove_admin", remove_admin),
            CommandHandler("block_user", block_user),
            CommandHandler("unblock_user", unblock_user),
            CommandHandler("get_from_db_by_student_id", get_from_db_by_student_id),
            CommandHandler("get_from_db_by_subject", get_from_db_by_subject),
            CommandHandler("download_this_file", download_this_file),
            CommandHandler("get_all_subjects", get_all_subjects),
            CommandHandler("delete_all_students", delete_all_students),
            CommandHandler("admin_help", admin_help_message),
            CommandHandler("add_season", add_new_season),
            InlineQueryHandler(inline_query_handler),
            MessageHandler(filters.Regex(arabic_text_pattern), callback=search_by_name),
            MessageHandler(filters.TEXT & ~filters.COMMAND, callback=responser),
            CallbackQueryHandler(responser, pattern=re.compile(r"^\d{1,5}$")),
            CallbackQueryHandler(
                send_marks_by_season, pattern=re.compile(r"^\d{1,5} \d{1,3}$")
            ),
            CallbackQueryHandler(cancel_task_handler, pattern=uuid4_pattern),
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
