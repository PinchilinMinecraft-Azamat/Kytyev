from collections import defaultdict
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from schedule_service import get_schedule


app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent)


def group_by_date(lessons):
    result = defaultdict(list)
    for lesson in lessons:
        result[lesson.date].append(lesson)
    return dict(result)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, group: str = "", date: str = "", kind: str = ""):
    error = ""

    try:
        schedule = get_schedule()
        lessons = schedule["lessons"]
        updated = schedule["updated"]
        source = schedule["source"]
    except Exception:
        lessons = []
        updated = "не удалось загрузить"
        source = ""
        error = "Расписание сейчас не получилось загрузить. Проверьте интернет или ссылку в schedule_service.py."

    groups = sorted({lesson.group for lesson in lessons})
    dates = sorted({lesson.date for lesson in lessons}, key=lambda item: datetime.strptime(item, "%d.%m.%Y"))
    kinds = sorted({lesson.kind for lesson in lessons})

    filtered = lessons
    if group:
        filtered = [lesson for lesson in filtered if lesson.group == group]
    if date:
        filtered = [lesson for lesson in filtered if lesson.date == date]
    if kind:
        filtered = [lesson for lesson in filtered if lesson.kind == kind]

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "days": group_by_date(filtered),
            "groups": groups,
            "dates": dates,
            "kinds": kinds,
            "selected_group": group,
            "selected_date": date,
            "selected_kind": kind,
            "total_count": len(lessons),
            "shown_count": len(filtered),
            "updated": updated,
            "source": source,
            "error": error,
        },
    )
