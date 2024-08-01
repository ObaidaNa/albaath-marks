from typing import List

from constants import HTML_SIGN
from helpers import is_passed
from lxml import etree
from schemas import StudentCreate, SubjectMarkCreateSchema, SubjectNameCreateSchema
from web_scrapper import WebStudentResponse


def initialize_table():
    root = etree.Element("html", dir="rtl")
    head = etree.SubElement(root, "head")
    etree.SubElement(
        head, "meta", http_equiv="Content-Type", content="text/html; charset=UTF-8"
    )
    style = etree.SubElement(head, "style")
    style.text = """
        body {
        background-color: #282828;
        background-image: url(http://www.transparenttextures.com/patterns/45-degree-fabric-light.png);
        }
        h1 {
        color: #cad6e1;
        font-size: 36px;
        margin: 40px 0 20px 0;
        text-align: center;
        }
        table {
        margin: 40px auto;
        border-collapse: collapse;
        border: 1px solid #666;
        width: 65%;
        background: #7286D3;
        table-layout: fixed;
        }
        td {
        font-size: 16px;
        text-align: center;
        padding: 6px;
        }
    """
    nfrowhtml = """
<tr>
<td style="color:#fff;background-color:#7a7a7a;font-size: 22px;">اسم المادة</td>
<td style="color:#fff;background-color:#7a7a7a;font-size: 22px;">الاسم</td>
<td style="color:#fff;background-color:#7a7a7a;font-size: 22px;">درجة العملي</td>
<td style="color:#fff;background-color:#7a7a7a;font-size: 22px;">درجة النظري</td>
<td style="color:#fff;background-color:#7a7a7a;font-size: 22px;">الدرجة النهائية</td>
</tr>
    """
    body = etree.SubElement(root, "body")
    h1 = etree.SubElement(body, "h1")
    h1.text = HTML_SIGN
    table = etree.SubElement(body, "table")
    nfrow = etree.fromstring(nfrowhtml)
    table.append(nfrow)
    return root


def extract_data(student_res: WebStudentResponse) -> StudentCreate:
    parser = etree.HTMLParser(encoding="utf-8")
    doc = etree.fromstring(student_res.html_page.decode("utf-8"), parser)
    rows = doc.xpath("//table//tr")

    student_name = str(rows[0].xpath(".//td")[0].text)
    if student_name == "None":
        student_name = "NULL"

    student_schema = StudentCreate(
        name=student_name, university_number=student_res.student_number
    )

    if len(rows) <= 2:
        return student_schema

    for i, row in enumerate(rows[2:]):
        columns = row.xpath(".//td")
        subject_name = str(columns[0].text).strip()
        subject_schema = SubjectNameCreateSchema(name=subject_name)
        amali = int(columns[1].text) if str(columns[1].text).isdigit() else 0
        nazari = int(columns[2].text) if str(columns[2].text).isdigit() else 0
        total = int(columns[3].text) if str(columns[3].text).isdigit() else 0
        subject_mark_schema = SubjectMarkCreateSchema(
            nazari=nazari, amali=amali, total=total, subject=subject_schema
        )
        student_schema.subjects_marks.append(subject_mark_schema)

    return student_schema


def get_rows_lenght(html_content: bytes) -> int:
    parser = etree.HTMLParser(encoding="utf-8")
    doc = etree.fromstring(html_content.decode("utf-8"), parser)
    rows = doc.xpath("//table//tr")
    return len(rows)


def html_maker(students: List[StudentCreate]):
    root = initialize_table()
    table = root.xpath("//table")[0]
    cnt = 0
    cnt2 = 0
    passed_students, failed_students = 0, 0

    for student in students:
        subjests = sorted(student.subjects_marks, key=lambda x: x.subject.name)
        if len(subjests) == 0:
            continue
        cnt += 1
        fr_style = """
        text-align: center;
        color: white;
        background-color: #760000;
        """
        base_row = etree.Element("tr")
        frow = etree.Element("td")
        # frow = rows[0].xpath(".//td")[0]
        frow.attrib["style"] = fr_style
        st_name = f"{str(student.name)} - {str(student.university_number)}"
        sub_name = etree.Element("td")
        sub_name.set("rowspan", str(len(subjests)))
        sub_name.text = st_name
        if cnt % 2:
            sub_name.set("style", "background-color: #8EA7E9")
        is_passed_student = is_passed(student.subjects_marks)
        if not is_passed_student:
            failed_students += 1
            sub_name.set("style", "background-color: #ff8383")
        else:
            passed_students += 1
        base_row.append(sub_name)
        style = "background-color: {}"
        for i, row in enumerate(subjests):
            cnt2 += 1
            cells = [etree.Element("td") for _ in range(4)]
            cells[0].text = row.subject.name
            cells[1].text = str(row.amali)
            cells[2].text = str(row.nazari)
            cells[3].text = str(row.total)
            score = row.total
            if score < 60:
                cells[3].attrib["style"] = style.format("#ff8383")
            else:
                cells[3].attrib["style"] = style.format("#9efcd6")

            for j, cell in enumerate(cells):
                if j < len(cells) - 1:
                    cell.attrib["style"] = (
                        "background-color: #FFF2F2;"
                        if cnt2 % 2
                        else "background-color: #E5E0FF;"
                    )
                base_row.append(cell)
            if i + 1 == len(subjests):
                base_row.attrib["style"] = (
                    "border-bottom-style: solid;"  # add border to the last row in a student rows
                )
            table.append(base_row)
            base_row = etree.Element("tr")
    body = table = root.xpath("//body")[0]
    total_students = passed_students + failed_students
    h1 = etree.SubElement(body, "h1")
    h1.text = "عدد الراسبين: {} من أصل {}".format(failed_students, total_students)
    h2 = etree.SubElement(body, "h1")
    h2.text = "نسبة الرسوب: {}%".format(
        round(failed_students / total_students * 100, 2)
    )
    return etree.tostring(root)
