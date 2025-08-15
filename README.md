# Orchestra Media Analysis Framework

## Setup

- macOS zsh example:
  - Create venv: `python3 -m venv .venv`
  - Activate: `source .venv/bin/activate`
  - Upgrade pip: `python -m pip install --upgrade pip`
  - Install deps: `pip install -r requirements.txt`

## Development
- Deactivate venv: `deactivate`
- Freeze deps after changes: `pip freeze > requirements.txt`

## Run the web app (local)
- Start: `FLASK_SECRET=dev source .venv/bin/activate && python app.py`
- Open: `http://localhost:8000` → upload CSV → download enriched CSV

## Deploy on Railway
- Use `Procfile` and `requirements.txt`; set `PORT` env (Railway provides automatically) and `FLASK_SECRET`.
- Start command: `gunicorn app:app --bind 0.0.0.0:${PORT}` (from Procfile)

## Project
- Workspace: `/Users/Valentine/ben_state_and_modifier_analysis/ben_state_and_modifier_analysis`
- Schema reference: `Topic, narrative and entity signal schema (8-14 v4).txt`

## One-pager (brand)
- Files: `one_pager/one_pager.html` and `one_pager/styles.css`
- Logo placeholder: `assets/repute-logo.jpg` (create this file or update the img src)
- Export to PDF: open `one_pager/one_pager.html` in a browser → Print → Save as PDF

