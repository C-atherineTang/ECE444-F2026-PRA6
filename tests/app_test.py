import pytest
from pathlib import Path
import json

from project.app import app, db
from project.models import Post

TEST_DB = "test.db"


# Runs before and after every test. Builds a test client, clears posts first,
# then clears them again after the test so tests do not affect each other.
@pytest.fixture
def client():
    BASE_DIR = Path(__file__).resolve().parent.parent
    app.config["TESTING"] = True
    app.config["DATABASE"] = BASE_DIR.joinpath(TEST_DB)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{BASE_DIR.joinpath(TEST_DB)}"

    with app.app_context():
        db.create_all()  # create the post table if it does not exist
        db.session.query(Post).delete()
        db.session.commit()
        yield app.test_client()  # the test runs at this point
        db.session.query(Post).delete()
        db.session.commit()


# Pretend to submit the login form. follow_redirects opens the next page,
# so the test can see the flashed message.
def login(client, username, password):
    """Login helper function"""
    return client.post(
        "/login",
        data=dict(username=username, password=password),
        follow_redirects=True,
    )


# Pretend to visit the logout route and follow the redirect home.
def logout(client):
    """Logout helper function"""
    return client.get("/logout", follow_redirects=True)


# The home page should load successfully.
def test_index(client):
    response = client.get("/", content_type="html/text")
    assert response.status_code == 200


# The SQLite test database file should exist on disk.
def test_database(client):
    """initial test. ensure that the database exists"""
    tester = Path("test.db").is_file()
    assert tester


# With no posts saved, the home page shows the empty-state message.
def test_empty_db(client):
    """Ensure database is blank"""
    rv = client.get("/")
    assert b"No entries yet. Add some!" in rv.data


# Correct admin/admin logs in and logout ends the session.
# A wrong username or password shows the matching error.
def test_login_logout(client):
    """Test login and logout using helper functions"""
    rv = login(client, app.config["USERNAME"], app.config["PASSWORD"])
    assert b"You were logged in" in rv.data
    rv = logout(client)
    assert b"You were logged out" in rv.data
    rv = login(client, app.config["USERNAME"] + "x", app.config["PASSWORD"])
    assert b"Invalid username" in rv.data
    rv = login(client, app.config["USERNAME"], app.config["PASSWORD"] + "x")
    assert b"Invalid password" in rv.data


# A logged-in user can add a post. The title is escaped so tags show as text.
# The body is marked safe, so its HTML is kept.
def test_messages(client):
    """Ensure that user can post messages"""
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    rv = client.post(
        "/add",
        data=dict(title="<Hello>", text="<strong>HTML</strong> allowed here"),
        follow_redirects=True,
    )
    assert b"No entries here so far" not in rv.data
    # "<Hello>" was escaped to "&lt;Hello&gt;"
    assert b"&lt;Hello&gt;" in rv.data
    assert b"<strong>HTML</strong> allowed here" in rv.data


# Logged-out delete is rejected with status 0.
# After login, the same delete returns status 1.
def test_delete_message(client):
    """Ensure the messages are being deleted"""
    rv = client.get("/delete/1")
    data = json.loads(rv.data)
    assert data["status"] == 0
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    rv = client.get("/delete/1")
    data = json.loads(rv.data)
    assert data["status"] == 1


# The search page loads, and a query keeps the matching post only.
def test_search(client):
    """Ensure posts can be searched by title or text."""
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    client.post(
        "/add",
        data=dict(title="Hello search", text="find this post"),
        follow_redirects=True,
    )
    client.post(
        "/add",
        data=dict(title="Other", text="unrelated"),
        follow_redirects=True,
    )

    # Opening /search/ with no query shows the search form.
    rv = client.get("/search/")
    assert rv.status_code == 200
    assert b"Search" in rv.data

    # "search" matches the first post and leaves out the unrelated one.
    rv = client.get("/search/", query_string={"query": "search"})
    assert rv.status_code == 200
    assert b"Hello search" in rv.data
    assert b"find this post" in rv.data
    assert b"unrelated" not in rv.data
