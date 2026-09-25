"""
============================================================
 LIGAO NATIONAL HIGH SCHOOL -- LEARNER INFORMATION SYSTEM
============================================================
Replaces a paper-based learner masterlist with a searchable,
browser-based system. Built with Flask (Python) + SQLite.

Fields match what a real DepEd high school actually needs to
track day to day:
  - LRN (Learner Reference Number) -- the official 12-digit ID
    DepEd assigns to every learner
  - Name, Grade Level (7-12), Section
  - Age
  - Guardian name and contact number -- the thing that's most
    often illegible, outdated, or lost on paper forms

Run:
    pip install -r requirements.txt
    python app.py
Then open:
    http://127.0.0.1:5000

Data is stored in learners.db in this folder.
============================================================
"""

import csv
import io
import re
import sqlite3

from flask import Flask, g, jsonify, render_template, request, Response

DB_FILE = "learners.db"

app = Flask(__name__)

LRN_PATTERN = re.compile(r"^\d{12}$")
CONTACT_PATTERN = re.compile(r"^\d{7,15}$")


# ------------------------------------------------------------
# Database helpers
# ------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
        g.db.execute(
            """
            CREATE TABLE IF NOT EXISTS learners (
                lrn               TEXT PRIMARY KEY,
                name              TEXT NOT NULL,
                grade_level       INTEGER NOT NULL,
                section           TEXT NOT NULL,
                age               INTEGER NOT NULL,
                guardian_name     TEXT NOT NULL,
                guardian_contact  TEXT NOT NULL
            )
            """
        )
        g.db.commit()
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def row_to_dict(row):
    return {
        "lrn": row["lrn"],
        "name": row["name"],
        "grade_level": row["grade_level"],
        "section": row["section"],
        "age": row["age"],
        "guardian_name": row["guardian_name"],
        "guardian_contact": row["guardian_contact"],
    }


# ------------------------------------------------------------
# Validation -- returns a list of error strings (empty = valid)
# ------------------------------------------------------------
def validate_payload(data, lrn_required=True):
    errors = []

    if lrn_required:
        lrn = str(data.get("lrn") or "").strip()
        if not LRN_PATTERN.match(lrn):
            errors.append("LRN must be exactly 12 digits.")

    name = (data.get("name") or "").strip()
    if not name:
        errors.append("Name can't be empty.")

    grade_level = data.get("grade_level")
    if not isinstance(grade_level, int) or not (7 <= grade_level <= 12):
        errors.append("Grade Level must be a whole number between 7 and 12.")

    section = (data.get("section") or "").strip()
    if not section:
        errors.append("Section can't be empty.")

    age = data.get("age")
    if not isinstance(age, int) or not (10 <= age <= 25):
        errors.append("Age must be a whole number between 10 and 25.")

    guardian_name = (data.get("guardian_name") or "").strip()
    if not guardian_name:
        errors.append("Guardian name can't be empty.")

    guardian_contact = str(data.get("guardian_contact") or "").strip()
    if not CONTACT_PATTERN.match(guardian_contact):
        errors.append("Guardian contact number must be 7-15 digits, numbers only.")

    return errors


# ------------------------------------------------------------
# Page route
# ------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# ------------------------------------------------------------
# API routes
# ------------------------------------------------------------
@app.route("/api/learners", methods=["GET"])
def list_learners():
    term = (request.args.get("q") or "").strip()
    db = get_db()

    if term:
        like = f"%{term}%"
        if term.isdigit():
            rows = db.execute(
                "SELECT * FROM learners WHERE lrn LIKE ? OR name LIKE ? "
                "ORDER BY grade_level, section, name",
                (f"{term}%", like),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM learners WHERE name LIKE ? OR section LIKE ? "
                "OR guardian_name LIKE ? ORDER BY grade_level, section, name",
                (like, like, like),
            ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM learners ORDER BY grade_level, section, name"
        ).fetchall()

    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/learners", methods=["POST"])
def create_learner():
    data = request.get_json(silent=True) or {}
    errors = validate_payload(data, lrn_required=True)
    if errors:
        return jsonify({"errors": errors}), 400

    lrn = str(data["lrn"]).strip()
    db = get_db()
    try:
        db.execute(
            "INSERT INTO learners (lrn, name, grade_level, section, age, "
            "guardian_name, guardian_contact) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                lrn,
                data["name"].strip(),
                data["grade_level"],
                data["section"].strip(),
                data["age"],
                data["guardian_name"].strip(),
                str(data["guardian_contact"]).strip(),
            ),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"errors": [f"LRN {lrn} is already in use."]}), 400

    return jsonify(row_to_dict(
        db.execute("SELECT * FROM learners WHERE lrn = ?", (lrn,)).fetchone()
    )), 201


@app.route("/api/learners/<lrn>", methods=["PUT"])
def update_learner(lrn):
    data = request.get_json(silent=True) or {}
    errors = validate_payload(data, lrn_required=False)
    if errors:
        return jsonify({"errors": errors}), 400

    db = get_db()
    cur = db.execute(
        "UPDATE learners SET name=?, grade_level=?, section=?, age=?, "
        "guardian_name=?, guardian_contact=? WHERE lrn=?",
        (
            data["name"].strip(),
            data["grade_level"],
            data["section"].strip(),
            data["age"],
            data["guardian_name"].strip(),
            str(data["guardian_contact"]).strip(),
            lrn,
        ),
    )
    db.commit()

    if cur.rowcount == 0:
        return jsonify({"errors": [f"No learner found with LRN {lrn}."]}), 404

    return jsonify(row_to_dict(
        db.execute("SELECT * FROM learners WHERE lrn = ?", (lrn,)).fetchone()
    ))


@app.route("/api/learners/<lrn>", methods=["DELETE"])
def delete_learner(lrn):
    db = get_db()
    cur = db.execute("DELETE FROM learners WHERE lrn = ?", (lrn,))
    db.commit()

    if cur.rowcount == 0:
        return jsonify({"errors": [f"No learner found with LRN {lrn}."]}), 404

    return jsonify({"status": "deleted", "lrn": lrn})


@app.route("/api/export")
def export_csv():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM learners ORDER BY grade_level, section, name"
    ).fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["LRN", "Name", "Grade Level", "Section", "Age", "Guardian Name", "Guardian Contact"]
    )
    for r in rows:
        writer.writerow(
            [r["lrn"], r["name"], r["grade_level"], r["section"], r["age"],
             r["guardian_name"], r["guardian_contact"]]
        )

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=learners_export.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True)
