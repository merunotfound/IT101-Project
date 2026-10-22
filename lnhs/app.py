"""
============================================================
 LIGAO NATIONAL HIGH SCHOOL -- LEARNER INFORMATION SYSTEM
============================================================
A browser-based enrollment system that replaces the paper
masterlist. Built with Flask (Python) + SQLite.

What it tracks for every learner:
  - LRN (the 12-digit DepEd Learner Reference Number)
  - Name, sex, birthdate (age is calculated, never typed in), address
  - School year, grade level, section
  - Enrollment status:  Pending / Enrolled / Transferred Out / Dropped
  - Learner type:       New / Transferee / Returning / Promoted
  - Guardian name and contact number
  - A checklist of submitted requirements (PSA birth certificate, etc.)

What it does with that data:
  - Add / edit / delete / search learners
  - Refuses to put a learner into a section that is already full
  - Shows an enrollment summary and section headcounts per school year
  - Exports the (filtered) list to CSV

Run:
    pip install -r requirements.txt
    python app.py
Then open  http://127.0.0.1:5000

Data lives in learners.db (same folder as this file). If you are
upgrading from the first version of this system, the old records are
migrated automatically the first time you start the app, and a backup
copy is saved as learners.db.bak.
============================================================
"""

import csv
import io
import os
import re
import shutil
import sqlite3
from datetime import date

from flask import Flask, g, jsonify, render_template, request, Response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.environ.get("LNHS_DB", os.path.join(BASE_DIR, "learners.db"))

app = Flask(__name__)

# ------------------------------------------------------------
# School rules -- change these to match how the school works
# ------------------------------------------------------------
MAX_SECTION_SIZE = 45  # most learners one section can hold

STATUSES = ["Pending", "Enrolled", "Transferred Out", "Dropped"]
ACTIVE_STATUSES = ("Pending", "Enrolled")  # these hold a seat in a section
LEARNER_TYPES = ["New", "Transferee", "Returning", "Promoted"]
SEXES = ["Male", "Female"]

# (key, label) -- the documents the registrar checks off at enrollment
REQUIREMENTS = [
    ("psa", "PSA Birth Certificate"),
    ("report_card", "Report Card (Form 138)"),
    ("form137", "Permanent Record (Form 137)"),
    ("good_moral", "Good Moral Certificate"),
    ("photo", "2x2 ID Photo"),
]
REQ_COLUMNS = [f"req_{key}" for key, _ in REQUIREMENTS]

LRN_PATTERN = re.compile(r"^\d{12}$")
CONTACT_PATTERN = re.compile(r"^\d{7,15}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SCHOOL_YEAR_PATTERN = re.compile(r"^(\d{4})-(\d{4})$")


# ------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------
def current_school_year(today=None):
    """Philippine school years start in June: Oct 2026 -> '2026-2027'."""
    today = today or date.today()
    start = today.year if today.month >= 6 else today.year - 1
    return f"{start}-{start + 1}"


def calc_age(birthdate_str, today=None):
    """Age in whole years from an ISO birthdate, or None if unknown."""
    try:
        born = date.fromisoformat(birthdate_str)
    except (TypeError, ValueError):
        return None
    today = today or date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def text(data, key):
    return str(data.get(key) or "").strip()


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def csv_safe(value):
    """Stop spreadsheet apps from running a cell that starts with = + - @"""
    s = str(value)
    return "'" + s if s and s[0] in "=+-@" else s


# ------------------------------------------------------------
# Database
# ------------------------------------------------------------
CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS learners (
    lrn               TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    sex               TEXT NOT NULL DEFAULT '',
    birthdate         TEXT NOT NULL DEFAULT '',
    address           TEXT NOT NULL DEFAULT '',
    grade_level       INTEGER NOT NULL,
    section           TEXT NOT NULL,
    school_year       TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'Pending',
    learner_type      TEXT NOT NULL DEFAULT 'New',
    guardian_name     TEXT NOT NULL,
    guardian_contact  TEXT NOT NULL,
    {", ".join(f"{c} INTEGER NOT NULL DEFAULT 0" for c in REQ_COLUMNS)}
)
"""

FIELDS = [
    "lrn", "name", "sex", "birthdate", "address", "grade_level", "section",
    "school_year", "status", "learner_type", "guardian_name", "guardian_contact",
] + REQ_COLUMNS


def migrate_old_schema(conn):
    """The first version stored 'age' and had no enrollment fields.
    Rebuild the table in the new shape and keep every old record."""
    shutil.copy(DB_FILE, DB_FILE + ".bak")  # safety copy before touching anything

    conn.isolation_level = None  # manual transaction so it's all-or-nothing
    conn.execute("BEGIN")
    try:
        conn.execute("ALTER TABLE learners RENAME TO learners_old")
        conn.execute(CREATE_TABLE)
        conn.execute(
            """
            INSERT INTO learners
                (lrn, name, grade_level, section, school_year, status,
                 learner_type, guardian_name, guardian_contact)
            SELECT lrn, name, grade_level, section, ?, 'Enrolled',
                   'New', guardian_name, guardian_contact
            FROM learners_old
            """,
            (current_school_year(),),
        )
        conn.execute("DROP TABLE learners_old")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def init_db():
    conn = sqlite3.connect(DB_FILE)
    try:
        columns = [r[1] for r in conn.execute("PRAGMA table_info(learners)")]
        if columns and "birthdate" not in columns:
            migrate_old_schema(conn)
        else:
            conn.execute(CREATE_TABLE)
            conn.commit()
    finally:
        conn.close()


init_db()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def row_to_dict(row):
    requirements = {key: bool(row[f"req_{key}"]) for key, _ in REQUIREMENTS}
    return {
        "lrn": row["lrn"],
        "name": row["name"],
        "sex": row["sex"],
        "birthdate": row["birthdate"],
        "age": calc_age(row["birthdate"]),
        "address": row["address"],
        "grade_level": row["grade_level"],
        "section": row["section"],
        "school_year": row["school_year"],
        "status": row["status"],
        "learner_type": row["learner_type"],
        "guardian_name": row["guardian_name"],
        "guardian_contact": row["guardian_contact"],
        "requirements": requirements,
        "requirements_done": sum(requirements.values()),
        "requirements_total": len(requirements),
    }


# ------------------------------------------------------------
# Validation -- returns a list of error strings (empty = valid)
# ------------------------------------------------------------
TEXT_KEYS = [
    "lrn", "name", "birthdate", "address", "section", "school_year",
    "guardian_name", "guardian_contact",
]


def validate_payload(data, lrn_required=True):
    errors = []

    # Text fields must really be text (the form always sends strings; this
    # stops odd API input like a number being saved as a name).
    for key in TEXT_KEYS:
        value = data.get(key)
        if value is not None and not isinstance(value, str):
            errors.append(f"{key.replace('_', ' ').capitalize()} must be text.")
    if errors:
        return errors

    if lrn_required and not LRN_PATTERN.match(text(data, "lrn")):
        errors.append("LRN must be exactly 12 digits.")

    if not text(data, "name"):
        errors.append("Name can't be empty.")
    elif len(text(data, "name")) > 100:
        errors.append("Name is too long (100 characters max).")

    if data.get("sex") not in SEXES:
        errors.append("Select the learner's sex.")

    birthdate = text(data, "birthdate")
    born = None
    if DATE_PATTERN.match(birthdate):
        try:
            born = date.fromisoformat(birthdate)
        except ValueError:
            born = None
    if born is None:
        errors.append("Birthdate must be a valid date.")
    elif born > date.today():
        errors.append("Birthdate can't be in the future.")
    elif not (10 <= calc_age(birthdate) <= 25):
        errors.append("Learner's age (from the birthdate) must be between 10 and 25.")

    if not text(data, "address"):
        errors.append("Address can't be empty.")
    elif len(text(data, "address")) > 200:
        errors.append("Address is too long (200 characters max).")

    grade = data.get("grade_level")
    if not is_int(grade) or not (7 <= grade <= 12):
        errors.append("Grade Level must be a whole number between 7 and 12.")

    if not text(data, "section"):
        errors.append("Section can't be empty.")
    elif len(text(data, "section")) > 30:
        errors.append("Section name is too long (30 characters max).")

    match = SCHOOL_YEAR_PATTERN.match(text(data, "school_year"))
    if not match or int(match.group(2)) != int(match.group(1)) + 1:
        errors.append("School Year must look like 2026-2027.")

    if data.get("status") not in STATUSES:
        errors.append("Select a valid enrollment status.")

    if data.get("learner_type") not in LEARNER_TYPES:
        errors.append("Select a valid learner type.")

    if not text(data, "guardian_name"):
        errors.append("Guardian name can't be empty.")

    if not CONTACT_PATTERN.match(text(data, "guardian_contact")):
        errors.append("Guardian contact number must be 7-15 digits, numbers only.")

    requirements = data.get("requirements")
    if requirements is not None:
        valid_keys = {key for key, _ in REQUIREMENTS}
        if not isinstance(requirements, dict) or any(
            k not in valid_keys or not isinstance(v, bool) for k, v in requirements.items()
        ):
            errors.append("Requirements checklist is invalid.")

    return errors


def clean_values(data):
    """Turn a validated payload into the values stored in the database."""
    requirements = data.get("requirements") or {}
    values = {
        "lrn": text(data, "lrn"),
        "name": text(data, "name"),
        "sex": data["sex"],
        "birthdate": text(data, "birthdate"),
        "address": text(data, "address"),
        "grade_level": data["grade_level"],
        "section": text(data, "section"),
        "school_year": text(data, "school_year"),
        "status": data["status"],
        "learner_type": data["learner_type"],
        "guardian_name": text(data, "guardian_name"),
        "guardian_contact": text(data, "guardian_contact"),
    }
    for key, _ in REQUIREMENTS:
        values[f"req_{key}"] = 1 if requirements.get(key) else 0
    return values


# ------------------------------------------------------------
# Section capacity
# ------------------------------------------------------------
def seats_taken(db, school_year, grade_level, section, exclude_lrn=None):
    sql = (
        "SELECT COUNT(*) FROM learners "
        "WHERE school_year = ? AND grade_level = ? AND LOWER(section) = LOWER(?) "
        "AND status IN ('Pending', 'Enrolled')"
    )
    params = [school_year, grade_level, section]
    if exclude_lrn:
        sql += " AND lrn != ?"
        params.append(exclude_lrn)
    return db.execute(sql, params).fetchone()[0]


def capacity_error(db, values, exclude_lrn=None):
    """Return an error message if this learner would take a seat in a full section.

    Only a NEW seat is checked: someone who already holds a seat in this exact
    section (same school year, grade and section) can always be edited, even if
    the section is over the limit -- e.g. old records, or a lowered limit.
    """
    if values["status"] not in ACTIVE_STATUSES:
        return None  # transferred-out / dropped learners don't hold a seat

    if exclude_lrn:
        current = db.execute(
            "SELECT school_year, grade_level, section, status FROM learners WHERE lrn = ?",
            (exclude_lrn,),
        ).fetchone()
        if (
            current
            and current["status"] in ACTIVE_STATUSES
            and current["school_year"] == values["school_year"]
            and current["grade_level"] == values["grade_level"]
            and current["section"].lower() == values["section"].lower()
        ):
            return None  # same seat as before -- nothing new to check

    taken = seats_taken(
        db, values["school_year"], values["grade_level"], values["section"], exclude_lrn
    )
    if taken >= MAX_SECTION_SIZE:
        return (
            f"Grade {values['grade_level']} - {values['section']} is full for "
            f"{values['school_year']} ({taken}/{MAX_SECTION_SIZE}). Choose another section."
        )
    return None


# ------------------------------------------------------------
# Page route
# ------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# ------------------------------------------------------------
# API routes
# ------------------------------------------------------------
@app.route("/api/meta")
def meta():
    """Lists and rules the page needs to build its dropdowns and checklist."""
    db = get_db()
    year = current_school_year()
    start = int(year[:4])
    years = {r[0] for r in db.execute("SELECT DISTINCT school_year FROM learners")}
    years |= {year, f"{start + 1}-{start + 2}"}
    return jsonify(
        {
            "current_school_year": year,
            "school_years": sorted(years, reverse=True),
            "statuses": STATUSES,
            "learner_types": LEARNER_TYPES,
            "sexes": SEXES,
            "requirements": [{"key": k, "label": label} for k, label in REQUIREMENTS],
            "max_section_size": MAX_SECTION_SIZE,
        }
    )


def filtered_rows(db):
    """Learners matching the ?school_year= ?status= ?q= query parameters."""
    school_year = (request.args.get("school_year") or "").strip()
    status = (request.args.get("status") or "").strip()
    term = (request.args.get("q") or "").strip()

    clauses, params = [], []
    if school_year:
        clauses.append("school_year = ?")
        params.append(school_year)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if term:
        like = f"%{term}%"
        if term.isdigit():
            clauses.append("(lrn LIKE ? OR name LIKE ? OR guardian_contact LIKE ?)")
            params += [f"{term}%", like, like]
        else:
            clauses.append(
                "(name LIKE ? OR section LIKE ? OR guardian_name LIKE ? OR address LIKE ?)"
            )
            params += [like, like, like, like]

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return db.execute(
        f"SELECT * FROM learners {where} "
        "ORDER BY grade_level, section COLLATE NOCASE, name COLLATE NOCASE",
        params,
    ).fetchall()


@app.route("/api/learners", methods=["GET"])
def list_learners():
    return jsonify([row_to_dict(r) for r in filtered_rows(get_db())])


@app.route("/api/learners", methods=["POST"])
def create_learner():
    data = request.get_json(silent=True) or {}
    errors = validate_payload(data, lrn_required=True)
    if errors:
        return jsonify({"errors": errors}), 400

    values = clean_values(data)
    db = get_db()

    problem = capacity_error(db, values)
    if problem:
        return jsonify({"errors": [problem]}), 400

    try:
        db.execute(
            f"INSERT INTO learners ({', '.join(FIELDS)}) "
            f"VALUES ({', '.join(':' + f for f in FIELDS)})",
            values,
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"errors": [f"LRN {values['lrn']} is already in use."]}), 400

    row = db.execute("SELECT * FROM learners WHERE lrn = ?", (values["lrn"],)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/learners/<lrn>", methods=["PUT"])
def update_learner(lrn):
    data = request.get_json(silent=True) or {}
    errors = validate_payload(data, lrn_required=False)
    if errors:
        return jsonify({"errors": errors}), 400

    data["lrn"] = lrn  # the LRN in the URL is the record being edited
    values = clean_values(data)
    db = get_db()

    exists = db.execute("SELECT 1 FROM learners WHERE lrn = ?", (lrn,)).fetchone()
    if not exists:
        return jsonify({"errors": [f"No learner found with LRN {lrn}."]}), 404

    problem = capacity_error(db, values, exclude_lrn=lrn)
    if problem:
        return jsonify({"errors": [problem]}), 400

    editable = [f for f in FIELDS if f != "lrn"]
    db.execute(
        f"UPDATE learners SET {', '.join(f'{f} = :{f}' for f in editable)} WHERE lrn = :lrn",
        values,
    )
    db.commit()

    row = db.execute("SELECT * FROM learners WHERE lrn = ?", (lrn,)).fetchone()
    return jsonify(row_to_dict(row))


@app.route("/api/learners/<lrn>", methods=["DELETE"])
def delete_learner(lrn):
    db = get_db()
    cur = db.execute("DELETE FROM learners WHERE lrn = ?", (lrn,))
    db.commit()

    if cur.rowcount == 0:
        return jsonify({"errors": [f"No learner found with LRN {lrn}."]}), 404

    return jsonify({"status": "deleted", "lrn": lrn})


@app.route("/api/summary")
def summary():
    """Headline numbers and section headcounts for one school year."""
    school_year = (request.args.get("school_year") or "").strip() or current_school_year()
    rows = get_db().execute(
        "SELECT * FROM learners WHERE school_year = ?", (school_year,)
    ).fetchall()

    by_status = {s: 0 for s in STATUSES}
    enrolled_by_sex = {"Male": 0, "Female": 0}
    incomplete = 0
    sections = {}

    for row in rows:
        learner = row_to_dict(row)
        by_status[learner["status"]] += 1

        if learner["status"] == "Enrolled" and learner["sex"] in enrolled_by_sex:
            enrolled_by_sex[learner["sex"]] += 1

        if learner["status"] in ACTIVE_STATUSES:
            if learner["requirements_done"] < learner["requirements_total"]:
                incomplete += 1

            key = (learner["grade_level"], learner["section"].lower())
            entry = sections.setdefault(
                key,
                {
                    "grade_level": learner["grade_level"],
                    "section": learner["section"],
                    "count": 0,
                    "male": 0,
                    "female": 0,
                },
            )
            entry["count"] += 1
            if learner["sex"] == "Male":
                entry["male"] += 1
            elif learner["sex"] == "Female":
                entry["female"] += 1

    section_list = sorted(
        sections.values(), key=lambda s: (s["grade_level"], s["section"].lower())
    )
    for s in section_list:
        s["capacity"] = MAX_SECTION_SIZE
        s["full"] = s["count"] >= MAX_SECTION_SIZE

    return jsonify(
        {
            "school_year": school_year,
            "total": len(rows),
            "by_status": by_status,
            "enrolled_male": enrolled_by_sex["Male"],
            "enrolled_female": enrolled_by_sex["Female"],
            "incomplete_requirements": incomplete,
            "sections": section_list,
        }
    )


@app.route("/api/export")
def export_csv():
    rows = filtered_rows(get_db())

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "LRN", "Name", "Sex", "Birthdate", "Age", "Address", "School Year",
            "Grade Level", "Section", "Status", "Learner Type", "Guardian Name",
            "Guardian Contact",
        ]
        + [label for _, label in REQUIREMENTS]
        + ["Requirements Complete"]
    )
    for row in rows:
        d = row_to_dict(row)
        writer.writerow(
            [
                d["lrn"], csv_safe(d["name"]), d["sex"], d["birthdate"],
                "" if d["age"] is None else d["age"], csv_safe(d["address"]),
                d["school_year"], d["grade_level"], csv_safe(d["section"]),
                d["status"], d["learner_type"], csv_safe(d["guardian_name"]),
                d["guardian_contact"],
            ]
            + ["Yes" if d["requirements"][key] else "No" for key, _ in REQUIREMENTS]
            + ["Yes" if d["requirements_done"] == d["requirements_total"] else "No"]
        )

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=learners_export.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True)
