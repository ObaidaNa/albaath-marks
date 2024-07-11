import functools
from datetime import datetime
from typing import List, Optional, Union

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    SessionTransaction,
    mapped_column,
    relationship,
    sessionmaker,
)


def session_wrapper(func):
    @functools.wraps(func)
    def inner_func(
        my_session: Union[sessionmaker[Session], SessionTransaction, Session],
        *args,
        **kwargs,
    ):
        if isinstance(my_session, (Session, SessionTransaction)):
            return func(my_session, *args, **kwargs)
        with my_session.begin() as session:
            result = func(session, *args, **kwargs)
        return result

    return inner_func


class Base(DeclarativeBase):
    pass


class BotUser(Base):
    __tablename__ = "bot_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)

    fullname: Mapped[str] = mapped_column(String(255))
    username: Mapped[Optional[str]] = mapped_column(String(55), nullable=True)
    join_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    is_blocked: Mapped[bool] = mapped_column(default=False)
    is_admin: Mapped[bool] = mapped_column(default=False)
    is_whitelisted: Mapped[bool] = mapped_column(default=False)


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    university_number: Mapped[int] = mapped_column(
        nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(length=255))
    last_update: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=func.now(), onupdate=func.now()
    )

    subjects_marks: Mapped[List["SubjectMark"]] = relationship(back_populates="student")


class SubjectName(Base):
    __tablename__ = "subjects_name"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(length=255), nullable=False, unique=True)

    subject_marks: Mapped[List["SubjectMark"]] = relationship(back_populates="subject")


class SubjectMark(Base):
    __tablename__ = "subject_marks"
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects_name.id"), primary_key=True
    )
    nazari: Mapped[int] = mapped_column(default=0)
    amali: Mapped[int] = mapped_column(default=0)
    total: Mapped[int] = mapped_column(default=0)
    last_update: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=func.now(), onupdate=func.now
    )

    student: Mapped[Student] = relationship(back_populates="subjects_marks")
    subject: Mapped[SubjectName] = relationship(
        back_populates="subject_marks", lazy="selectin"
    )


class Season(Base):
    __tablename__ = "seasons"
    id: Mapped[int] = mapped_column(primary_key=True)
    season_title: Mapped[str] = mapped_column(String(length=255), nullable=True)
    from_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    to_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
