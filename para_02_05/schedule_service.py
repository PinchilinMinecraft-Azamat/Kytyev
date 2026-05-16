from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from re import IGNORECASE, DOTALL, search, sub
from urllib.request import Request, urlopen


SCHEDULE_URL = "http://schedule.ckstr.ru/cg133.htm"


@dataclass
class Lesson:
    date: str
    day: str
    pair: int
    group: str
    subject: str
    kind: str
    room: str
    teacher: str
    subgroup: str


class ScheduleTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.in_schedule_table = False
        self.table_level = 0
        self.current_row = None
        self.current_cell = None
        self.current_link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "table":
            class_name = attrs.get("class", "")
            if "inf" in class_name.split() and not self.in_schedule_table:
                self.in_schedule_table = True
                self.table_level = 1
                return
            if self.in_schedule_table:
                self.table_level += 1

        if not self.in_schedule_table:
            return

        if tag == "tr":
            self.current_row = []

        if tag in ("td", "th") and self.current_row is not None:
            self.current_cell = {
                "class": attrs.get("class", ""),
                "rowspan": int(attrs.get("rowspan", 1)),
                "colspan": int(attrs.get("colspan", 1)),
                "text": [],
                "z1": [],
                "z2": [],
                "z3": [],
            }

        if tag == "a" and self.current_cell is not None:
            class_name = attrs.get("class", "")
            if class_name in ("z1", "z2", "z3"):
                self.current_link = class_name

    def handle_data(self, data):
        if self.current_cell is None:
            return

        self.current_cell["text"].append(data)
        if self.current_link:
            self.current_cell[self.current_link].append(data)

    def handle_endtag(self, tag):
        if not self.in_schedule_table:
            return

        if tag == "a":
            self.current_link = None

        if tag in ("td", "th") and self.current_cell is not None:
            self.current_row.append(self.current_cell)
            self.current_cell = None

        if tag == "tr" and self.current_row is not None:
            self.rows.append(self.current_row)
            self.current_row = None

        if tag == "table":
            self.table_level -= 1
            if self.table_level == 0:
                self.in_schedule_table = False


def load_html():
    request = Request(SCHEDULE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=10) as response:
        return response.read().decode("windows-1251", errors="ignore")


def clean_text(value):
    return " ".join(value.replace("\xa0", " ").split())


def strip_tags(value):
    return clean_text(sub(r"<[^>]+>", " ", value))


def get_group_name(html):
    title = search(r"<h1[^>]*>(.*?)</h1>", html, IGNORECASE | DOTALL)
    text = strip_tags(title.group(1)) if title else "Группа"
    return text.replace("Группа:", "").strip() or "Группа"


def get_update_time(html):
    result = search(r"Обновлено:\s*([^<\n\r]+)", html, IGNORECASE | DOTALL)
    if not result:
        return "не указано"
    return clean_text(result.group(1)).rstrip(".")


def get_day_name(cell_text):
    names = {
        "Пн": "Понедельник",
        "Вт": "Вторник",
        "Ср": "Среда",
        "Чт": "Четверг",
        "Пт": "Пятница",
        "Сб": "Суббота",
        "Вс": "Воскресенье",
    }
    parts = cell_text.split()
    if len(parts) < 2:
        return ""
    short_name = parts[1].split("-")[0]
    return names.get(short_name, short_name)


def get_lesson_kind(subject):
    text = subject.upper().replace(" ", "")
    if text.startswith("УП") or "УП" in text:
        return "УП"
    if "ПРАК" in text:
        return "Практика"
    if "ЛЕК" in text:
        return "Лекция"
    return "Занятие"


def parse_schedule(html):
    parser = ScheduleTableParser()
    parser.feed(html)

    group = get_group_name(html)
    lessons = []
    current_date = ""
    current_day = ""

    for row in parser.rows:
        if not row:
            continue

        first_text = clean_text(" ".join(row[0]["text"]))
        date_found = search(r"\d{2}\.\d{2}\.\d{4}", first_text)

        start = 0
        if date_found and row[0]["rowspan"] > 1:
            current_date = date_found.group(0)
            current_day = get_day_name(first_text)
            start = 1

        if len(row) <= start:
            continue

        pair_text = clean_text(" ".join(row[start]["text"]))
        if not pair_text.isdigit():
            continue

        pair = int(pair_text)
        lesson_cells = row[start + 1:]
        part_number = 1

        for cell in lesson_cells:
            subject = clean_text(" ".join(cell["z1"]))
            if not subject:
                part_number += cell["colspan"]
                continue

            subgroup = "вся группа"
            if cell["colspan"] == 1 and len(lesson_cells) > 1:
                subgroup = f"{part_number} подгруппа"

            lessons.append(
                Lesson(
                    date=current_date,
                    day=current_day,
                    pair=pair,
                    group=group,
                    subject=subject,
                    kind=get_lesson_kind(subject),
                    room=clean_text(" ".join(cell["z2"])),
                    teacher=clean_text(" ".join(cell["z3"])),
                    subgroup=subgroup,
                )
            )
            part_number += cell["colspan"]

    lessons.sort(key=lambda item: (datetime.strptime(item.date, "%d.%m.%Y"), item.pair, item.subgroup))
    return lessons


def get_schedule():
    html = load_html()
    return {
        "lessons": parse_schedule(html),
        "updated": get_update_time(html),
        "source": SCHEDULE_URL,
    }
