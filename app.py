
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3, os
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

class PostgresConnection:
    """Compatibility wrapper retaining the app's qmark SQL placeholders."""
    def __init__(self, conn): self.conn = conn
    def execute(self, sql, params=()): return self.conn.execute(sql.replace("?", "%s"), params)
    def commit(self): self.conn.commit()
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
          id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS users (
          id SERIAL PRIMARY KEY, login TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
          student_id TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL, club_id INTEGER,
          points INTEGER NOT NULL DEFAULT 0
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS clubs (
          id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL,
          members INTEGER NOT NULL DEFAULT 0, points INTEGER NOT NULL DEFAULT 0
        )""")
        con.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS points INTEGER NOT NULL DEFAULT 0")
        con.execute("""CREATE TABLE IF NOT EXISTS news (
          id SERIAL PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
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
    else:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS operators (
          id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL
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
        user_columns = [row["name"] for row in con.execute("PRAGMA table_info(users)").fetchall()]
        if "points" not in user_columns:
            con.execute("ALTER TABLE users ADD COLUMN points INTEGER NOT NULL DEFAULT 0")
    if not con.execute("SELECT id FROM operators LIMIT 1").fetchone():
        initial_username = os.environ.get("OPERATOR_USERNAME", "admin").strip()
        initial_password = os.environ.get("OPERATOR_PASSWORD", "ChangeMe2026!")
        con.execute("INSERT INTO operators(username,password_hash) VALUES(?,?)",
                    (initial_username, generate_password_hash(initial_password)))
    if not con.execute("SELECT id FROM clubs LIMIT 1").fetchone():
        for name, members, points in [("Клуб науки",18,860),("Клуб творчества",15,740),("Клуб спорта",22,690),("Клуб IT",12,620)]:
            con.execute("INSERT INTO clubs(name,members,points) VALUES(?,?,?)", (name,members,points))
    con.commit(); con.close()

def operator_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if session.get("role") != "operator":
            return redirect(url_for("operator_login"))
        return fn(*args, **kwargs)
    return wrapped

def user_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if session.get("role") != "user":
            return redirect(url_for("user_login"))
        return fn(*args, **kwargs)
    return wrapped

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/operator/login", methods=["GET","POST"])
def operator_login():
    if request.method == "POST":
        con = db()
        row = con.execute("SELECT * FROM operators WHERE username=?", (request.form["login"].strip(),)).fetchone()
        con.close()
        if row and check_password_hash(row["password_hash"], request.form["password"]):
            session.clear(); session.permanent=True; session["role"]="operator"; session["operator_id"]=row["id"]
            return redirect(url_for("operator_dashboard"))
        flash("Неверный логин или пароль.")
    return render_template("login.html", title="Вход оператора", action=url_for("operator_login"))

@app.route("/user/login", methods=["GET","POST"])
def user_login():
    if request.method == "POST":
        con = db()
        row = con.execute("SELECT * FROM users WHERE login=?", (request.form["login"].strip(),)).fetchone()
        con.close()
        if row and check_password_hash(row["password_hash"], request.form["password"]):
            session.clear(); session.permanent=True; session["role"]="user"; session["user_id"]=row["id"]
            return redirect(url_for("user_dashboard"))
        flash("Неверный логин или пароль.")
    return render_template("login.html", title="Вход пользователя", action=url_for("user_login"))

@app.route("/operator")
@operator_required
def operator_dashboard():
    con=db()
    clubs=con.execute("""SELECT c.*, COUNT(u.id) AS real_members
                         FROM clubs c LEFT JOIN users u ON u.club_id=c.id
                         GROUP BY c.id ORDER BY c.points DESC""").fetchall()
    users=con.execute("""SELECT u.*, c.name AS club_name FROM users u
                         LEFT JOIN clubs c ON c.id=u.club_id ORDER BY u.full_name""").fetchall()
    totals=con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    points=con.execute("SELECT COALESCE(SUM(points),0) n FROM clubs").fetchone()["n"]
    news_items=con.execute("SELECT * FROM news ORDER BY created_at DESC, id DESC").fetchall()
    tournaments=con.execute("""SELECT t.*, COUNT(r.id) AS registered FROM tournaments t
        LEFT JOIN tournament_registrations r ON r.tournament_id=t.id
        GROUP BY t.id ORDER BY t.event_date, t.id DESC""").fetchall()
    registrations=con.execute("""SELECT t.title AS tournament_title, u.full_name, u.student_id
        FROM tournament_registrations r JOIN tournaments t ON t.id=r.tournament_id
        JOIN users u ON u.id=r.user_id ORDER BY t.event_date, t.title, u.full_name""").fetchall()
    con.close()
    return render_template("operator.html", clubs=clubs, users=users, total_users=totals,
                           total_points=points, news_items=news_items, tournaments=tournaments,
                           registrations=registrations)

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
            con.execute("UPDATE clubs SET name=?,members=?,points=? WHERE id=?",
                        (name,members,points,int(club_id)))
        else:
            con.execute("INSERT INTO clubs(name,members,points) VALUES(?,?,?)",(name,members,points))
        con.commit(); con.close(); flash("Клуб сохранён.")
    except (ValueError, sqlite3.IntegrityError) + ((psycopg.IntegrityError,) if psycopg else ()):
        flash("Проверьте данные: название должно быть уникальным, баллы и участники — целыми числами.")
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/club/delete/<int:club_id>")
@operator_required
def delete_club(club_id):
    con=db()
    con.execute("UPDATE users SET club_id=NULL WHERE club_id=?",(club_id,))
    con.execute("DELETE FROM clubs WHERE id=?",(club_id,))
    con.commit(); con.close(); flash("Клуб удалён.")
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
        flash("Заполните все поля. Пароль должен содержать минимум 8 символов.")
        return redirect(url_for("operator_dashboard"))
    try:
        con=db()
        personal_points=max(0,int(request.form.get("points",0)))
        con.execute("""INSERT INTO users(login,password_hash,student_id,full_name,club_id,points)
                       VALUES(?,?,?,?,?,?)""",
                    (login,generate_password_hash(password),student_id,full_name,club_id,personal_points))
        con.commit(); con.close(); flash("Аккаунт пользователя создан.")
    except ((psycopg.IntegrityError,) if psycopg else (sqlite3.IntegrityError,)):
        flash("Такой логин или ID ученика уже существует.")
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
        flash("Личные баллы ученика обновлены.")
    except ValueError:
        flash("Введите корректное целое число баллов.")
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/user/delete/<int:user_id>")
@operator_required
def delete_user(user_id):
    con=db(); con.execute("DELETE FROM users WHERE id=?",(user_id,)); con.commit(); con.close()
    flash("Аккаунт удалён.")
    return redirect(url_for("operator_dashboard"))

@app.route("/user")
@user_required
def user_dashboard():
    con=db()
    user=con.execute("""SELECT u.*, c.name AS club_name, c.points AS club_points,
                        c.members AS club_members FROM users u LEFT JOIN clubs c ON c.id=u.club_id
                        WHERE u.id=?""",(session["user_id"],)).fetchone()
    clubs=con.execute("SELECT * FROM clubs ORDER BY points DESC").fetchall()
    con.close()
    return render_template("user.html", user=user, clubs=clubs)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/news")
def news_catalog():
    con=db()
    news_items=con.execute("SELECT * FROM news ORDER BY created_at DESC, id DESC").fetchall()
    con.close()
    return render_template("news.html", news_items=news_items)

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
        con.close(); flash("Турнир не найден.")
        return redirect(url_for("tournaments_catalog"))
    if tournament["status"] != "open":
        con.close(); flash("Регистрация на этот турнир закрыта.")
        return redirect(url_for("tournaments_catalog"))
    existing=con.execute("SELECT id FROM tournament_registrations WHERE tournament_id=? AND user_id=?",
                         (tournament_id, session["user_id"])).fetchone()
    if existing:
        con.close(); flash("Вы уже зарегистрированы на этот турнир.")
        return redirect(url_for("tournaments_catalog"))
    count=con.execute("SELECT COUNT(*) AS n FROM tournament_registrations WHERE tournament_id=?",
                      (tournament_id,)).fetchone()["n"]
    if tournament["capacity"] > 0 and count >= tournament["capacity"]:
        con.close(); flash("Свободных мест больше нет.")
        return redirect(url_for("tournaments_catalog"))
    try:
        con.execute("INSERT INTO tournament_registrations(tournament_id,user_id) VALUES(?,?)",
                    (tournament_id, session["user_id"]))
        con.commit(); flash("Вы успешно зарегистрированы на турнир.")
    except Exception:
        con.close(); flash("Не удалось зарегистрироваться. Возможно, вы уже записаны.")
        return redirect(url_for("tournaments_catalog"))
    con.close()
    return redirect(url_for("tournaments_catalog"))

@app.post("/operator/news")
@operator_required
def create_news():
    title=request.form.get("title","").strip()
    body=request.form.get("body","").strip()
    if not title or not body:
        flash("Заполните заголовок и текст новости.")
    else:
        con=db()
        con.execute("INSERT INTO news(title,body) VALUES(?,?)",(title,body))
        con.commit(); con.close(); flash("Новость опубликована.")
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/news/delete/<int:news_id>")
@operator_required
def delete_news(news_id):
    con=db(); con.execute("DELETE FROM news WHERE id=?",(news_id,))
    con.commit(); con.close(); flash("Новость удалена.")
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
        con.commit(); con.close(); flash("Турнир создан.")
    except ValueError:
        flash("Проверьте название, дату, количество мест и статус турнира.")
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/tournament/status/<int:tournament_id>")
@operator_required
def update_tournament_status(tournament_id):
    status=request.form.get("status","")
    if status in ("open","closed","finished"):
        con=db(); con.execute("UPDATE tournaments SET status=? WHERE id=?",(status,tournament_id))
        con.commit(); con.close(); flash("Статус турнира обновлён.")
    return redirect(url_for("operator_dashboard"))

@app.post("/operator/tournament/delete/<int:tournament_id>")
@operator_required
def delete_tournament(tournament_id):
    con=db(); con.execute("DELETE FROM tournament_registrations WHERE tournament_id=?",(tournament_id,))
    con.execute("DELETE FROM tournaments WHERE id=?",(tournament_id,))
    con.commit(); con.close(); flash("Турнир удалён.")
    return redirect(url_for("operator_dashboard"))


init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
