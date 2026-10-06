from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os

from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)

app.secret_key = "smart-community-secret-key"

# ==========================================
# DATABASE PATH
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

def init_db():

    conn = get_db()

    # USERS TABLE
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    # HELP REQUESTS TABLE
    conn.execute("""
        CREATE TABLE IF NOT EXISTS help_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            volunteer_id INTEGER
        )
    """)

    # CHECK volunteer_id COLUMN
    columns = conn.execute("""
        PRAGMA table_info(help_requests)
    """).fetchall()

    column_names = [column["name"] for column in columns]

    if "volunteer_id" not in column_names:

        conn.execute("""
            ALTER TABLE help_requests
            ADD COLUMN volunteer_id INTEGER
        """)

    conn.commit()
    conn.close()
    


# ==========================================
# HOME PAGE
# ==========================================

@app.route("/")
def home():

    conn = get_db()

    requests_data = conn.execute("""
        SELECT
            help_requests.*,
            users.name
        FROM help_requests
        LEFT JOIN users
        ON help_requests.user_id = users.id
        ORDER BY help_requests.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "index.html",
        requests=requests_data
    )


# ==========================================
# REGISTER
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        role = request.form["role"]

        conn = get_db()

        try:

            conn.execute("""
                INSERT INTO users
                (name, email, password, role)
                VALUES (?, ?, ?, ?)
            """, (
                name,
                email,
                password,
                role
            ))

            conn.commit()

        except sqlite3.IntegrityError:

            conn.close()

            return "Email already registered!"

        conn.close()
        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))

        return redirect(url_for("login"))

    return render_template("register.html")


# ==========================================
# LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        entered_password = request.form["password"]

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (email,)).fetchone()

        if user:
            stored_password = user["password"]

            # New users: password is hashed
            if stored_password.startswith(("scrypt:", "pbkdf2:")):
                password_valid = check_password_hash(
                    stored_password,
                    entered_password
                )

            # Old users: password may still be plain text
            else:
                password_valid = stored_password == entered_password

                # Upgrade old password to secure hash
                if password_valid:
                    new_password = generate_password_hash(
                        entered_password
                    )

                    conn.execute("""
                        UPDATE users
                        SET password = ?
                        WHERE id = ?
                    """, (new_password, user["id"]))

                    conn.commit()

            if password_valid:
                session["user_id"] = user["id"]
                session["name"] = user["name"]
                session["role"] = user["role"]

                conn.close()

                if user["role"] == "Volunteer":
                    return redirect(url_for("volunteer"))

                if user["role"] == "Admin":
                    return redirect(url_for("admin"))

                return redirect(url_for("dashboard"))

        conn.close()

        return render_template(
            "login.html",
            error="Invalid email or password!"
        )

    return render_template("login.html")


# ==========================================
# REQUEST HELP
# ==========================================

@app.route("/request-help", methods=["GET", "POST"])
def request_help():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        category = request.form["category"]
        description = request.form["description"]
        location = request.form["location"]

        conn = get_db()

        conn.execute("""
            INSERT INTO help_requests
            (
                user_id,
                category,
                description,
                location,
                status
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            category,
            description,
            location,
            "Pending"
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("request_help.html")


# ==========================================
# HELP SEEKER DASHBOARD
# ==========================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    requests_data = conn.execute("""
        SELECT
            help_requests.*,
            volunteer.name AS volunteer_name
        FROM help_requests
        LEFT JOIN users AS volunteer
        ON help_requests.volunteer_id = volunteer.id
        WHERE help_requests.user_id = ?
        ORDER BY help_requests.id DESC
    """, (
        session["user_id"],
    )).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        requests=requests_data
    )


# ==========================================
# VOLUNTEER DASHBOARD
# ==========================================

@app.route("/volunteer")
def volunteer():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Volunteer":
        return redirect(url_for("dashboard"))

    conn = get_db()

    # PENDING REQUESTS
    pending_requests = conn.execute("""
        SELECT
            help_requests.*,
            users.name
        FROM help_requests
        LEFT JOIN users
        ON help_requests.user_id = users.id
        WHERE help_requests.status = 'Pending'
        ORDER BY help_requests.id DESC
    """).fetchall()

    # ACCEPTED REQUESTS
    accepted_requests = conn.execute("""
        SELECT
            help_requests.*,
            users.name
        FROM help_requests
        LEFT JOIN users
        ON help_requests.user_id = users.id
        WHERE help_requests.volunteer_id = ?
        ORDER BY help_requests.id DESC
    """, (
        session["user_id"],
    )).fetchall()

    conn.close()

    return render_template(
        "volunteer.html",
        requests=pending_requests,
        accepted_requests=accepted_requests
    )


# ==========================================
# ACCEPT HELP REQUEST
# ==========================================

@app.route(
    "/help/<int:request_id>/accept",
    methods=["POST"]
)
def accept_help(request_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Volunteer":
        return redirect(url_for("dashboard"))

    conn = get_db()

    conn.execute("""
        UPDATE help_requests

        SET
            status = 'Volunteer Assigned',
            volunteer_id = ?

        WHERE id = ?
        AND status = 'Pending'
    """, (
        session["user_id"],
        request_id
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("volunteer"))


# ==========================================
# COMPLETE HELP REQUEST
# ==========================================

@app.route(
    "/help/<int:request_id>/complete",
    methods=["POST"]
)
def complete_help(request_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Volunteer":
        return redirect(url_for("dashboard"))

    conn = get_db()

    conn.execute("""
        UPDATE help_requests

        SET status = 'Completed'

        WHERE id = ?
        AND volunteer_id = ?
    """, (
        request_id,
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("volunteer"))


# ==========================================
# ADMIN DASHBOARD
# ==========================================

@app.route("/admin")
def admin():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Admin":
        return redirect(url_for("dashboard"))

    conn = get_db()

    # --------------------------------------
    # TOTAL USERS
    # --------------------------------------

    total_users = conn.execute("""
        SELECT COUNT(*) AS total
        FROM users
        WHERE role != 'Admin'
    """).fetchone()["total"]


    # --------------------------------------
    # TOTAL VOLUNTEERS
    # --------------------------------------

    total_volunteers = conn.execute("""
        SELECT COUNT(*) AS total
        FROM users
        WHERE role = 'Volunteer'
    """).fetchone()["total"]


    # --------------------------------------
    # TOTAL HELP REQUESTS
    # --------------------------------------

    total_requests = conn.execute("""
        SELECT COUNT(*) AS total
        FROM help_requests
    """).fetchone()["total"]


    # --------------------------------------
    # PENDING REQUESTS
    # --------------------------------------

    pending_requests = conn.execute("""
        SELECT COUNT(*) AS total
        FROM help_requests
        WHERE status = 'Pending'
    """).fetchone()["total"]


    # --------------------------------------
    # ASSIGNED REQUESTS
    # --------------------------------------

    assigned_requests = conn.execute("""
        SELECT COUNT(*) AS total
        FROM help_requests
        WHERE status = 'Volunteer Assigned'
    """).fetchone()["total"]


    # --------------------------------------
    # COMPLETED REQUESTS
    # --------------------------------------

    completed_requests = conn.execute("""
        SELECT COUNT(*) AS total
        FROM help_requests
        WHERE status = 'Completed'
    """).fetchone()["total"]


    # --------------------------------------
    # CATEGORY STATISTICS
    # --------------------------------------

    category_stats = conn.execute("""
        SELECT
            category,
            COUNT(*) AS total
        FROM help_requests
        GROUP BY category
        ORDER BY total DESC
    """).fetchall()


    # --------------------------------------
    # ALL REQUESTS
    # --------------------------------------

    all_requests = conn.execute("""
        SELECT

            help_requests.id,

            help_requests.category,

            help_requests.description,

            help_requests.location,

            help_requests.status,

            seeker.name AS seeker_name,

            volunteer.name AS volunteer_name

        FROM help_requests

        LEFT JOIN users AS seeker
        ON help_requests.user_id = seeker.id

        LEFT JOIN users AS volunteer
        ON help_requests.volunteer_id = volunteer.id

        ORDER BY help_requests.id DESC

    """).fetchall()


    # --------------------------------------
    # DEBUG INFORMATION
    # --------------------------------------

    print("----------------------------------------")
    print("DATABASE:", DATABASE)
    print("TOTAL REQUESTS:", total_requests)
    print("ALL REQUESTS LOADED:", len(all_requests))

    for item in all_requests:

        print(
            item["id"],
            item["category"],
            item["seeker_name"],
            item["volunteer_name"],
            item["status"]
        )

    print("----------------------------------------")


    conn.close()


    # --------------------------------------
    # SEND DATA TO ADMIN.HTML
    # --------------------------------------

    return render_template(

        "admin.html",

        total_users=total_users,

        total_volunteers=total_volunteers,

        total_requests=total_requests,

        pending_requests=pending_requests,

        assigned_requests=assigned_requests,

        completed_requests=completed_requests,

        category_stats=category_stats,

        all_requests=all_requests
    )


# ==========================================
# ADMIN REQUEST DETAILS
# ==========================================

@app.route("/admin/request/<int:request_id>")
def admin_request_details(request_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Admin":
        return redirect(url_for("dashboard"))

    conn = get_db()

    item = conn.execute("""
        SELECT

            help_requests.*,

            seeker.name AS seeker_name,

            volunteer.name AS volunteer_name

        FROM help_requests

        LEFT JOIN users AS seeker
        ON help_requests.user_id = seeker.id

        LEFT JOIN users AS volunteer
        ON help_requests.volunteer_id = volunteer.id

        WHERE help_requests.id = ?

    """, (
        request_id,
    )).fetchone()

    conn.close()

    if item is None:
        return "Help request not found!"

    return render_template(
        "request_details.html",
        item=item
    )


# ==========================================
# LOGOUT
# ==========================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# ==========================================
# START APPLICATION
# ==========================================

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)