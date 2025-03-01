import logging
from fpdf import FPDF, FontFace
from io import BytesIO
from models import SubjectName, SubjectMark
from typing import List
WARNING_MESSAGE = """
 تنبيه:
 إن كل ما يصدر من بوت العلامات أو قناة بوت العلامات هو مجرد عمل طلابي وغير رسمي،
 وشعبة الامتحانات غير مسؤولة عنه وقد لا تكون المعلومات صحيحة.
 بما في ذلك العلامات التي يرسلها البوت، أو ملفات ال pdf التي فيها العلامات، كلها غير رسمية.
 لذلك فإن المرجع الصحيح والموثوق هو فقط موقع العلامات الرسمي، أو ما يصدر من شعبة الامتحانات.
 
 
"""

logging.getLogger('fontTools.subset').level = logging.WARN

# Pdf color themes 
def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2],16) for i in range(0,2,4))
themes = {
    "light": {
        "background":"#ffffff",
        "second_background":"#e6e6e6",
        "text":"#333333",
        "link":"#db4d52",
        "border":"#b4b4b4",     
        "first_row":"#d0d0d0" 
    }
}

def convert_marks_to_pdf_file(
    subject: SubjectName, marks: List[SubjectMark], bot_username: str
) -> bytes:
    current_theme = themes["light"]
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


    table_head = ("المجموع","النظري","العملي ","الرقم الجامعي ","الاسم","الترتيب")
    data_table = [ table_head ] 
    passed_cnt = 0
    for mark in marks:
        data_table.append((
                mark.total,
                mark.nazari,
                mark.amali,
                mark.student.university_number,
                mark.student.name,
                students_rank[mark.student_id],
            ))
        if mark.total >= 60:
            passed_cnt += 1
    
    # creating the pdf   
    pdf = FPDF()
    # add font 
    # NOTE: Arabic don't work with this Italic font
    pdf.add_font("MyFont","",fname="./source/fonts/Vazir.ttf")
    pdf.add_font("MyFont","B",fname="./source/fonts/Vazir-Bold.ttf")
    pdf.add_font("MyFont","I",fname="./source/fonts/DejaVuSerif-Italic.ttf")
    pdf.set_font("MyFont", size=10)
    pdf.set_text_shaping(True)
    pdf.set_page_background(hex_to_rgb(current_theme["background"]))
    pdf.add_page()
    pdf.set_text_color(current_theme["text"])
    pdf.set_font_size(20)
    pdf.cell(text=subject.name, align="C", center=True, ln=1) 
    pdf.set_font_size(12)
    pdf.multi_cell(text=WARNING_MESSAGE, w=0, h=7, align="R")
    pdf.set_font_size(10) 
    # Blue line
    pdf.set_line_width(1)
    pdf.set_draw_color(current_theme["link"])
    pdf.line(x1=200, y1=25, x2=200, y2=60)

    # Grey line
    pdf.set_line_width(0.5)
    pdf.set_draw_color(current_theme["border"])
    pdf.line(x1=30, y1=65 , x2=180, y2 = 65)
    pdf.set_line_width(0.2)

    style = FontFace(color=current_theme["text"], fill_color=current_theme["background"])
    style2 = FontFace(color=current_theme["text"], fill_color=current_theme["second_background"])


    # Creat marks table
    pdf.set_draw_color(current_theme["border"])

    row_number = int(0)
    with pdf.table(text_align="center", col_widths=(15,10,10,15,30,20)) as table:
        for data_row in data_table:
            row_number = row_number + 1 
            row_style = style2 if row_number % 2 else style 
            row = table.row()
            cell_number = int(0)
            for data_cell in data_row:
                cell_number = cell_number + 1
                cell_style = FontFace(color=row_style.color, fill_color=row_style.fill_color)
                if row_number ==1:
                    cell_style.fill_color = current_theme["first_row"]
                if cell_number == 1:
                    cell_style.emphasis = "B"
                elif (cell_number == 2 or cell_number == 3) and row_number != 1:
                    cell_style.emphasis = "I"
                row.cell(str(data_cell), style=cell_style)

    # Add Extra info at the end of the pdf file
    pdf.ln(10)
    success_rate = round(passed_cnt / len(marks) * 100, 2)
    pdf.set_font_size(20) 
    pdf.cell(text=f"نسبة النجاح: {success_rate}", w=0, align="R", ln=1)
    pdf.ln(5)
    pdf.set_font_size(15)
    pdf.cell(text=f"العدد الكلي: {len(marks)}", w=0, h=10, align="R", ln=1) 
    pdf.cell(text=f"عدد الناجحين: {passed_cnt}", w=0, h=10, align="R", ln=1)
    pdf.set_text_color(current_theme["link"])
    pdf.cell(h=10, text="https://t.me/Syria_Marks", w=pdf.epw-45, link="https://t.me/Syria_Marks" , align="R") 
    pdf.set_text_color(current_theme["text"])
    pdf.cell(text="قناة بوت العلامات:", w=45, h=10, align="R", ln=1)
    pdf.cell(text="By:" ,h=10)
    pdf.set_text_color(current_theme["link"])
    pdf.cell(h=10,text=f"@{bot_username}", w=0, link=f"https://t.me/{bot_username}") 
    pdf.set_text_color(current_theme["text"])
    
     # Grey line
    pdf.set_line_width(0.5)
    pdf.set_draw_color(current_theme["border"])
    y_position = pdf.get_y()+20
    pdf.line(x1=30, y1=y_position , x2=180, y2 = y_position)
    pdf.set_line_width(0.2)
   
    filebytes = BytesIO()
    pdf.output(filebytes) 
    return filebytes.getvalue()

