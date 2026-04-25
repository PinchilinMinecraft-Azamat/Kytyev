import math
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent)


operations = {
    "+": "Сложение",
    "-": "Вычитание",
    "*": "Умножение",
    "/": "Деление",
    "%": "Остаток от деления",
    "^": "Степень",
}


def calculate(first_number: float, second_number: float, operation: str):
    if operation == "+":
        return first_number + second_number
    if operation == "-":
        return first_number - second_number
    if operation == "*":
        return first_number * second_number
    if operation == "/":
        if second_number == 0:
            return "На ноль делить нельзя"
        return first_number / second_number
    if operation == "%":
        if second_number == 0:
            return "Остаток от деления на ноль найти нельзя"
        return first_number % second_number
    if operation == "^":
        try:
            return pow(first_number, second_number)
        except OverflowError:
            return "Слишком большое число"

    return "Неизвестная операция"


def format_number(number: float) -> str:
    if number.is_integer():
        return str(int(number))

    return str(number)


def get_value(form_data: dict, name: str) -> str:
    values = form_data.get(name, [""])
    return values[0].strip()


def render_page(
    request: Request,
    first_number: str = "",
    second_number: str = "",
    operation: str = "+",
    answer: str = "",
):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "operations": operations,
            "first_number": first_number,
            "second_number": second_number,
            "operation": operation,
            "answer": answer,
        },
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render_page(request)


@app.post("/", response_class=HTMLResponse)
async def count(request: Request):
    body = await request.body()
    form_data = parse_qs(body.decode("utf-8"))

    first_text = get_value(form_data, "first_number")
    second_text = get_value(form_data, "second_number")
    operation = get_value(form_data, "operation")

    if first_text == "" or second_text == "":
        answer = "Заполните оба поля"
        return render_page(request, first_text, second_text, operation, answer)

    try:
        first_number = float(first_text.replace(",", "."))
        second_number = float(second_text.replace(",", "."))
    except ValueError:
        answer = "Введите числа"
        return render_page(request, first_text, second_text, operation, answer)

    result = calculate(first_number, second_number, operation)

    if isinstance(result, str):
        answer = result
    elif not math.isfinite(result):
        answer = "Слишком большое число"
    else:
        answer = (
            f"{format_number(first_number)} {operation} "
            f"{format_number(second_number)} = {format_number(result)}"
        )

    return render_page(request, first_text, second_text, operation, answer)
