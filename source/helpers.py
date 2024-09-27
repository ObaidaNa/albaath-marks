import logging
import random
from io import BytesIO
from typing import List, Optional

from constants import DATABASE_URL, WARINNG_MESSAGE
from models import Base, BotUser, Season, SubjectMark, SubjectName
from queries import get_student_rank_by_subject, get_user_from_db, insert_user, is_exist
from schemas import StudentCreate, StudentSchema, SubjectMarkCreateSchema
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

logger = logging.getLogger(__name__)


def get_session(context: ContextTypes.DEFAULT_TYPE) -> sessionmaker[Session]:
    MySession: sessionmaker[Session] = context.bot_data["db_session"]
    return MySession


def convert_makrs_to_md_file(
    subject: SubjectName, marks: List[SubjectMark], bot_username: str
) -> bytes:
    sorted_marks = sorted(marks, key=lambda x: x.total, reverse=True)
    students_rank = {}
    rank_cnt, tmp_cnt, last_mark = 0, 0, 9999
    for mark in sorted_marks:
        tmp_cnt += 1
        if last_mark != mark.total:
            rank_cnt += tmp_cnt
            last_mark = mark.total
            tmp_cnt = 0

        students_rank[mark.student_id] = rank_cnt

    lst = [
        "# {}\n\n\n\n".format(subject.name),
        "## تنبيه:\n\n{}\n---\n\n\n\n".format(WARINNG_MESSAGE),
        "| الترتيب | الاسم  | الرقم الجامعي | العملي | النظري | المجموع |\n",
        "| ---- | ----- | ----- | ----- | ---- | ----- |\n",
    ]
    passed_cnt = 0
    for mark in marks:
        lst.append(
            "| {} | {} | {} | _{}_ | _{}_ | **{}** |\n".format(
                students_rank[mark.student_id],
                mark.student.name,
                mark.student.university_number,
                mark.amali,
                mark.nazari,
                mark.total,
            )
        )
        if mark.total >= 60:
            passed_cnt += 1
    success_rate = round(passed_cnt / len(marks) * 100, 2)
    lst.append("\n\n# نسبة النجاح: {}\n".format(success_rate))
    lst.append("- العدد الكلي: {}\n".format(len(marks)))
    lst.append("- عدد الناجحين: {}\n\n".format(passed_cnt))
    lst.append("# By: [@{}](https://t.me/{})\n\n".format(bot_username, bot_username))
    lst.append("# قناة البوت: https://t.me/albaath_marks\n---")
    output = "".join(lst)
    with BytesIO() as f:
        f.write(output.encode())
        filebytes = f.getvalue()
    return filebytes


def verify_blocked_user(func):
    async def inner_func(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ):
        user_id = update.effective_user.id
        user = get_user_from_db(get_session(context), user_id)
        if user and user.is_blocked:
            return
        return await func(update, context, *args, **kwargs)

    return inner_func


def init_database(bot_data: dict):
    logger.info("initializing the database...")

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(engine, expire_on_commit=False)

    with Session() as conn:
        Base.metadata.create_all(engine)
        conn.commit()

    bot_data["db_session"] = Session
    logger.info("database initializing has finished successfully...")


def check_and_insert_user(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> BotUser:
    DbSession = get_session(context)

    query = update.callback_query
    tg_user = query.from_user if query else None
    if update.message:
        tg_user = update.message.from_user
    elif update.edited_message:
        tg_user = update.edited_message.from_user
    with DbSession.begin() as session:
        if not is_exist(session, tg_user.id):
            insert_user(
                session,
                tg_user.id,
                tg_user.full_name,
                tg_user.username,
            )
    user = get_user_from_db(DbSession, tg_user.id)
    return user


def parse_marks_to_text_from_website(student: StudentCreate) -> str:
    marks = student.subjects_marks
    marks.sort(key=lambda x: x.subject.name)
    books = ["📕", "📗", "📘", "📙"]
    random.shuffle(books)
    if len(marks) == 0:
        return ""

    output = [
        "👤 *",
        escape_markdown(student.name, version=2)
        + f" \- {student.university_number} *:\n\n",
    ]
    for i, subject in enumerate(marks):
        output.append(f"{books[i % len(books)]} _*")
        output.append(escape_markdown(f"({subject.subject.name})", version=2) + "*_\n")
        output.append(f"_{subject.amali}_ ")
        output.append(f"_{subject.nazari}_ ")
        output.append(f"*{subject.total}* ")
        if str(subject.total).isnumeric():
            output.append(" ✅" if int(subject.total) >= 60 else " ❌")
        output.append(escape_markdown("\n-----------\n", version=2))

    output.append("\n> *من الموقع* ✔️\n")
    output.append("\n> *By*: @albaath\\_marks\\_bot")
    return "".join(output)


def parse_marks_to_text_from_db(
    student: StudentSchema, context: ContextTypes.DEFAULT_TYPE, season: Season
) -> str:
    marks = student.subjects_marks
    marks.sort(key=lambda x: x.subject.name)
    books = ["📕", "📗", "📘", "📙"]
    random.shuffle(books)
    output = [
        "👤 *",
        escape_markdown(student.name, version=2)
        + f" \- {student.university_number} *:\n\n",
    ]

    if len(marks) == 0:
        return "".join([*output, "\n📭 لا يوجد علامات حاليا"])

    Session = get_session(context)
    with Session.begin() as session:
        for i, subject in enumerate(marks):
            output.append(f"{books[i % len(books)]} _*")
            output.append(
                escape_markdown(f"({subject.subject.name})", version=2) + "*_\n"
            )
            output.append(f"_{subject.amali}_ ")
            output.append(f"_{subject.nazari}_ ")
            output.append(f"*{subject.total}* ")
            if str(subject.total).isnumeric():
                output.append(" ✅" if int(subject.total) >= 60 else " ❌")
            rank = get_student_rank_by_subject(session, subject, season)
            output.append("\n📊 _الترتيب_: `{}`".format(rank))
            output.append(escape_markdown("\n-----------\n", version=2))
        marks_sum = sum([x.total for x in marks])
        avg_result = str(round(marks_sum / len(marks), 3))
        output.append("\n🧮 *المعدل*: `{}`\n".format(escape_markdown(avg_result, 2)))
        output.append("\n> *By*: @albaath\\_marks\\_bot")
    return "".join(output)


def get_user_id(update: Update) -> Optional[int]:
    query = update.callback_query
    user_id = None
    if query:
        user_id = query.from_user.id
    elif update.message:
        user_id = update.message.from_user.id
    elif update.edited_message:
        user_id = update.edited_message.from_user.id

    return user_id


def acquire_task_or_drop(func):
    async def inner(update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        flag_name = "is_busy"
        if context.user_data.get(flag_name):
            return  # drop the update
        try:
            context.user_data[flag_name] = True
            ret = await func(update, context, *args, **kwargs)
        finally:
            context.user_data[flag_name] = False
        return ret

    return inner


def is_passed(marks: list[SubjectMarkCreateSchema]) -> bool:
    sorted_marks = sorted(marks, key=lambda x: x.total, reverse=True)
    help_marks = 2
    faild = 0
    for mark in sorted_marks:
        if mark.total >= 60:
            continue
        if mark.total < 60 and mark.total + help_marks >= 60:
            help_marks -= 60 - mark.total
        else:
            faild += 1
    return faild < 5
