import sqlite3
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

## uvicorn main:app --reload

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "registrations.db"

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


def has_column(cursor: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return any(column[1] == column_name for column in columns)


def init_db():
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                course TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS abonements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                abonement TEXT NOT NULL,
                total_visits INTEGER NOT NULL DEFAULT 8,
                remaining_visits INTEGER NOT NULL DEFAULT 8,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            UPDATE abonements
            SET remaining_visits = total_visits
            WHERE remaining_visits > total_visits
            """
        )
        connection.commit()


def save_registration(name: str, phone: str, course: str):
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO registrations (name, phone, course)
            VALUES (?, ?, ?)
            """,
            (name, phone, course),
        )
        connection.commit()


def get_registrations():
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, name, phone, course, created_at
            FROM registrations
            ORDER BY datetime(created_at) DESC, id DESC
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def save_abonement(name: str, phone: str, abonement: str, total_visits: int):
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO abonements (name, phone, abonement, total_visits, remaining_visits)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, phone, abonement, total_visits, total_visits),
        )
        connection.commit()


def get_abonements():
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, name, phone, abonement, total_visits, remaining_visits, created_at
            FROM abonements
            ORDER BY datetime(created_at) DESC, id DESC
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def update_abonement(abonement_id: int, name: str, phone: str, abonement: str, total_visits: int):
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE abonements
            SET
                name = ?,
                phone = ?,
                abonement = ?,
                total_visits = ?,
                remaining_visits = MIN(remaining_visits, ?)
            WHERE id = ?
            """,
            (name, phone, abonement, total_visits, total_visits, abonement_id),
        )
        connection.commit()


def adjust_abonement_visits(abonement_id: int, delta: int):
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT total_visits, remaining_visits
            FROM abonements
            WHERE id = ?
            """,
            (abonement_id,),
        )
        abonement = cursor.fetchone()
        if abonement is None:
            return None

        next_remaining = abonement["remaining_visits"] + delta
        next_remaining = max(0, min(abonement["total_visits"], next_remaining))

        cursor.execute(
            """
            UPDATE abonements
            SET remaining_visits = ?
            WHERE id = ?
            """,
            (next_remaining, abonement_id),
        )
        connection.commit()
        return next_remaining


def refresh_abonement(abonement_id: int):
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT total_visits
            FROM abonements
            WHERE id = ?
            """,
            (abonement_id,),
        )
        abonement = cursor.fetchone()
        if abonement is None:
            return None

        cursor.execute(
            """
            UPDATE abonements
            SET remaining_visits = total_visits
            WHERE id = ?
            """,
            (abonement_id,),
        )
        connection.commit()
        return abonement["total_visits"]


def delete_registration(registration_id: int):
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            DELETE FROM registrations
            WHERE id = ?
            """,
            (registration_id,),
        )
        connection.commit()


def delete_abonement(abonement_id: int):
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            DELETE FROM abonements
            WHERE id = ?
            """,
            (abonement_id,),
        )
        connection.commit()


def get_registrations_stats():
    registrations = get_registrations()
    total_registrations = len(registrations)
    unique_courses = len({item["course"] for item in registrations})
    latest_registration = registrations[0]["created_at"] if registrations else "Пока нет заявок"
    return {
        "registrations": registrations,
        "total_registrations": total_registrations,
        "unique_courses": unique_courses,
        "latest_registration": latest_registration,
    }


def get_abonements_stats():
    abonements = get_abonements()
    total_abonements = len(abonements)
    unique_abonements = len({item["abonement"] for item in abonements})
    average_remaining_visits = (
        round(sum(item["remaining_visits"] for item in abonements) / total_abonements, 1)
        if total_abonements
        else 0
    )
    latest_abonement = abonements[0]["created_at"] if abonements else "Пока нет абонементов"
    return {
        "abonements": abonements,
        "total_abonements": total_abonements,
        "unique_abonements": unique_abonements,
        "average_remaining_visits": average_remaining_visits,
        "latest_abonement": latest_abonement,
    }


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def read_main_page(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="index.html"
    )


@app.get("/admin", response_class=HTMLResponse)
async def read_admin_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context=get_registrations_stats(),
    )


@app.get("/admin/abonements", response_class=HTMLResponse)
async def read_admin_abonements_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin_abonements.html",
        context=get_abonements_stats(),
    )


@app.post("/admin/delete/{registration_id}")
async def handle_delete_registration(registration_id: int):
    delete_registration(registration_id)
    return JSONResponse(
        content={
            "status_ok": True,
            "registration_id": registration_id,
            **get_registrations_stats(),
        }
    )


@app.post("/admin/abonements/delete/{abonement_id}")
async def handle_delete_abonement(abonement_id: int):
    delete_abonement(abonement_id)
    return JSONResponse(
        content={
            "status_ok": True,
            "abonement_id": abonement_id,
            **get_abonements_stats(),
        }
    )


@app.post("/admin/abonements/create")
async def handle_create_abonement(
    name: str = Form(...),
    phone: str = Form(...),
    abonement: str = Form(...),
    total_visits: int = Form(...),
):
    name = name.strip()
    phone = phone.strip()
    abonement = abonement.strip()

    if not name or not phone or not abonement:
        return JSONResponse(
            status_code=400,
            content={"status_ok": False, "message": "Заполните все поля."},
        )

    if total_visits < 1:
        return JSONResponse(
            status_code=400,
            content={"status_ok": False, "message": "Количество посещений должно быть больше 0."},
        )

    save_abonement(name, phone, abonement, total_visits)
    return JSONResponse(content={"status_ok": True, **get_abonements_stats()})


@app.post("/admin/abonements/update/{abonement_id}")
async def handle_update_abonement(
    abonement_id: int,
    name: str = Form(...),
    phone: str = Form(...),
    abonement: str = Form(...),
    total_visits: int = Form(...),
):
    name = name.strip()
    phone = phone.strip()
    abonement = abonement.strip()

    if not name or not phone or not abonement:
        return JSONResponse(
            status_code=400,
            content={"status_ok": False, "message": "Заполните все поля."},
        )

    if total_visits < 1:
        return JSONResponse(
            status_code=400,
            content={"status_ok": False, "message": "Количество посещений должно быть больше 0."},
        )

    update_abonement(abonement_id, name, phone, abonement, total_visits)
    return JSONResponse(content={"status_ok": True, **get_abonements_stats()})


@app.post("/admin/abonements/adjust/{abonement_id}")
async def handle_adjust_abonement(abonement_id: int, delta: int = Form(...)):
    remaining_visits = adjust_abonement_visits(abonement_id, delta)
    if remaining_visits is None:
        return JSONResponse(
            status_code=404,
            content={"status_ok": False, "message": "Абонемент не найден."},
        )

    return JSONResponse(
        content={
            "status_ok": True,
            "abonement_id": abonement_id,
            "remaining_visits": remaining_visits,
            **get_abonements_stats(),
        }
    )


@app.post("/admin/abonements/refresh/{abonement_id}")
async def handle_refresh_abonement(abonement_id: int):
    remaining_visits = refresh_abonement(abonement_id)
    if remaining_visits is None:
        return JSONResponse(
            status_code=404,
            content={"status_ok": False, "message": "Абонемент не найден."},
        )

    return JSONResponse(
        content={
            "status_ok": True,
            "abonement_id": abonement_id,
            "remaining_visits": remaining_visits,
            **get_abonements_stats(),
        }
    )

@app.post("/submit_register")
async def handle_form_register(
    name: str = Form(...),
    phone: str = Form(...),
    course: str = Form(...)
):
    name = name.strip()
    phone = phone.strip()
    course = course.strip()

    print(name, phone, course)

    if not name or not phone or not course:
        return JSONResponse(
            status_code=400,
            content={
                "status_ok": False,
                "message": "Заполните все поля."
            }
        )

    save_registration(name, phone, course)

    return {
        "status_ok": True,
        "message": "Вы записаны!"
    }
