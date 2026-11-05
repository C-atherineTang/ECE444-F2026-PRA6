import os
import re
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    session,
    flash,
    redirect,
    url_for,
    abort,
    jsonify,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError

basedir = Path(__file__).resolve().parent

# Local SQLite file, the one login account, and the key used to sign the session cookie.
DATABASE = "flaskr.db"
USERNAME = "admin"
PASSWORD = "admin"
SECRET_KEY = "change_me"


# Use Postgres when DATABASE_URL is set. Otherwise use the local SQLite file.
# Render's old URLs start with postgres://, which SQLAlchemy does not accept.
def _normalize_database_url(raw):
    """Turn Render's DATABASE_URL into a URL SQLAlchemy can parse."""
    if raw is None or not str(raw).strip():
        return f"sqlite:///{Path(basedir).joinpath(DATABASE)}"

    text = str(raw).strip().strip('"').strip("'")
    match = re.search(r"postgres(?:ql)?(?:\+\w+)?://\S+", text)
    if match:
        text = match.group(0).rstrip(".,);\"'")
    if text.startswith("postgres://"):
        text = text.replace("postgres://", "postgresql://", 1)
    return text


SQLALCHEMY_DATABASE_URI = _normalize_database_url(os.getenv("DATABASE_URL"))
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Stop at startup if the URL cannot be parsed, instead of failing later inside SQLAlchemy.
try:
    make_url(SQLALCHEMY_DATABASE_URI)
except ArgumentError as exc:
    raw = os.getenv("DATABASE_URL") or ""
    recognizable = raw.lstrip().startswith(
        ("postgres://", "postgresql://", "sqlite://")
    )
    detail = (
        "starts with a database scheme"
        if recognizable
        else "does not start with postgresql:// or postgres://"
    )
    raise RuntimeError(
        "DATABASE_URL is not a valid database URL. "
        f"The value is {len(raw)} characters and {detail}. "
        "In the Render web service, set DATABASE_URL to the Internal Database URL only, "
        "with no quotes, labels, or extra words."
    ) from exc


# Create the app, copy the uppercase settings above into app.config, and connect the database.
app = Flask(__name__)
app.config.from_object(__name__)
db = SQLAlchemy(app)

# Imported after db exists because models.py uses that db object.
from project import models


# Blocks a route when the user is logged out. status 0 means the request was refused.
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in.")
            return jsonify({"status": 0, "message": "Please log in."}), 401
        return f(*args, **kwargs)

    return decorated_function


# Home page. Loads every post and lets index.html draw them.
@app.route("/")
def index():
    """Searches the database for entries, then displays them."""
    entries = db.session.query(models.Post)
    return render_template("index.html", entries=entries)


# Saves a new post. Logged-out users get 401 and the post is not saved.
@app.route("/add", methods=["POST"])
def add_entry():
    """Adds new post to the database."""
    if not session.get("logged_in"):
        abort(401)
    new_entry = models.Post(request.form["title"], request.form["text"])
    db.session.add(new_entry)
    db.session.commit()
    flash("New entry was successfully posted")
    return redirect(url_for("index"))


# GET shows the login form. POST checks the username and password,
# then stores logged_in in the session cookie.
@app.route("/login", methods=["GET", "POST"])
def login():
    """User login/authentication/session management."""
    error = None
    if request.method == "POST":
        if request.form["username"] != app.config["USERNAME"]:
            error = "Invalid username"
        elif request.form["password"] != app.config["PASSWORD"]:
            error = "Invalid password"
        else:
            session["logged_in"] = True
            flash("You were logged in")
            return redirect(url_for("index"))
    return render_template("login.html", error=error)


# Removes logged_in from the session and sends the user back home.
@app.route("/logout")
def logout():
    """User logout/authentication/session management."""
    session.pop("logged_in", None)
    flash("You were logged out")
    return redirect(url_for("index"))


# Deletes one post by id. login_required returns status 0 when logged out.
# status 1 means the delete code finished. It is still 1 if no row had that id.
@app.route("/delete/<int:post_id>", methods=["GET"])
@login_required
def delete_entry(post_id):
    """Deletes post from database."""
    result = {"status": 0, "message": "Error"}
    try:
        new_id = post_id
        db.session.query(models.Post).filter_by(id=new_id).delete()
        db.session.commit()
        result = {"status": 1, "message": "Post Deleted"}
        flash("The entry was deleted.")
    except Exception as e:
        result = {"status": 0, "message": repr(e)}
    return jsonify(result)


# Search page. The query comes from the URL (?query=...).
# With a query, the template keeps posts whose title or text contains it.
@app.route("/search/", methods=["GET"])
def search():
    query = request.args.get("query")
    entries = db.session.query(models.Post)
    if query:
        return render_template("search.html", entries=entries, query=query)
    return render_template("search.html")


# Starts the development server when this file is run directly.
if __name__ == "__main__":
    app.run()
