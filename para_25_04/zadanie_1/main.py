from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent)


users = [
    {"name": "Алексей Иванов", "age": 19, "email": "alexey@mail.ru", "city": "Екатеринбург"},
    {"name": "Мария Петрова", "age": 20, "email": "maria@mail.ru", "city": "Пермь"},
    {"name": "Дмитрий Соколов", "age": 18, "email": "dima@mail.ru", "city": "Тюмень"},
    {"name": "Анна Смирнова", "age": 21, "email": "anna@mail.ru", "city": "Казань"},
    {"name": "Илья Морозов", "age": 19, "email": "ilya@mail.ru", "city": "Челябинск"},
]


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "users": users,
        },
    )
