from typing import List, Optional

from models import BotUser, Student, SubjectMark, SubjectName, session_wrapper
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session, selectinload


@session_wrapper
def is_exist(session: Session, user_id: int):
    stmt = select(BotUser).where(BotUser.telegram_id == user_id)
    user = session.scalars(stmt).first()
    return bool(user)


@session_wrapper
def get_user_from_db(session: Session, telegram_id: int):
    stmt = select(BotUser).where(BotUser.telegram_id == telegram_id)
    user = session.scalars(stmt).first()
    return user


@session_wrapper
def insert_user(
    session: Session, telegram_id: int, fullname: Optional[str], username: Optional[str]
):
    stmt = insert(BotUser).values(
        telegram_id=telegram_id, fullname=fullname, username=username
    )
    session.execute(stmt)


@session_wrapper
def get_all_users(session: Session) -> List[BotUser]:
    return session.scalars(select(BotUser)).all()


@session_wrapper
def get_subject_by_name(session: Session, name: str) -> Optional[SubjectName]:
    stmt = select(SubjectName).where(SubjectName.name == name)
    return session.scalars(stmt).first()


@session_wrapper
def get_marks_by_subject(session: Session, subject_id: int) -> List[SubjectMark]:
    stmt = (
        select(SubjectMark)
        .join(Student)
        .where(SubjectMark.subject_id == subject_id)
        .order_by(Student.name)
    )
    return session.scalars(stmt).all()


@session_wrapper
def db_get_all_subjects(session: Session) -> List[SubjectName]:
    stmt = select(SubjectName).order_by(SubjectName.name)
    return session.scalars(stmt).all()


@session_wrapper
def insert_subject(session: Session, name: str) -> SubjectName:
    subject = SubjectName(name=name)
    session.add(subject)
    return subject


@session_wrapper
def get_subject_mark(
    session: Session, student_id: int, subject_id: int
) -> Optional[SubjectMark]:
    stmt = (
        select(SubjectMark)
        .where(SubjectMark.student_id == student_id)
        .where(SubjectMark.subject_id == subject_id)
        .options(
            selectinload(SubjectMark.subject),
        )
    )
    return session.scalars(stmt).first()


@session_wrapper
def insert_or_update_mark(session: Session, new_marks: SubjectMark):
    subject_mark = get_subject_mark(session, new_marks.student_id, new_marks.subject_id)
    if not subject_mark:
        session.add(new_marks)
        return new_marks
    subject_mark.amali = new_marks.amali
    subject_mark.nazari = new_marks.nazari
    subject_mark.total = new_marks.total

    return subject_mark


@session_wrapper
def get_student(session: Session, university_id: int) -> Optional[Student]:
    stmt = select(Student).where(Student.university_number == university_id)
    return session.scalars(stmt).first()


@session_wrapper
def insert_or_update_student(
    session: Session, new_student: Student, update_time: bool = False
) -> Student:
    db_student = get_student(session, new_student.university_number)

    if not db_student:
        session.add(new_student)
        return new_student

    db_student.name = new_student.name
    if update_time:
        db_student.last_update = func.now()
    return db_student


@session_wrapper
def db_delete_all_marks(session: Session):
    stmt = sql_delete(SubjectMark)
    session.execute(stmt)


@session_wrapper
def db_delete_all_subjects(session: Session):
    stmt = sql_delete(SubjectName)
    session.execute(stmt)


@session_wrapper
def db_delete_all_students(session: Session):
    stmt = sql_delete(Student)
    session.execute(stmt)