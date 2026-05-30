import hashlib
import sqlite3
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

## uvicorn main:app --reload

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "registrations.db"
ADMIN_COOKIE_NAME = "admin_login"
ADMIN_ROLES = {"admin", "superadmin"}

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def check_admin_login(username: str, password: str) -> bool:
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id
            FROM admin_users
            WHERE username = ? AND password_hash = ?
            """,
            (username, hash_password(password)),
        )
        return cursor.fetchone() is not None


def get_admin_by_username(username: str):
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, username, role
            FROM admin_users
            WHERE username = ?
            """,
            (username,),
        )
        admin_user = cursor.fetchone()
        return dict(admin_user) if admin_user else None


def get_current_admin(request: Request):
    username = request.cookies.get(ADMIN_COOKIE_NAME)
    if not username:
        return None

    return get_admin_by_username(username)


def is_admin_authorized(request: Request) -> bool:
    return get_current_admin(request) is not None


def is_superadmin(request: Request) -> bool:
    admin_user = get_current_admin(request)
    return admin_user is not None and admin_user["role"] == "superadmin"


def require_admin(request: Request) -> None:
    if is_admin_authorized(request):
        return

    if request.method == "GET":
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/admin/login"},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin authorization required",
    )


def require_superadmin(request: Request) -> None:
    require_admin(request)

    if not is_superadmin(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmin can manage admins",
        )


def get_admin_template_context(request: Request):
    return {
        "current_admin": get_current_admin(request),
        "is_superadmin": is_superadmin(request),
    }


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
                price REAL NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        if not has_column(cursor, "abonements", "price"):
            cursor.execute("ALTER TABLE abonements ADD COLUMN price REAL NOT NULL DEFAULT 0")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin'
            )
            """
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO admin_users (username, password_hash, role)
            VALUES (?, ?, ?)
            """,
            ("admin", hash_password("admin"), "superadmin"),
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


def save_abonement(name: str, phone: str, abonement: str, total_visits: int, price: float = 0):
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO abonements (name, phone, abonement, total_visits, remaining_visits, price)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, phone, abonement, total_visits, total_visits, price),
        )
        connection.commit()


def get_abonements():
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, name, phone, abonement, total_visits, remaining_visits, price, created_at
            FROM abonements
            ORDER BY datetime(created_at) DESC, id DESC
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def update_abonement(abonement_id: int, name: str, phone: str, abonement: str, total_visits: int, price: float = 0):
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
                remaining_visits = MIN(remaining_visits, ?),
                price = ?
            WHERE id = ?
            """,
            (name, phone, abonement, total_visits, total_visits, price, abonement_id),
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


def get_admin_users():
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, username, role
            FROM admin_users
            ORDER BY id
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def create_admin_user(username: str, password: str, role: str):
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO admin_users (username, password_hash, role)
            VALUES (?, ?, ?)
            """,
            (username, hash_password(password), role),
        )
        connection.commit()


def update_admin_role(admin_id: int, role: str):
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE admin_users
            SET role = ?
            WHERE id = ?
            """,
            (role, admin_id),
        )
        connection.commit()


def delete_admin_user(admin_id: int):
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            DELETE FROM admin_users
            WHERE id = ?
            """,
            (admin_id,),
        )
        connection.commit()


def get_admin_user(admin_id: int):
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, username, role
            FROM admin_users
            WHERE id = ?
            """,
            (admin_id,),
        )
        admin_user = cursor.fetchone()
        return dict(admin_user) if admin_user else None


def count_superadmins():
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM admin_users
            WHERE role = 'superadmin'
            """
        )
        return cursor.fetchone()[0]


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


@app.get("/admin/login", response_class=HTMLResponse)
async def read_admin_login_page(request: Request):
    if is_admin_authorized(request):
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="admin_login.html",
        context={"error": ""},
    )


@app.post("/admin/login", response_class=HTMLResponse)
async def handle_admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if not check_admin_login(username, password):
        return templates.TemplateResponse(
            request=request,
            name="admin_login.html",
            context={
                "error": "Неверный логин или пароль.",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=username,
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/admin/logout")
async def handle_admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(ADMIN_COOKIE_NAME)
    return response


def get_admin_users_context(request: Request, error: str = "", success: str = ""):
    return {
        **get_admin_template_context(request),
        "admin_users": get_admin_users(),
        "roles": [
            {"value": "admin", "title": "Админ"},
            {"value": "superadmin", "title": "Главный админ"},
        ],
        "error": error,
        "success": success,
    }


@app.get("/admin/users", response_class=HTMLResponse)
async def read_admin_users_page(request: Request, _: None = Depends(require_superadmin)):
    return templates.TemplateResponse(
        request=request,
        name="admin_users.html",
        context=get_admin_users_context(request),
    )


@app.post("/admin/users/create", response_class=HTMLResponse)
async def handle_create_admin_user(
    request: Request,
    _: None = Depends(require_superadmin),
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
):
    username = username.strip()
    password = password.strip()
    role = role.strip()

    if not username or not password:
        return templates.TemplateResponse(
            request=request,
            name="admin_users.html",
            context=get_admin_users_context(request, error="Заполните логин и пароль."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if role not in ADMIN_ROLES:
        return templates.TemplateResponse(
            request=request,
            name="admin_users.html",
            context=get_admin_users_context(request, error="Выберите правильную роль."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        create_admin_user(username, password, role)
    except sqlite3.IntegrityError:
        return templates.TemplateResponse(
            request=request,
            name="admin_users.html",
            context=get_admin_users_context(request, error="Админ с таким логином уже есть."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/users/update/{admin_id}", response_class=HTMLResponse)
async def handle_update_admin_user_role(
    request: Request,
    admin_id: int,
    _: None = Depends(require_superadmin),
    role: str = Form(...),
):
    role = role.strip()
    admin_user = get_admin_user(admin_id)

    if admin_user is None:
        return templates.TemplateResponse(
            request=request,
            name="admin_users.html",
            context=get_admin_users_context(request, error="Админ не найден."),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if role not in ADMIN_ROLES:
        return templates.TemplateResponse(
            request=request,
            name="admin_users.html",
            context=get_admin_users_context(request, error="Выберите правильную роль."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if admin_user["role"] == "superadmin" and role != "superadmin" and count_superadmins() <= 1:
        return templates.TemplateResponse(
            request=request,
            name="admin_users.html",
            context=get_admin_users_context(request, error="Нельзя убрать последнего главного админа."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    update_admin_role(admin_id, role)
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/users/delete/{admin_id}", response_class=HTMLResponse)
async def handle_delete_admin_user(
    request: Request,
    admin_id: int,
    _: None = Depends(require_superadmin),
):
    admin_user = get_admin_user(admin_id)
    current_admin = get_current_admin(request)

    if admin_user is None:
        return templates.TemplateResponse(
            request=request,
            name="admin_users.html",
            context=get_admin_users_context(request, error="Админ не найден."),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if current_admin and admin_user["id"] == current_admin["id"]:
        return templates.TemplateResponse(
            request=request,
            name="admin_users.html",
            context=get_admin_users_context(request, error="Нельзя удалить самого себя."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if admin_user["role"] == "superadmin" and count_superadmins() <= 1:
        return templates.TemplateResponse(
            request=request,
            name="admin_users.html",
            context=get_admin_users_context(request, error="Нельзя удалить последнего главного админа."),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    delete_admin_user(admin_id)
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin", response_class=HTMLResponse)
async def read_admin_page(request: Request, _: None = Depends(require_admin)):
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={**get_registrations_stats(), **get_admin_template_context(request)},
    )


@app.get("/admin/abonements", response_class=HTMLResponse)
async def read_admin_abonements_page(request: Request, _: None = Depends(require_admin)):
    return templates.TemplateResponse(
        request=request,
        name="admin_abonements.html",
        context={**get_abonements_stats(), **get_admin_template_context(request)},
    )


@app.post("/admin/delete/{registration_id}")
async def handle_delete_registration(registration_id: int, _: None = Depends(require_admin)):
    delete_registration(registration_id)
    return JSONResponse(
        content={
            "status_ok": True,
            "registration_id": registration_id,
            **get_registrations_stats(),
        }
    )


@app.post("/admin/abonements/delete/{abonement_id}")
async def handle_delete_abonement(abonement_id: int, _: None = Depends(require_admin)):
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
    _: None = Depends(require_admin),
    name: str = Form(...),
    phone: str = Form(...),
    abonement: str = Form(...),
    total_visits: int = Form(...),
    price: float = Form(0),
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

    save_abonement(name, phone, abonement, total_visits, price)
    return JSONResponse(content={"status_ok": True, **get_abonements_stats()})


@app.post("/admin/abonements/update/{abonement_id}")
async def handle_update_abonement(
    abonement_id: int,
    _: None = Depends(require_admin),
    name: str = Form(...),
    phone: str = Form(...),
    abonement: str = Form(...),
    total_visits: int = Form(...),
    price: float = Form(0),
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

    update_abonement(abonement_id, name, phone, abonement, total_visits, price)
    return JSONResponse(content={"status_ok": True, **get_abonements_stats()})


@app.post("/admin/abonements/adjust/{abonement_id}")
async def handle_adjust_abonement(
    abonement_id: int,
    _: None = Depends(require_admin),
    delta: int = Form(...),
):
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
async def handle_refresh_abonement(abonement_id: int, _: None = Depends(require_admin)):
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

@app.get("/api/abonements/pricing")
async def get_abonement_pricing():
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT abonement, total_visits, price
            FROM abonements
            WHERE price > 0
            GROUP BY abonement
            ORDER BY price
            """
        )
        return [dict(row) for row in cursor.fetchall()]


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
