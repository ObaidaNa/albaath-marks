from datetime import datetime

from pydantic import BaseModel, Field


class SubjectNameBaseSchema(BaseModel):
    name: str


class SubjectNameCreateSchema(SubjectNameBaseSchema):
    pass

    class Config:
        from_attributes = True


class SubjectNameSchema(SubjectNameCreateSchema):
    id: int

    class Config:
        from_attributes = True


class SubjectMarkBaseSchema(BaseModel):
    nazari: int
    amali: int
    total: int


class SubjectMarkCreateSchema(SubjectMarkBaseSchema):
    subject: SubjectNameCreateSchema = Field(exclude=True)


class SubjectMarkSchema(SubjectMarkBaseSchema):
    subject_id: int
    subject: SubjectNameSchema = Field(exclude=True)

    class Config:
        from_attributes = True


class StudentBaseSchema(BaseModel):
    name: str
    university_number: int


class StudentCreate(StudentBaseSchema):
    subjects_marks: list[SubjectMarkCreateSchema] = []


class StudentSchema(StudentBaseSchema):
    id: int
    last_update: datetime
    subjects_marks: list[SubjectMarkSchema | SubjectMarkCreateSchema] = []

    class Config:
        from_attributes = True
