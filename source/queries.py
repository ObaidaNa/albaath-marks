from datetime import datetime
from typing import Iterable, List, Optional

from models import BotUser, Season, Student, SubjectMark, SubjectName, session_wrapper
from schemas import (
    StudentCreate,
    SubjectMarkSchema,
    SubjectNameCreateSchema,
    SubjectNameSchema,
)
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
def get_marks_by_subject(
    session: Session, subject_id: int, season: Season
) -> List[SubjectMark]:
    stmt = (
        select(SubjectMark)
        .join(Student)
        .where(SubjectMark.subject_id == subject_id)
        .where(SubjectMark.last_update.between(season.from_date, season.to_date))
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
def get_student_rank_by_subject(
    session: Session, student_mark: SubjectMarkSchema, season: Season
) -> int:
    stmt = (
        select(func.count())
        .select_from(SubjectMark)
        .where(SubjectMark.subject_id == student_mark.subject.id)
        .where(SubjectMark.last_update.between(season.from_date, season.to_date))
        .where(SubjectMark.total > student_mark.total)
    )

    return int(session.execute(stmt).one()[0]) + 1


@session_wrapper
def insert_or_update_mark(session: Session, new_marks: SubjectMark):
    subject_mark = get_subject_mark(session, new_marks.student_id, new_marks.subject_id)
    if not subject_mark:
        session.add(new_marks)
        return new_marks
    subject_mark.amali = new_marks.amali
    subject_mark.nazari = new_marks.nazari
    subject_mark.total = new_marks.total
    subject_mark.last_update = func.now()
    session.refresh(subject_mark, ["subject"])
    return subject_mark


@session_wrapper
def get_student(session: Session, university_id: int) -> Optional[Student]:
    stmt = (
        select(Student)
        .where(Student.university_number == university_id)
        .options(selectinload(Student.subjects_marks))
    )
    return session.scalars(stmt).first()


@session_wrapper
def get_students_within_range(
    session: Session, start: int, end: int, after_date: datetime, season: Season
) -> List[Student]:
    stmt = (
        select(
            Student,
        )
        .where(Student.university_number.between(start, end))
        .where(Student.last_update >= after_date)
        .options(
            selectinload(
                Student.subjects_marks.and_(
                    SubjectMark.last_update.between(
                        season.from_date,
                        season.to_date,
                    )
                )
            )
        )
        .order_by(Student.university_number)
    )
    return session.scalars(stmt).all()


@session_wrapper
def get_students_set(session: Session, students_numbers: Iterable[int], season: Season):
    stmt = (
        select(Student)
        .where(Student.university_number.in_(students_numbers))
        .options(
            selectinload(
                Student.subjects_marks.and_(
                    SubjectMark.last_update.between(season.from_date, season.to_date)
                )
            )
        )
    )
    return session.scalars(stmt).all()


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


@session_wrapper
def search_by_name_db(session: Session, name: str, limit: int = 5) -> List[Student]:
    stmt = select(Student).where(Student.name.regexp_match(name)).limit(limit)
    return session.scalars(stmt).all()


@session_wrapper
def get_marks_by_season(
    session: Session, season: Season, student_id: int
) -> List[SubjectMark]:
    stmt = (
        select(SubjectMark)
        .where(SubjectMark.student_id == student_id)
        .where(SubjectMark.last_update >= season.from_date)
        .where(SubjectMark.last_update <= season.to_date)
    )
    return session.scalars(stmt).all()


@session_wrapper
def get_all_season(session: Session) -> List[Season]:
    stmt = select(Season).order_by(Season.to_date.desc())
    seasons = session.scalars(stmt).all()
    if not seasons:
        return [
            Season(
                season_title="كل العلامات",
                from_date=datetime(2000, 1, 1),
                to_date=datetime(3000, 1, 1),
            )
        ]
    return seasons


@session_wrapper
def get_season_by_id(session: Session, season_id: int) -> Season:
    stmt = select(Season).where(Season.id == season_id)
    return session.scalars(stmt).one()


@session_wrapper
def get_all_subjects(session: Session) -> List[SubjectName]:
    stmt = select(SubjectName).order_by(SubjectName.name)
    return session.scalars(stmt).all()


def update_or_insert_students_data(session: Session, students: List[StudentCreate]):
    """
    insert/update student data, include new subjects, marks, students
    """
    subjects = {}
    # check if there's a new subjects and create them
    # extract unique subjects name
    for student in students:
        for subject_mark in student.subjects_marks:
            if not subjects.get(subject_mark.subject.name):
                subjects[subject_mark.subject.name] = subject_mark.subject

    # insert them
    insert_only_new_subjects(session, subjects.values())

    # refetch them from db after they've updated
    subjects = {
        x.name: SubjectNameSchema.model_validate(x) for x in get_all_subjects(session)
    }
    for student in students:
        for index, subject_mark in enumerate(student.subjects_marks):
            subj = subjects[subject_mark.subject.name]
            student.subjects_marks[index] = SubjectMarkSchema(
                **subject_mark.model_dump(),
                subject_id=subj.id,
                subject=SubjectNameSchema.model_validate(subj),
            )

    students_stmt = (
        select(Student)
        .where(Student.university_number.in_({x.university_number for x in students}))
        .options(selectinload(Student.subjects_marks, SubjectMark.subject))
    )

    existing_students = session.scalars(students_stmt).all()

    existing_set = {x.university_number for x in existing_students}

    new_students = [
        Student(
            **student.model_dump(include=["university_number", "name"]),
            subjects_marks=[
                SubjectMark(
                    **sub_mark.model_dump(),
                )
                for sub_mark in student.subjects_marks
            ],
        )
        for student in students
        if student.university_number not in existing_set
    ]

    session.add_all(new_students)

    session.commit()
    hashed_students = {x.university_number: x for x in students}

    for student in existing_students:
        student.last_update = func.now()
        marks = {
            subject_mark.subject.name: subject_mark
            for subject_mark in hashed_students[
                student.university_number
            ].subjects_marks
        }
        for subject_mark in student.subjects_marks:
            mark = marks.get(subject_mark.subject.name)
            if mark:
                subject_mark.nazari = mark.nazari
                subject_mark.amali = mark.amali
                subject_mark.total = mark.total
                subject_mark.last_update = func.now()
                del marks[subject_mark.subject.name]

        student.subjects_marks.extend(
            [SubjectMark(**mark.model_dump()) for mark in marks.values()]
        )

    session.commit()


@session_wrapper
def insert_only_new_subjects(session: Session, subjects: List[SubjectNameCreateSchema]):
    db_subjects = [row.name for row in get_all_subjects(session)]

    to_insert = [
        SubjectName(name=x.name) for x in subjects if x.name not in db_subjects
    ]
    session.add_all(to_insert)
    session.commit()
