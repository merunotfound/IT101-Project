# Ligao National High School — Learner Information System

A browser-based enrollment system that replaces the paper learner
masterlist. Built with Flask (Python) for the backend and database
(SQLite) and plain HTML/CSS/JS for the page — no build tools.

## The problem it addresses

On paper, finding one learner means flipping through pages, fixing a
detail means erasing and rewriting, guardian numbers get smudged or
lost, and nobody can tell at a glance which learners are still missing
documents or which sections are already full. This system keeps the same
information but makes it searchable, editable in place, and summarized
automatically.

## What it tracks

| Group | Fields |
|---|---|
| Learner | LRN (12 digits, unique), full name, sex, **birthdate** (age is calculated from it), home address |
| Enrollment | school year, grade level (7–12), section, **status** (Pending / Enrolled / Transferred Out / Dropped), **learner type** (New / Transferee / Returning / Promoted) |
| Guardian | name, contact number |
| Requirements | checklist: PSA Birth Certificate, Report Card (Form 138), Permanent Record (Form 137), Good Moral Certificate, 2×2 ID Photo |

## What it does

- **Add / edit / delete** learners, with validation (e.g. LRN must be 12
  digits, birthdate must be a real date giving an age of 10–25, contact
  number digits only). Bad input shows a clear message instead of failing.
- **Enrollment summary** for the selected school year: how many are
  Enrolled (with male/female split), Pending, Transferred/Dropped, and how
  many still have **incomplete requirements**.
- **Section headcounts** — every section shows seats used out of its
  maximum, with a bar that turns amber when nearly full and red when full.
- **Full-section rule** — the system refuses to put a new learner into a
  section that is already full (default 45). Learners who are Transferred
  Out or Dropped don't hold a seat, so changing a status frees one.
  Someone already seated in a section can always still be edited.
- **School year switch** — view any school year; each year's sections and
  counts are separate.
- **Search** by LRN, name, section, guardian or address; **filter** by
  status; **sort** by clicking a column heading.
- **Requirements badge** — "Complete", or "3/5" (hover to see exactly
  which documents are missing).
- **Export to CSV** — exports exactly what is on screen (same school year,
  status filter and search), including each requirement as Yes/No.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** in a browser. Leave the terminal running
(Ctrl+C stops the server). Data is stored in `learners.db` next to
`app.py`.

## Upgrading from the earlier version

Replace these files in your project folder with the new ones:
`app.py`, `templates/index.html`, `static/script.js`, `static/style.css`
(and this README). **Keep** your `learners.db` and your `static/images/`
folder.

The first time you start the new version, it converts the old records
automatically and saves a safety copy as `learners.db.bak`. Converted
learners are given the current school year, status **Enrolled**, type
**New**, and requirements all unchecked; their **sex, birthdate and
address are blank** because the old version never stored them (age shows
as "—"). Open each one with **Edit** and fill those in — the form won't
save until they're complete.

## Settings you can change (top of `app.py`)

- `MAX_SECTION_SIZE = 45` — most learners one section can hold.
- `REQUIREMENTS` — the list of documents on the checklist. Add or remove a
  line to change it; the form, table badge and export follow automatically.
- `STATUSES`, `LEARNER_TYPES` — the dropdown options.

## Project structure

```
lnhs/
├── app.py                  <- backend: database, rules, API (run this)
├── requirements.txt
├── learners.db             <- created automatically on first run
├── templates/
│   └── index.html          <- page structure
└── static/
    ├── style.css           <- all styling (colors are variables at the top)
    ├── script.js           <- everything interactive
    └── images/
        ├── cover.jpg       <- banner photo
        └── logo.jpg        <- school seal
```

## Ideas for later (say these in your documentation as future work)

- Teacher login, and a log of who changed what
- A printable class list per section
- Strand tracking for Grades 11–12 (STEM, ABM, HUMSS, TVL)
- A year-end "promote to next grade level" action
- Putting it on a school computer so other staff can reach it on the network
