
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3, os, json
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

APP_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_PATH = Path(os.environ.get("CLUBPOINT_DB", str(APP_DIR / "clubpoint.db")))
if not DATABASE_URL:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
csrf = CSRFProtect()
secret = os.environ.get("CLUBPOINT_SECRET")
if not secret and os.environ.get("RENDER"):
    raise RuntimeError("Set CLUBPOINT_SECRET in Render environment variables.")
app.secret_key = secret or "DEV-ONLY-CHANGE-ME"
app.config.update(
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1" if os.environ.get("RENDER") else "0") == "1",
    PERMANENT_SESSION_LIFETIME=__import__("datetime").timedelta(hours=8),
)
csrf.init_app(app)
try:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
except Exception:
    pass


TRANSLATIONS = {'Новости': 'Yangiliklar', 'Турниры': 'Turnirlar', 'Панель оператора': 'Operator paneli', 'Выйти из оператора': 'Operatordan chiqish', 'Мой кабинет': 'Mening kabinetim', 'Выйти из ученика': 'O‘quvchi hisobidan chiqish', 'Неверный логин или пароль.': 'Login yoki parol noto‘g‘ri.', 'Вход оператора': 'Operator tizimiga kirish', 'Вход пользователя': 'Foydalanuvchi tizimiga kirish', 'Управление клубами, баллами и аккаунтами пользователей': 'Klublar, ballar va foydalanuvchi hisoblarini boshqarish', 'Клубов': 'Klublar', 'Пользователей': 'Foydalanuvchilar', 'Сумма баллов': 'Jami ballar', 'Добавить клуб': 'Klub qo‘shish', 'Название клуба': 'Klub nomi', 'Количество участников': 'Ishtirokchilar soni', 'Баллы': 'Ballar', 'Статистика клубов': 'Klublar statistikasi', 'Клуб': 'Klub', 'Участники': 'Ishtirokchilar', 'Изменить': 'O‘zgartirish', 'Сохранить': 'Saqlash', 'Удалить': 'O‘chirish', 'Создать аккаунт ученика': 'O‘quvchi hisobini yaratish', 'ФИО': 'F.I.Sh.', 'ID ученика': 'O‘quvchi ID raqami', 'Логин для входа': 'Kirish logini', 'Временный пароль (от 8 символов)': 'Vaqtinchalik parol (kamida 8 belgi)', 'Личные баллы ученика': 'O‘quvchining shaxsiy ballari', 'Без клуба': 'Klubsiz', 'Создать пользователя': 'Foydalanuvchi yaratish', 'Аккаунты пользователей': 'Foydalanuvchi hisoblari', 'Ученик': 'O‘quvchi', 'Логин': 'Login', 'Личные баллы': 'Shaxsiy ballar', 'Пароли хранятся в виде хешей и не отображаются оператору после создания.': 'Parollar xesh ko‘rinishida saqlanadi va yaratilgandan keyin operatorga ko‘rsatilmaydi.', 'Опубликовать новость': 'Yangilikni e’lon qilish', 'Заголовок': 'Sarlavha', 'Текст новости': 'Yangilik matni', 'Опубликованные новости': 'E’lon qilingan yangiliklar', 'Новостей пока нет.': 'Hozircha yangiliklar yo‘q.', 'Создать турнир': 'Turnir yaratish', 'Название турнира': 'Turnir nomi', 'Дата проведения': 'O‘tkazilish sanasi', 'Максимум участников (0 — без лимита)': 'Ishtirokchilar maksimumi (0 — cheklovsiz)', 'Статус': 'Holati', 'Регистрация открыта': 'Ro‘yxatdan o‘tish ochiq', 'Регистрация закрыта': 'Ro‘yxatdan o‘tish yopiq', 'Завершён': 'Yakunlangan', 'Описание': 'Tavsif', 'Турниры и участники': 'Turnirlar va ishtirokchilar', 'Зарегистрировано:': 'Ro‘yxatdan o‘tgan:', 'без лимита': 'cheklovsiz', 'Открыта': 'Ochiq', 'Закрыта': 'Yopiq', 'Изменить статус': 'Holatni o‘zgartirish', 'Турниров пока нет.': 'Hozircha turnirlar yo‘q.', 'Список участников турниров': 'Turnir ishtirokchilari ro‘yxati', 'Турнир': 'Turnir', 'Пока нет регистраций.': 'Hozircha ro‘yxatdan o‘tganlar yo‘q.', 'Личный кабинет': 'Shaxsiy kabinet', 'Добро пожаловать,': 'Xush kelibsiz,', 'Ваш ID': 'Sizning ID raqamingiz', 'Ваши личные баллы': 'Shaxsiy ballaringiz', 'Ваш клуб': 'Klubingiz', 'Не назначен': 'Biriktirilmagan', 'Баллы клуба:': 'Klub ballari:', 'Новости и турниры': 'Yangiliklar va turnirlar', 'Смотрите последние публикации и записывайтесь на турниры через каталог.': 'So‘nggi yangiliklarni ko‘ring va katalog orqali turnirlarga yoziling.', 'Открыть новости': 'Yangiliklarni ochish', 'Посмотреть турниры': 'Turnirlarni ko‘rish', 'Рейтинг клубов': 'Klublar reytingi', 'Место': 'O‘rin', 'Здесь доступен только просмотр. Изменять клубы и баллы может оператор.': 'Bu yerda faqat ko‘rish mumkin. Klublar va ballarni operator o‘zgartiradi.', 'Выберите турнир и зарегистрируйтесь через свой аккаунт ученика.': 'Turnirni tanlang va o‘quvchi hisobingiz orqali ro‘yxatdan o‘ting.', 'Дата': 'Sana', 'Вы уже зарегистрированы.': 'Siz allaqachon ro‘yxatdan o‘tgansiz.', 'Зарегистрироваться': 'Ro‘yxatdan o‘tish', 'Регистрация недоступна.': 'Ro‘yxatdan o‘tish imkonsiz.', 'Войти, чтобы зарегистрироваться': 'Ro‘yxatdan o‘tish uchun kiring', 'Пока турниров нет.': 'Hozircha turnirlar yo‘q.', 'Пока новостей нет.': 'Hozircha yangiliklar yo‘q.', 'Клуб сохранён.': 'Klub saqlandi.', 'Проверьте данные: название должно быть уникальным, баллы и участники — целыми числами.': 'Ma’lumotlarni tekshiring: klub nomi takrorlanmasin, ballar va ishtirokchilar soni butun son bo‘lsin.', 'Клуб удалён.': 'Klub o‘chirildi.', 'Заполните все поля. Пароль должен содержать минимум 8 символов.': 'Barcha maydonlarni to‘ldiring. Parol kamida 8 ta belgidan iborat bo‘lishi kerak.', 'Аккаунт пользователя создан.': 'Foydalanuvchi hisobi yaratildi.', 'Такой логин или ID ученика уже существует.': 'Bunday login yoki o‘quvchi ID raqami allaqachon mavjud.', 'Личные баллы ученика обновлены.': 'O‘quvchining shaxsiy ballari yangilandi.', 'Введите корректное целое число баллов.': 'Ballar uchun to‘g‘ri butun son kiriting.', 'Аккаунт удалён.': 'Hisob o‘chirildi.', 'Турнир не найден.': 'Turnir topilmadi.', 'Регистрация на этот турнир закрыта.': 'Ushbu turnirga ro‘yxatdan o‘tish yopilgan.', 'Свободных мест больше нет.': 'Bo‘sh joy qolmagan.', 'Вы успешно зарегистрированы на турнир.': 'Turnirga muvaffaqiyatli ro‘yxatdan o‘tdingiz.', 'Не удалось зарегистрироваться. Возможно, вы уже записаны.': 'Ro‘yxatdan o‘tib bo‘lmadi. Balki siz allaqachon yozilgandirsiz.', 'Заполните заголовок и текст новости.': 'Yangilik sarlavhasi va matnini kiriting.', 'Новость опубликована.': 'Yangilik e’lon qilindi.', 'Новость удалена.': 'Yangilik o‘chirildi.', 'Турнир создан.': 'Turnir yaratildi.', 'Проверьте название, дату, количество мест и статус турнира.': 'Turnir nomi, sanasi, joylar soni va holatini tekshiring.', 'Статус турнира обновлён.': 'Turnir holati yangilandi.', 'Турнир удалён.': 'Turnir o‘chirildi.', 'и личный кабинет ученика': 'va o‘quvchining shaxsiy kabineti', 'Каталог COLBA CLUBS': 'COLBA CLUBS katalogi', 'Читайте новости и участвуйте в турнирах.': 'Yangiliklarni o‘qing va turnirlarda qatnashing.', 'Управление клубами, баллами и аккаунтами учеников.': 'Klublar, ballar va o‘quvchi hisoblarini boshqarish.', 'Кабинет пользователя': 'Foydalanuvchi kabineti', 'Просмотр рейтинга клубов и своей информации.': 'Klublar reytingi va shaxsiy ma’lumotlarni ko‘rish.', 'Последние новости COLBA CLUBS': 'COLBA CLUBS so‘nggi yangiliklari', 'Кабинет ученика': 'O‘quvchi kabineti', 'Пароль': 'Parol', 'Войти': 'Kirish', 'Без лимита': 'Cheklovsiz', 'Удалить клуб?': 'Klub o‘chirilsinmi?', 'Удалить аккаунт?': 'Hisob o‘chirilsinmi?', 'Удалить турнир и регистрации?': 'Turnir va ro‘yxatdan o‘tganlar o‘chirilsinmi?'}
def tr(value):
    return TRANSLATIONS.get(value, value) if session.get("language", "ru") == "uz" else value

@app.context_processor
def inject_language():
    return {"_": tr, "current_language": session.get("language", "ru")}

@app.route("/language/<lang>")
def set_language(lang):
    if lang in ("ru", "uz"):
        session["language"] = lang
    return redirect(request.referrer or url_for("home"))

class PostgresConnection:
    """Compatibility wrapper retaining the app's qmark SQL placeholders."""
    def __init__(self, conn): self.conn = conn
    def execute(self, sql, params=()): return self.conn.execute(sql.replace("?", "%s"), params)
    def commit(self): self.conn.commit()
    def rollback(self): self.conn.rollback()
    def close(self): self.conn.close()

def db():
    if DATABASE_URL:
        if psycopg is None:
            raise RuntimeError("Install psycopg[binary] to use PostgreSQL.")
        return PostgresConnection(psycopg.connect(DATABASE_URL, row_factory=dict_row))
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    if DATABASE_URL:
        con.execute("""CREATE TABLE IF NOT EXISTS operators (
          id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'operator'
        )""")
        con.execute("ALTER TABLE operators ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'operator'")
        con.execute("""CREATE TABLE IF NOT EXISTS users (
          id SERIAL PRIMARY KEY, login TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
          student_id TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL, club_id INTEGER,
          points INTEGER NOT NULL DEFAULT 0
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS clubs (
          id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL,
          members INTEGER NOT NULL DEFAULT 0, points INTEGER NOT NULL DEFAULT 0
        )""")
        con.execute("ALTER TABLE clubs ADD COLUMN IF NOT EXISTS president_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
        con.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS points INTEGER NOT NULL DEFAULT 0")
        con.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_data BYTEA")
        con.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_mime TEXT")
        con.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS image_data BYTEA") if False else None
        con.execute("""CREATE TABLE IF NOT EXISTS news (
          id SERIAL PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS image_data BYTEA")
        con.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS image_mime TEXT")
        con.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS club_id INTEGER REFERENCES clubs(id) ON DELETE CASCADE")
        con.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS author_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
        con.execute("""CREATE TABLE IF NOT EXISTS tournaments (
          id SERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          event_date TEXT NOT NULL, capacity INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'open', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS tournament_registrations (
          id SERIAL PRIMARY KEY, tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(tournament_id, user_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS book_quiz_submissions (
          id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          book_key TEXT NOT NULL, answers TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          awarded_points INTEGER, operator_note TEXT NOT NULL DEFAULT '',
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          reviewed_at TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS student_messages (
          id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          subject TEXT NOT NULL, body TEXT NOT NULL, reply TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'new',
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          replied_at TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
          id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          body TEXT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS operator_chat_messages (
          id SERIAL PRIMARY KEY, operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
          body TEXT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS club_chat_messages (
          id SERIAL PRIMARY KEY, club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          body TEXT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_club_chat_messages_club_id_id ON club_chat_messages(club_id, id)")
        con.execute("""CREATE TABLE IF NOT EXISTS club_join_requests (
          id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
          status TEXT NOT NULL DEFAULT 'pending', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          reviewed_at TIMESTAMP, reviewed_by_operator_id INTEGER REFERENCES operators(id) ON DELETE SET NULL,
          reviewed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_club_join_requests_status ON club_join_requests(status, club_id)")
    else:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS operators (
          id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'operator'
        );
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT, login TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
          student_id TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL, club_id INTEGER,
          points INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS clubs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
          members INTEGER NOT NULL DEFAULT 0, points INTEGER NOT NULL DEFAULT 0
        );
        """)
        con.executescript("""
        CREATE TABLE IF NOT EXISTS news (
          id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tournaments (
          id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          event_date TEXT NOT NULL, capacity INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'open', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tournament_registrations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(tournament_id, user_id)
        );
        """)
        club_columns = [row["name"] for row in con.execute("PRAGMA table_info(clubs)").fetchall()]
        if "president_user_id" not in club_columns:
            con.execute("ALTER TABLE clubs ADD COLUMN president_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
        news_columns = [row["name"] for row in con.execute("PRAGMA table_info(news)").fetchall()]
        if "club_id" not in news_columns:
            con.execute("ALTER TABLE news ADD COLUMN club_id INTEGER REFERENCES clubs(id) ON DELETE CASCADE")
        if "author_user_id" not in news_columns:
            con.execute("ALTER TABLE news ADD COLUMN author_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
        if "image_data" not in news_columns:
            con.execute("ALTER TABLE news ADD COLUMN image_data BLOB")
        if "image_mime" not in news_columns:
            con.execute("ALTER TABLE news ADD COLUMN image_mime TEXT")
        user_columns = [row["name"] for row in con.execute("PRAGMA table_info(users)").fetchall()]
        if "points" not in user_columns:
            con.execute("ALTER TABLE users ADD COLUMN points INTEGER NOT NULL DEFAULT 0")
        if "avatar_data" not in user_columns:
            con.execute("ALTER TABLE users ADD COLUMN avatar_data BLOB")
        if "avatar_mime" not in user_columns:
            con.execute("ALTER TABLE users ADD COLUMN avatar_mime TEXT")
        con.execute("""CREATE TABLE IF NOT EXISTS book_quiz_submissions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          book_key TEXT NOT NULL, answers TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          awarded_points INTEGER, operator_note TEXT NOT NULL DEFAULT '',
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          reviewed_at TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS student_messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          subject TEXT NOT NULL, body TEXT NOT NULL, reply TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'new',
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          replied_at TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          body TEXT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS operator_chat_messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT, operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
          body TEXT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS club_chat_messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT, club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          body TEXT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_club_chat_messages_club_id_id ON club_chat_messages(club_id, id)")
        con.execute("""CREATE TABLE IF NOT EXISTS club_join_requests (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
          status TEXT NOT NULL DEFAULT 'pending', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          reviewed_at TIMESTAMP, reviewed_by_operator_id INTEGER REFERENCES operators(id) ON DELETE SET NULL,
          reviewed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_club_join_requests_status ON club_join_requests(status, club_id)")
    # Backward-compatible migration for existing SQLite databases.
    if not DATABASE_URL:
        operator_columns = [row["name"] for row in con.execute("PRAGMA table_info(operators)").fetchall()]
        if "role" not in operator_columns:
            con.execute("ALTER TABLE operators ADD COLUMN role TEXT NOT NULL DEFAULT 'operator'")
    if not con.execute("SELECT id FROM operators LIMIT 1").fetchone():
        initial_username = os.environ.get("OPERATOR_USERNAME", "admin").strip()
        initial_password = os.environ.get("OPERATOR_PASSWORD", "ChangeMe2026!")
        con.execute("INSERT INTO operators(username,password_hash,role) VALUES(?,?,?)",
                    (initial_username, generate_password_hash(initial_password), "superadmin"))
    # Existing installations: grant the first-created operator the owner role once.
    if not con.execute("SELECT id FROM operators WHERE role='superadmin' LIMIT 1").fetchone():
        first_operator = con.execute("SELECT id FROM operators ORDER BY id LIMIT 1").fetchone()
        if first_operator:
            con.execute("UPDATE operators SET role='superadmin' WHERE id=?", (first_operator["id"],))
    if not con.execute("SELECT id FROM clubs LIMIT 1").fetchone():
        for name, members, points in [("Клуб науки",18,860),("Клуб творчества",15,740),("Клуб спорта",22,690),("Клуб IT",12,620)]:
            con.execute("INSERT INTO clubs(name,members,points) VALUES(?,?,?)", (name,members,points))
    con.commit(); con.close()

def operator_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("operator_id"):
            return redirect(url_for("operator_login"))
        return fn(*args, **kwargs)
    return wrapped

def super_operator_required(fn):
    """Only the main operator (superadmin) can manage operator accounts."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        operator_id = session.get("operator_id")
        if not operator_id:
            return redirect(url_for("operator_login"))
        con = db()
        row = con.execute("SELECT role FROM operators WHERE id=?", (operator_id,)).fetchone()
        con.close()
        if not row or row["role"] != "superadmin":
            flash("Это действие доступно только главному оператору.")
            return redirect(url_for("operator_dashboard"))
        return fn(*args, **kwargs)
    return wrapped

def user_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("user_login"))
        return fn(*args, **kwargs)
    return wrapped

@app.route("/public-chat", methods=["GET", "POST"])
def public_chat():
    # The chat is available to authenticated students and operators only.
    if not session.get("user_id") and not session.get("operator_id"):
        return redirect(url_for("user_login"))

    if request.method == "POST":
        if not session.get("user_id"):
            flash("Только ученики могут отправлять сообщения в общий чат.")
        else:
            body = request.form.get("body", "").strip()
            if not body:
                flash("Введите текст сообщения.")
            elif len(body) > 2000:
                flash("Сообщение не должно превышать 2000 символов.")
            else:
                con = db()
                con.execute("INSERT INTO chat_messages(user_id, body) VALUES(?, ?)",
                            (session["user_id"], body))
                con.commit()
                con.close()
        return redirect(url_for("public_chat"))

    con = db()
    messages = con.execute("""SELECT cm.id, cm.body, cm.created_at,
                                    u.full_name, c.name AS club_name
                             FROM chat_messages cm
                             JOIN users u ON u.id = cm.user_id
                             LEFT JOIN clubs c ON c.id = u.club_id
                             ORDER BY cm.id DESC LIMIT 200""").fetchall()
    con.close()
    return render_template("public_chat.html", messages=list(reversed(messages)))

@app.route("/club-chat", methods=["GET", "POST"])
@user_required
def club_chat():
    """Private chat room for students belonging to the same club."""
    con = db()
    member = con.execute("""SELECT u.id, u.full_name, u.club_id, c.name AS club_name
                            FROM users u LEFT JOIN clubs c ON c.id=u.club_id
                            WHERE u.id=?""", (session["user_id"],)).fetchone()
    if not member or not member["club_id"]:
        con.close()
        flash("Сначала оператор должен назначить вас в клуб." if session.get("language", "ru") == "ru" else "Avval operator sizni klubga biriktirishi kerak.")
        return redirect(url_for("user_dashboard"))

    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if not body:
            flash("Введите текст сообщения." if session.get("language", "ru") == "ru" else "Xabar matnini kiriting.")
        elif len(body) > 2000:
            flash("Сообщение не должно превышать 2000 символов." if session.get("language", "ru") == "ru" else "Xabar 2000 belgidan oshmasligi kerak.")
        else:
            # Club ID is taken from the authenticated user's database record,
            # never from a client-supplied form value.
            con.execute("INSERT INTO club_chat_messages(club_id, user_id, body) VALUES(?,?,?)",
                        (member["club_id"], session["user_id"], body))
            con.commit()
        con.close()
        return redirect(url_for("club_chat"))

    messages = con.execute("""SELECT m.id, m.body, m.created_at, u.full_name, u.student_id
                              FROM club_chat_messages m
                              JOIN users u ON u.id=m.user_id
                              WHERE m.club_id=?
                              ORDER BY m.id DESC LIMIT 300""", (member["club_id"],)).fetchall()
    con.close()
    return render_template("club_chat.html", club=member, messages=list(reversed(messages)))


@app.route("/operator/chat", methods=["GET", "POST"])
@operator_required
def operator_chat():
    """Private room shared only by authenticated operator accounts."""
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if not body:
            flash("Введите текст сообщения.")
        elif len(body) > 2000:
            flash("Сообщение не должно превышать 2000 символов.")
        else:
            con = db()
            con.execute("INSERT INTO operator_chat_messages(operator_id, body) VALUES(?, ?)",
                        (session["operator_id"], body))
            con.commit()
            con.close()
        return redirect(url_for("operator_chat"))

    con = db()
    messages = con.execute("""SELECT m.id, m.body, m.created_at, o.username
                              FROM operator_chat_messages m
                              JOIN operators o ON o.id = m.operator_id
                              ORDER BY m.id DESC LIMIT 300""").fetchall()
    con.close()
    return render_template("operator_chat.html", messages=list(reversed(messages)))

@app.route("/")
def home():
    return render_template(
        "login.html",
        title=tr("Вход пользователя"),
        action=url_for("user_login"),
        show_operator_link=True
    )

@app.route("/operator/login", methods=["GET","POST"])
def operator_login():
    if request.method == "POST":
        con = db()
        row = con.execute("SELECT * FROM operators WHERE username=?", (request.form["login"].strip(),)).fetchone()
        con.close()
        if row and check_password_hash(row["password_hash"], request.form["password"]):
            session.permanent=True; session["operator_id"]=row["id"]
            return redirect(url_for("operator_dashboard"))
        flash(tr("Неверный логин или пароль."))
    return render_template("login.html", title=tr("Вход оператора"), action=url_for("operator_login"))

@app.route("/user/login", methods=["GET","POST"])
def user_login():
    if request.method == "POST":
        con = db()
        row = con.execute("SELECT * FROM users WHERE login=?", (request.form["login"].strip(),)).fetchone()
        con.close()
        if row and check_password_hash(row["password_hash"], request.form["password"]):
            session.permanent=True; session["user_id"]=row["id"]
            return redirect(url_for("user_dashboard"))
        flash(tr("Неверный логин или пароль."))
    return render_template("login.html", title=tr("Вход пользователя"), action=url_for("user_login"), show_operator_link=True)

@app.route("/operator")
@operator_required
def operator_dashboard():
    con=db()
    current_operator = con.execute("SELECT role FROM operators WHERE id=?", (session.get("operator_id"),)).fetchone()
    is_super_operator = bool(current_operator and current_operator["role"] == "superadmin")
    operator_accounts = con.execute("SELECT id, username, role FROM operators ORDER BY id").fetchall() if is_super_operator else []
    clubs=con.execute("""SELECT c.*, COUNT(u.id) AS real_members,
                         COALESCE(SUM(u.points),0) AS points
                         FROM clubs c LEFT JOIN users u ON u.club_id=c.id
                         GROUP BY c.id ORDER BY COALESCE(SUM(u.points),0) DESC""").fetchall()
    users=con.execute("""SELECT u.*, c.name AS club_name FROM users u
                         LEFT JOIN clubs c ON c.id=u.club_id ORDER BY u.full_name""").fetchall()
    totals=con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    points=con.execute("SELECT COALESCE(SUM(points),0) n FROM users").fetchone()["n"]
    news_items=con.execute("SELECT * FROM news ORDER BY created_at DESC, id DESC").fetchall()
    tournaments=con.execute("""SELECT t.*, COUNT(r.id) AS registered FROM tournaments t
        LEFT JOIN tournament_registrations r ON r.tournament_id=t.id
        GROUP BY t.id ORDER BY t.event_date, t.id DESC""").fetchall()
    registrations=con.execute("""SELECT t.title AS tournament_title, u.full_name, u.student_id
        FROM tournament_registrations r JOIN tournaments t ON t.id=r.tournament_id
        JOIN users u ON u.id=r.user_id ORDER BY t.event_date, t.title, u.full_name""").fetchall()
    quiz_submissions=con.execute("""SELECT q.*, u.full_name, u.student_id, c.name AS club_name
        FROM book_quiz_submissions q JOIN users u ON u.id=q.user_id
        LEFT JOIN clubs c ON c.id=u.club_id ORDER BY CASE WHEN q.status='pending' THEN 0 ELSE 1 END, q.id DESC""").fetchall()
    quiz_submissions = [dict(q, answers_data=json.loads(q["answers"])) for q in quiz_submissions]
    student_messages=con.execute("""SELECT m.*, u.full_name, u.student_id, c.name AS club_name
        FROM student_messages m JOIN users u ON u.id=m.user_id
        LEFT JOIN clubs c ON c.id=u.club_id
        ORDER BY CASE WHEN m.status='new' THEN 0 ELSE 1 END, m.id DESC""").fetchall()
    con.close()
    return render_template("operator.html", clubs=clubs, users=users, total_users=totals,
                           total_points=points, news_items=news_items, tournaments=tournaments,
                           registrations=registrations, quiz_submissions=quiz_submissions,
                           student_messages=student_messages, is_super_operator=is_super_operator,
                           operator_accounts=operator_accounts)

@app.post("/operator/create-operator")
@super_operator_required
def create_operator():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or len(username) < 3 or len(password) < 8:
        flash("Укажите логин (не менее 3 символов) и пароль (не менее 8 символов).")
        return redirect(url_for("operator_dashboard"))
    con = db()
    try:
        con.execute("INSERT INTO operators(username,password_hash,role) VALUES(?,?,?)",
                    (username, generate_password_hash(password), "operator"))
        con.commit()
        flash("Аккаунт оператора создан.")
    except Exception:
        con.rollback()
        flash("Не удалось создать аккаунт: такой логин уже существует.")
    finally:
        con.close()
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/delete-operator/<int:operator_id>")
@super_operator_required
def delete_operator(operator_id):
    if operator_id == session.get("operator_id"):
        flash("Нельзя удалить собственный аккаунт главного оператора.")
        return redirect(url_for("operator_dashboard"))
    con = db()
    target = con.execute("SELECT role FROM operators WHERE id=?", (operator_id,)).fetchone()
    if not target:
        flash("Оператор не найден.")
    elif target["role"] == "superadmin":
        flash("Нельзя удалить аккаунт главного оператора.")
    else:
        con.execute("DELETE FROM operators WHERE id=?", (operator_id,))
        con.commit()
        flash("Аккаунт оператора удалён.")
    con.close()
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/club")
@operator_required
def save_club():
    name=request.form.get("name","").strip()
    try:
        members=max(0,int(request.form.get("members",0)))
        points=max(0,int(request.form.get("points",0)))
        club_id=request.form.get("club_id","")
        if not name: raise ValueError()
        con=db()
        if club_id:
            con.execute("UPDATE clubs SET name=?,members=? WHERE id=?",
                        (name,members,int(club_id)))
        else:
            con.execute("INSERT INTO clubs(name,members,points) VALUES(?,?,0)",(name,members))
        con.commit(); con.close(); flash(tr("Клуб сохранён."))
    except (ValueError, sqlite3.IntegrityError) + ((psycopg.IntegrityError,) if psycopg else ()):
        flash(tr("Проверьте данные: название должно быть уникальным, баллы и участники — целыми числами."))
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/club/delete/<int:club_id>")
@operator_required
def delete_club(club_id):
    con=db()
    con.execute("UPDATE users SET club_id=NULL WHERE club_id=?",(club_id,))
    con.execute("DELETE FROM clubs WHERE id=?",(club_id,))
    con.commit(); con.close(); flash(tr("Клуб удалён."))
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/user")
@operator_required
def create_user():
    login=request.form.get("login","").strip()
    password=request.form.get("password","")
    student_id=request.form.get("student_id","").strip()
    full_name=request.form.get("full_name","").strip()
    club_id=request.form.get("club_id") or None
    if not all([login,password,student_id,full_name]) or len(password)<8:
        flash(tr("Заполните все поля. Пароль должен содержать минимум 8 символов."))
        return redirect(url_for("operator_dashboard"))
    try:
        con=db()
        personal_points=max(0,int(request.form.get("points",0)))
        con.execute("""INSERT INTO users(login,password_hash,student_id,full_name,club_id,points)
                       VALUES(?,?,?,?,?,?)""",
                    (login,generate_password_hash(password),student_id,full_name,club_id,personal_points))
        con.commit(); con.close(); flash(tr("Аккаунт пользователя создан."))
    except ((psycopg.IntegrityError,) if psycopg else (sqlite3.IntegrityError,)):
        flash(tr("Такой логин или ID ученика уже существует."))
    return redirect(url_for("operator_dashboard"))


@app.post("/operator/user/points/<int:user_id>")
@operator_required
def update_user_points(user_id):
    try:
        points = max(0, int(request.form.get("points", 0)))
        con = db()
        con.execute("UPDATE users SET points=? WHERE id=?", (points, user_id))
        con.commit()
        con.close()
        flash(tr("Личные баллы ученика обновлены."))
    except ValueError:
        flash(tr("Введите корректное целое число баллов."))
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/user/club/<int:user_id>")
@operator_required
def update_user_club(user_id):
    """Allow an authenticated operator to move a student to another club."""
    raw_club_id = request.form.get("club_id", "").strip()
    con = db()
    user = con.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        con.close()
        flash("Ученик не найден." if session.get("language", "ru") == "ru" else "O‘quvchi topilmadi.")
        return redirect(url_for("operator_dashboard"))

    club_id = None
    if raw_club_id:
        try:
            club_id = int(raw_club_id)
        except ValueError:
            con.close()
            flash("Выберите корректный клуб." if session.get("language", "ru") == "ru" else "To‘g‘ri klubni tanlang.")
            return redirect(url_for("operator_dashboard"))
        club = con.execute("SELECT id FROM clubs WHERE id=?", (club_id,)).fetchone()
        if not club:
            con.close()
            flash("Выбранный клуб не найден." if session.get("language", "ru") == "ru" else "Tanlangan klub topilmadi.")
            return redirect(url_for("operator_dashboard"))

    con.execute("UPDATE clubs SET president_user_id=NULL WHERE president_user_id=? AND id<>COALESCE(?, -1)", (user_id, club_id))
    con.execute("UPDATE users SET club_id=? WHERE id=?", (club_id, user_id))
    con.commit()
    con.close()
    flash("Клуб ученика обновлён." if session.get("language", "ru") == "ru" else "O‘quvchining klubi yangilandi.")
    return redirect(url_for("operator_dashboard"))


@app.post("/operator/club/<int:club_id>/president")
@operator_required
def set_club_president(club_id):
    raw_user_id = request.form.get("user_id", "").strip()
    con = db()
    club = con.execute("SELECT id FROM clubs WHERE id=?", (club_id,)).fetchone()
    if not club:
        con.close()
        flash("Клуб не найден.")
        return redirect(url_for("operator_dashboard"))
    user_id = None
    if raw_user_id:
        try:
            user_id = int(raw_user_id)
        except ValueError:
            con.close()
            flash("Выберите корректного ученика.")
            return redirect(url_for("operator_dashboard"))
        member = con.execute("SELECT id FROM users WHERE id=? AND club_id=?", (user_id, club_id)).fetchone()
        if not member:
            con.close()
            flash("Президентом можно назначить только ученика этого клуба.")
            return redirect(url_for("operator_dashboard"))
        # One student may be president of only one club.
        con.execute("UPDATE clubs SET president_user_id=NULL WHERE president_user_id=?", (user_id,))
    con.execute("UPDATE clubs SET president_user_id=? WHERE id=?", (user_id, club_id))
    con.commit()
    con.close()
    flash("Президент клуба обновлён.")
    return redirect(url_for("operator_dashboard"))


@app.post("/operator/user/delete/<int:user_id>")
@operator_required
def delete_user(user_id):
    con=db(); con.execute("DELETE FROM users WHERE id=?",(user_id,)); con.commit(); con.close()
    flash(tr("Аккаунт удалён."))
    return redirect(url_for("operator_dashboard"))

@app.route("/user/settings", methods=["GET", "POST"])
@user_required
def user_settings():
    con = db()
    user = con.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if not user:
        con.close()
        session.pop("user_id", None)
        return redirect(url_for("user_login"))

    if request.method == "POST":
        action = request.form.get("action", "password")
        if action == "photo":
            photo = request.files.get("photo")
            if not photo or not photo.filename:
                flash("Выберите фотографию профиля.")
            else:
                data = photo.read(2 * 1024 * 1024 + 1)
                mime = photo.mimetype
                valid = ((mime == "image/jpeg" and data.startswith(b"\xff\xd8\xff")) or
                         (mime == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n")) or
                         (mime == "image/webp" and len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"))
                if len(data) > 2 * 1024 * 1024 or not valid:
                    flash("Используйте JPG, PNG или WEBP размером не более 2 МБ.")
                else:
                    con.execute("UPDATE users SET avatar_data=?, avatar_mime=? WHERE id=?",
                                (data, mime, session["user_id"]))
                    con.commit()
                    flash("Фото профиля обновлено.")
        elif action == "password":
            current = request.form.get("current_password", "")
            new = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")
            if not check_password_hash(user["password_hash"], current):
                flash("Текущий пароль указан неверно.")
            elif len(new) < 8:
                flash("Новый пароль должен содержать минимум 8 символов.")
            elif new != confirm:
                flash("Новые пароли не совпадают.")
            else:
                con.execute("UPDATE users SET password_hash=? WHERE id=?",
                            (generate_password_hash(new), session["user_id"]))
                con.commit()
                flash("Пароль успешно изменён.")
        con.close()
        return redirect(url_for("user_settings"))

    con.close()
    return render_template("user_settings.html", user=user)

@app.route("/user/club-requests", methods=["GET", "POST"])
@user_required
def user_club_requests():
    con = db()
    if request.method == "POST":
        try:
            club_id = int(request.form.get("club_id", ""))
        except ValueError:
            club_id = 0
        club = con.execute("SELECT id FROM clubs WHERE id=?", (club_id,)).fetchone()
        current = con.execute("SELECT club_id FROM users WHERE id=?", (session["user_id"],)).fetchone()
        pending = con.execute("SELECT id FROM club_join_requests WHERE user_id=? AND status='pending'", (session["user_id"],)).fetchone()
        if not club:
            flash("Выберите существующий клуб.")
        elif current and current["club_id"]:
            flash("Вы уже состоите в клубе. Сначала попросите оператора исключить вас из него.")
        elif pending:
            flash("У вас уже есть заявка на рассмотрении.")
        else:
            con.execute("INSERT INTO club_join_requests(user_id, club_id) VALUES(?,?)", (session["user_id"], club_id))
            con.commit()
            flash("Заявка отправлена. Её может принять президент клуба или оператор.")
        con.close()
        return redirect(url_for("user_club_requests"))
    clubs = con.execute("SELECT id, name FROM clubs ORDER BY name").fetchall()
    requests = con.execute("SELECT r.*, c.name AS club_name FROM club_join_requests r JOIN clubs c ON c.id=r.club_id WHERE r.user_id=? ORDER BY r.id DESC", (session["user_id"],)).fetchall()
    con.close()
    return render_template("club_join_requests.html", clubs=clubs, requests=requests)

@app.route("/club/president/manage", methods=["GET"])
@user_required
def president_manage_club():
    con = db()
    club = con.execute("SELECT id, name FROM clubs WHERE president_user_id=?", (session["user_id"],)).fetchone()
    if not club:
        con.close()
        flash("У вас нет прав президента клуба.")
        return redirect(url_for("user_dashboard"))
    requests = con.execute("""SELECT r.id, r.created_at, u.full_name, u.student_id
        FROM club_join_requests r JOIN users u ON u.id=r.user_id
        WHERE r.club_id=? AND r.status='pending' ORDER BY r.id""", (club["id"],)).fetchall()
    members = con.execute("SELECT id, full_name, student_id FROM users WHERE club_id=? ORDER BY full_name", (club["id"],)).fetchall()
    con.close()
    return render_template("president_manage.html", club=club, requests=requests, members=members)

@app.post("/club/president/request/<int:request_id>/<decision>")
@user_required
def president_review_request(request_id, decision):
    if decision not in ("approve", "reject"):
        return redirect(url_for("president_manage_club"))
    con = db()
    club = con.execute("SELECT id FROM clubs WHERE president_user_id=?", (session["user_id"],)).fetchone()
    if not club:
        con.close(); flash("Нет прав президента."); return redirect(url_for("user_dashboard"))
    req = con.execute("SELECT id, user_id, club_id FROM club_join_requests WHERE id=? AND club_id=? AND status='pending'", (request_id, club["id"])).fetchone()
    if not req:
        con.close(); flash("Заявка не найдена или уже обработана."); return redirect(url_for("president_manage_club"))
    if decision == "approve":
        con.execute("UPDATE users SET club_id=? WHERE id=? AND club_id IS NULL", (club["id"], req["user_id"]))
        con.execute("UPDATE club_join_requests SET status='approved', reviewed_at=CURRENT_TIMESTAMP, reviewed_by_user_id=? WHERE id=?", (session["user_id"], request_id))
        flash("Заявка принята.")
    else:
        con.execute("UPDATE club_join_requests SET status='rejected', reviewed_at=CURRENT_TIMESTAMP, reviewed_by_user_id=? WHERE id=?", (session["user_id"], request_id))
        flash("Заявка отклонена.")
    con.commit(); con.close()
    return redirect(url_for("president_manage_club"))

@app.post("/club/president/remove/<int:user_id>")
@user_required
def president_remove_member(user_id):
    con = db()
    club = con.execute("SELECT id FROM clubs WHERE president_user_id=?", (session["user_id"],)).fetchone()
    if not club:
        con.close(); flash("Нет прав президента."); return redirect(url_for("user_dashboard"))
    member = con.execute("SELECT id FROM users WHERE id=? AND club_id=?", (user_id, club["id"])).fetchone()
    if not member or user_id == session["user_id"]:
        con.close(); flash("Нельзя исключить этого пользователя."); return redirect(url_for("president_manage_club"))
    con.execute("UPDATE users SET club_id=NULL WHERE id=?", (user_id,))
    con.commit(); con.close(); flash("Ученик исключён из клуба.")
    return redirect(url_for("president_manage_club"))

@app.route("/operator/club-requests")
@operator_required
def operator_club_requests():
    con = db()
    requests = con.execute("""SELECT r.id, r.created_at, u.full_name, u.student_id, c.name AS club_name
        FROM club_join_requests r JOIN users u ON u.id=r.user_id JOIN clubs c ON c.id=r.club_id
        WHERE r.status='pending' ORDER BY r.id""").fetchall()
    con.close()
    return render_template("operator_club_requests.html", requests=requests)

@app.post("/operator/club-request/<int:request_id>/<decision>")
@operator_required
def operator_review_club_request(request_id, decision):
    if decision not in ("approve", "reject"):
        return redirect(url_for("operator_club_requests"))
    con = db()
    req = con.execute("SELECT id, user_id, club_id FROM club_join_requests WHERE id=? AND status='pending'", (request_id,)).fetchone()
    if not req:
        con.close(); flash("Заявка не найдена или уже обработана."); return redirect(url_for("operator_club_requests"))
    if decision == "approve":
        con.execute("UPDATE users SET club_id=? WHERE id=?", (req["club_id"], req["user_id"]))
        con.execute("UPDATE clubs SET president_user_id=NULL WHERE president_user_id=? AND id<>?", (req["user_id"], req["club_id"]))
        con.execute("UPDATE club_join_requests SET status='approved', reviewed_at=CURRENT_TIMESTAMP, reviewed_by_operator_id=? WHERE id=?", (session["operator_id"], request_id))
        flash("Заявка принята, ученик добавлен в клуб.")
    else:
        con.execute("UPDATE club_join_requests SET status='rejected', reviewed_at=CURRENT_TIMESTAMP, reviewed_by_operator_id=? WHERE id=?", (session["operator_id"], request_id))
        flash("Заявка отклонена.")
    con.commit(); con.close()
    return redirect(url_for("operator_club_requests"))

@app.route("/user/avatar/<int:user_id>")
@user_required
def user_avatar(user_id):
    con = db()
    row = con.execute("SELECT avatar_data, avatar_mime FROM users WHERE id=?", (user_id,)).fetchone()
    con.close()
    if not row or not row["avatar_data"]:
        return "", 404
    return Response(bytes(row["avatar_data"]), mimetype=row["avatar_mime"] or "image/jpeg",
                    headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})

@app.route("/operator/avatar/<int:user_id>")
@operator_required
def operator_user_avatar(user_id):
    con=db()
    row=con.execute("SELECT avatar_data, avatar_mime FROM users WHERE id=?", (user_id,)).fetchone()
    con.close()
    if not row or not row["avatar_data"]:
        return "", 404
    return Response(bytes(row["avatar_data"]), mimetype=row["avatar_mime"] or "image/jpeg",
                    headers={"Cache-Control":"private, max-age=300","X-Content-Type-Options":"nosniff"})

@app.route("/news/image/<int:news_id>")
def news_image(news_id):
    con=db()
    row=con.execute("SELECT image_data,image_mime FROM news WHERE id=?", (news_id,)).fetchone()
    con.close()
    if not row or not row["image_data"]:
        return "", 404
    return Response(bytes(row["image_data"]), mimetype=row["image_mime"] or "image/jpeg",
                    headers={"Cache-Control":"public, max-age=3600","X-Content-Type-Options":"nosniff"})

@app.route("/user")
@user_required
def user_dashboard():
    con=db()
    user=con.execute("""SELECT u.*, c.name AS club_name,
                        (SELECT COALESCE(SUM(u2.points),0) FROM users u2 WHERE u2.club_id=u.club_id) AS club_points,
                        c.members AS club_members FROM users u LEFT JOIN clubs c ON c.id=u.club_id
                        WHERE u.id=?""",(session["user_id"],)).fetchone()
    clubs=con.execute("""SELECT c.*, COALESCE(SUM(u.points),0) AS points FROM clubs c
                        LEFT JOIN users u ON u.club_id=c.id GROUP BY c.id ORDER BY COALESCE(SUM(u.points),0) DESC""").fetchall()
    president_club = con.execute("SELECT id, name FROM clubs WHERE president_user_id=?", (session["user_id"],)).fetchone()
    con.close()
    return render_template("user.html", user=user, clubs=clubs, president_club=president_club)

@app.route("/user/messages", methods=["GET", "POST"])
@user_required
def user_messages():
    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        if not subject or not body:
            flash("Введите тему и текст сообщения.")
        elif len(subject) > 160 or len(body) > 5000:
            flash("Тема — до 160 символов, сообщение — до 5000 символов.")
        else:
            con = db()
            con.execute("INSERT INTO student_messages(user_id, subject, body) VALUES(?,?,?)",
                        (session["user_id"], subject, body))
            con.commit()
            con.close()
            flash("Ваш вопрос отправлен оператору.")
        return redirect(url_for("user_messages"))

    con = db()
    messages = con.execute(
        "SELECT * FROM student_messages WHERE user_id=? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()
    con.close()
    return render_template("user_messages.html", messages=messages)


@app.post("/operator/message/reply/<int:message_id>")
@operator_required
def reply_student_message(message_id):
    reply = request.form.get("reply", "").strip()
    if not reply:
        flash("Введите ответ ученику.")
    elif len(reply) > 5000:
        flash("Ответ не должен превышать 5000 символов.")
    else:
        con = db()
        row = con.execute("SELECT id FROM student_messages WHERE id=?", (message_id,)).fetchone()
        if row:
            con.execute("""UPDATE student_messages
                           SET reply=?, status='replied', replied_at=CURRENT_TIMESTAMP
                           WHERE id=?""", (reply, message_id))
            con.commit()
            flash("Ответ отправлен ученику.")
        else:
            flash("Сообщение не найдено.")
        con.close()
    return redirect(url_for("operator_dashboard"))


BOOKS = {
    "men": {"title": "Мен — Фотих Думан", "questions": [
        "Asarning asosiy g‘oyasini o‘z so‘zlaringiz bilan tushuntiring.",
        "Asardagi sizga eng ta’sir qilgan voqea yoki fikr qaysi? Nima uchun?",
        "Asar qahramoni yoki muallif fikridan qanday xulosa chiqardingiz?",
        "Asar nomi mazmun bilan qanday bog‘langan deb o‘ylaysiz?",
        "Asarni boshqa o‘quvchiga tavsiya qilarmidingiz? Sababini yozing."
    ]},
    "dunyo": {"title": "Дунёнинг ишлари — Ўткир Ҳошимов", "questions": [
        "Asarning asosiy mavzusi va g‘oyasini tushuntiring.",
        "Ona obrazi asarda qanday tasvirlangan? Misollar bilan izohlang.",
        "Sizga eng kuchli ta’sir qilgan hikoya yoki epizod qaysi? Nima uchun?",
        "Asarda qanday insoniy qadriyatlar yoritilgan?",
        "Asarni o‘qib qanday xulosa chiqardingiz?"
    ]},
    "otam": {"title": "Отамдан қолган далалар — Тоғай Мурод", "questions": [
        "Asarda xalq hayoti va tarixiy xotira qanday yoritilgan?",
        "Asar nomidagi ‘dalalar’ timsolini qanday tushunasiz?",
        "Asardagi bosh qahramonlar taqdiri orqali qanday muammolar ko‘rsatilgan?",
        "Asarning sizga eng ta’sir qilgan jihatini izohlang.",
        "Muallif o‘quvchiga qanday fikrni yetkazmoqchi deb o‘ylaysiz?"
    ]}
}

@app.route("/books")
@user_required
def book_quizzes():
    con=db()
    submissions=con.execute("SELECT * FROM book_quiz_submissions WHERE user_id=? ORDER BY id DESC",(session["user_id"],)).fetchall()
    con.close()
    display_books = BOOKS if session.get("language", "ru") == "uz" else {
        "men": {"title": "Мен — Фотих Думан", "questions": [
            "Объясните своими словами основную идею произведения.",
            "Какой эпизод или мысль произвели на вас наибольшее впечатление? Почему?",
            "Какой вывод вы сделали из поступков героя или мыслей автора?",
            "Как, по вашему мнению, название связано с содержанием?",
            "Посоветовали бы вы эту книгу другому читателю? Почему?"]},
        "dunyo": {"title": "Дунёнинг ишлари — Ўткир Ҳошимов", "questions": [
            "Объясните основную тему и идею произведения.",
            "Как в произведении показан образ матери? Приведите примеры.",
            "Какой рассказ или эпизод затронул вас сильнее всего? Почему?",
            "Какие человеческие ценности раскрываются в произведении?",
            "Какой вывод вы сделали после прочтения?"]},
        "otam": {"title": "Отамдан қолган далалар — Тоғай Мурод", "questions": [
            "Как в произведении раскрываются жизнь народа и историческая память?",
            "Как вы понимаете образ «полей» в названии произведения?",
            "Какие проблемы показаны через судьбы героев?",
            "Какая сторона произведения произвела на вас наибольшее впечатление?",
            "Какую мысль автор хотел донести до читателя?"]}
    }
    return render_template("books.html", books=display_books, submissions=submissions)

@app.post("/books/submit/<book_key>")
@user_required
def submit_book_quiz(book_key):
    book=BOOKS.get(book_key)
    if not book:
        flash("Kitob testi topilmadi.")
        return redirect(url_for("book_quizzes"))
    answers=[]
    for i, question in enumerate(book["questions"],1):
        answer=request.form.get(f"answer_{i}","").strip()
        if not answer:
            flash("Iltimos, barcha savollarga javob bering.")
            return redirect(url_for("book_quizzes"))
        answers.append({"question":question,"answer":answer})
    con=db()
    con.execute("INSERT INTO book_quiz_submissions(user_id,book_key,answers) VALUES(?,?,?)",
                (session["user_id"],book_key,json.dumps(answers,ensure_ascii=False)))
    con.commit(); con.close()
    flash("Javoblaringiz operatorga tekshirish uchun yuborildi.")
    return redirect(url_for("book_quizzes"))

@app.post("/operator/book-review/<int:submission_id>")
@operator_required
def review_book_quiz(submission_id):
    try:
        points=max(0,int(request.form.get("points","0")))
        note=request.form.get("note","").strip()
    except ValueError:
        flash("Ball uchun butun son kiriting.")
        return redirect(url_for("operator_dashboard"))
    con=db()
    row=con.execute("SELECT * FROM book_quiz_submissions WHERE id=? AND status='pending'",(submission_id,)).fetchone()
    if not row:
        con.close(); flash("Bu ish allaqachon tekshirilgan yoki topilmadi.")
        return redirect(url_for("operator_dashboard"))
    con.execute("UPDATE book_quiz_submissions SET status='reviewed', awarded_points=?, operator_note=?, reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
                (points,note,submission_id))
    con.execute("UPDATE users SET points=points+? WHERE id=?",(points,row["user_id"]))
    con.commit(); con.close()
    flash("Natija tasdiqlandi. Ballar o‘quvchi va uning klubiga qo‘shildi.")
    return redirect(url_for("operator_dashboard"))

@app.route("/operator/logout")
def operator_logout():
    session.pop("operator_id", None)
    return redirect(url_for("home"))

@app.route("/user/logout")
def user_logout():
    session.pop("user_id", None)
    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/news")
def news_catalog():
    con=db()
    news_items=con.execute("SELECT n.*, c.name AS club_name FROM news n LEFT JOIN clubs c ON c.id=n.club_id ORDER BY n.created_at DESC, n.id DESC").fetchall()
    president_club = None
    if session.get("user_id"):
        president_club = con.execute("SELECT c.id, c.name FROM clubs c WHERE c.president_user_id=?", (session["user_id"],)).fetchone()
    con.close()
    return render_template("news.html", news_items=news_items, president_club=president_club)

@app.route("/tournaments")
def tournaments_catalog():
    con=db()
    tournaments=con.execute("""SELECT t.*, COUNT(r.id) AS registered,
        SUM(CASE WHEN r.user_id=? THEN 1 ELSE 0 END) AS joined
        FROM tournaments t LEFT JOIN tournament_registrations r ON r.tournament_id=t.id
        GROUP BY t.id ORDER BY t.event_date, t.id DESC""",
        (session.get("user_id", -1),)).fetchall()
    con.close()
    return render_template("tournaments.html", tournaments=tournaments)

@app.post("/tournament/<int:tournament_id>/register")
@user_required
def register_tournament(tournament_id):
    con=db()
    tournament=con.execute("SELECT * FROM tournaments WHERE id=?", (tournament_id,)).fetchone()
    if not tournament:
        con.close(); flash(tr("Турнир не найден."))
        return redirect(url_for("tournaments_catalog"))
    if tournament["status"] != "open":
        con.close(); flash(tr("Регистрация на этот турнир закрыта."))
        return redirect(url_for("tournaments_catalog"))
    existing=con.execute("SELECT id FROM tournament_registrations WHERE tournament_id=? AND user_id=?",
                         (tournament_id, session["user_id"])).fetchone()
    if existing:
        con.close(); flash(tr("Вы уже зарегистрированы на этот турнир."))
        return redirect(url_for("tournaments_catalog"))
    count=con.execute("SELECT COUNT(*) AS n FROM tournament_registrations WHERE tournament_id=?",
                      (tournament_id,)).fetchone()["n"]
    if tournament["capacity"] > 0 and count >= tournament["capacity"]:
        con.close(); flash(tr("Свободных мест больше нет."))
        return redirect(url_for("tournaments_catalog"))
    try:
        con.execute("INSERT INTO tournament_registrations(tournament_id,user_id) VALUES(?,?)",
                    (tournament_id, session["user_id"]))
        con.commit(); flash(tr("Вы успешно зарегистрированы на турнир."))
    except Exception:
        con.close(); flash(tr("Не удалось зарегистрироваться. Возможно, вы уже записаны."))
        return redirect(url_for("tournaments_catalog"))
    con.close()
    return redirect(url_for("tournaments_catalog"))

@app.post("/club/president/news")
@user_required
def create_club_news():
    title = request.form.get("title", "").strip()
    body = request.form.get("body", "").strip()
    photo = request.files.get("photo")
    image_data = None
    image_mime = None
    if photo and photo.filename:
        image_data = photo.read(1_500_001)
        image_mime = photo.mimetype
        valid = ((image_mime == "image/jpeg" and image_data.startswith(b"\xff\xd8\xff")) or
                 (image_mime == "image/png" and image_data.startswith(b"\x89PNG\r\n\x1a\n")) or
                 (image_mime == "image/webp" and len(image_data) > 12 and image_data[:4] == b"RIFF" and image_data[8:12] == b"WEBP"))
        if len(image_data) > 1_500_000 or not valid:
            flash("Фото должно быть JPG, PNG или WEBP размером не более 1,5 МБ.")
            return redirect(url_for("news_catalog"))
    con = db()
    club = con.execute("SELECT id FROM clubs WHERE president_user_id=?", (session["user_id"],)).fetchone()
    if not club:
        con.close()
        flash("Публиковать новости клуба может только назначенный президент.")
        return redirect(url_for("news_catalog"))
    if not title or not body:
        con.close()
        flash("Заполните заголовок и текст новости.")
        return redirect(url_for("news_catalog"))
    con.execute("INSERT INTO news(title,body,image_data,image_mime,club_id,author_user_id) VALUES(?,?,?,?,?,?)",
                (title, body, image_data, image_mime, club["id"], session["user_id"]))
    con.commit()
    con.close()
    flash("Новость клуба опубликована.")
    return redirect(url_for("news_catalog"))


@app.post("/operator/news")
@operator_required
def create_news():
    title=request.form.get("title","").strip()
    body=request.form.get("body","").strip()
    photo=request.files.get("photo")
    image_data=None
    image_mime=None
    if photo and photo.filename:
        image_data=photo.read(1_500_001)
        image_mime=photo.mimetype
        valid=((image_mime=="image/jpeg" and image_data.startswith(b"\xff\xd8\xff")) or
               (image_mime=="image/png" and image_data.startswith(b"\x89PNG\r\n\x1a\n")) or
               (image_mime=="image/webp" and len(image_data)>12 and image_data[:4]==b"RIFF" and image_data[8:12]==b"WEBP"))
        if len(image_data)>1_500_000 or not valid:
            flash("Фото должно быть JPG, PNG или WEBP размером не более 1,5 МБ.")
            return redirect(url_for("operator_dashboard"))
    if not title or not body:
        flash(tr("Заполните заголовок и текст новости."))
    else:
        con=db()
        con.execute("INSERT INTO news(title,body,image_data,image_mime) VALUES(?,?,?,?)",
                    (title,body,image_data,image_mime))
        con.commit(); con.close(); flash(tr("Новость опубликована."))
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/news/delete/<int:news_id>")
@operator_required
def delete_news(news_id):
    con=db(); con.execute("DELETE FROM news WHERE id=?",(news_id,))
    con.commit(); con.close(); flash(tr("Новость удалена."))
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/tournament")
@operator_required
def create_tournament():
    title=request.form.get("title","").strip()
    description=request.form.get("description","").strip()
    event_date=request.form.get("event_date","").strip()
    status=request.form.get("status","open")
    try:
        capacity=max(0,int(request.form.get("capacity","0")))
        if not title or not event_date or status not in ("open","closed","finished"):
            raise ValueError()
        con=db()
        con.execute("""INSERT INTO tournaments(title,description,event_date,capacity,status)
                       VALUES(?,?,?,?,?)""",(title,description,event_date,capacity,status))
        con.commit(); con.close(); flash(tr("Турнир создан."))
    except ValueError:
        flash(tr("Проверьте название, дату, количество мест и статус турнира."))
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/tournament/status/<int:tournament_id>")
@operator_required
def update_tournament_status(tournament_id):
    status=request.form.get("status","")
    if status in ("open","closed","finished"):
        con=db(); con.execute("UPDATE tournaments SET status=? WHERE id=?",(status,tournament_id))
        con.commit(); con.close(); flash(tr("Статус турнира обновлён."))
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/tournament/delete/<int:tournament_id>")
@operator_required
def delete_tournament(tournament_id):
    con=db(); con.execute("DELETE FROM tournament_registrations WHERE tournament_id=?",(tournament_id,))
    con.execute("DELETE FROM tournaments WHERE id=?",(tournament_id,))
    con.commit(); con.close(); flash(tr("Турнир удалён."))
    return redirect(url_for("operator_dashboard"))


init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
