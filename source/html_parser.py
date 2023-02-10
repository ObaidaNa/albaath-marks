import json
from lxml import etree
from telegram.helpers import escape_markdown
from random import shuffle


def initialize_table():
    root = etree.Element("html", dir="rtl")
    head = etree.SubElement(root, "head")
    etree.SubElement(
        head, "meta", http_equiv="Content-Type", content="text/html; charset=UTF-8")
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
    with open('config.json', 'r') as f:
        h1.text = json.load(f).get('HTML_sign')
    table = etree.SubElement(body, "table")
    nfrow = etree.fromstring(nfrowhtml)
    table.append(nfrow)
    return root


def html_maker(students):

    root = initialize_table()
    table = root.xpath('//table')[0]
    cnt = 0
    cnt2 = 0
    for student in students:
        parser = etree.HTMLParser(encoding='utf-8')
        doc = etree.fromstring(student['html'].decode('cp1256'), parser)
        rows = doc.xpath("//table//tr")
        if len(rows) == 2:
            continue
        cnt += 1
        fr_style = '''
        text-align: center;
        color: white;
        background-color: #760000;
        '''
        base_row = etree.Element('tr')
        frow = rows[0].xpath('.//td')[0]
        frow.attrib['style'] = fr_style
        st_name = f"{frow.text} - {student['number']}"
        sub_name = etree.Element('td')
        sub_name.set('rowspan', str(len(rows) - 2))
        sub_name.text = st_name
        if cnt % 2:
            sub_name.set('style', 'background-color: #8EA7E9')
        base_row.append(sub_name)
        style = "background-color: {}"
        for row in rows[2:]:
            cnt2 += 1
            cells = row.xpath(".//td")
            if len(cells) == 4:
                if cells[3].text.isdigit():
                    score = float(cells[3].text)
                    if score < 60:
                        cells[3].attrib["style"] = style.format("#ff8383")
                    else:
                        cells[3].attrib["style"] = style.format("#9efcd6")
            for j, cell in enumerate(cells):
                if j < len(cells) - 1:
                    cell.attrib['style'] = 'background-color: #FFF2F2;' if cnt2 % 2 else "background-color: #E5E0FF;"
                base_row.append(cell)
            table.append(base_row)
            base_row = etree.Element('tr')
    return etree.tostring(root)


def parse_to_text(html_content: bytes, number: str) -> str:
    books = ['📕', '📗', '📘', '📙']
    shuffle(books)
    parser = etree.HTMLParser(encoding='utf-8')
    doc = etree.fromstring(html_content.decode('cp1256'), parser)
    rows = doc.xpath("//table//tr")
    if len(rows) <= 2:
        return ''

    output = ["👤 *", escape_markdown(rows[0].xpath('.//td')[0].text,
                                     version=2) + f" \- {number} *:\n\n"]
    for i, row in enumerate(rows[2:]):
        columns = row.xpath('.//td')
        output.append(f"{books[i % len(books)]} _*")
        output.append(escape_markdown(
            f"({columns[0].text})", version=2) + "*_\n")
        for index, column in enumerate(columns[1:]):
            output += f"_{column.text}_ " if index != 2 else f"*{column.text}*"
            if index == 2 and str(column.text).isnumeric():
                output.append(" ✅" if int(column.text) >= 60 else " ❌")
        output.append(escape_markdown("\n-----------\n", version=2))
    return "".join(output)
