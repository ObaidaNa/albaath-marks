import json
import os

DANGER_TIME_DURATION = 60
DEV_ID = os.getenv("DEV_ID", 668270522)
DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME", "marks_bot_db.sqlite3")
DATABASE_URL = "sqlite:///{}".format(DATABASE_NAME)

WARINNG_MESSAGE = """
> **إن كل ما يصدر من بوت العلامات أو قناة بوت العلامات هو مجرد عمل طلابي وغير رسمي**،
> **وشعبة الامتحانات غير مسؤولة عنه وقد لا تكون المعلومات صحيحة.**
> **بما في ذلك العلامات التي يرسلها البوت، أو ملفات ال pdf التي فيها العلامات، كلها غير رسمية.**
> 
> **لذلك فإن المرجع الصحيح والموثوق هو فقط موقع العلامات الرسمي، أو ما يصدر من شعبة الامتحانات**
"""

START_MESSAGE = ""
with open("config.json", "r", encoding="utf-8") as f:
    dc = json.load(f)
    START_MESSAGE = dc["start"]
    FILE_CAPTION = dc.get("caption")
    HTML_SIGN = dc.get("HTML_sign")
