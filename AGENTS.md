# Developer Guidelines for meal_planner

This document provides guidance for OpenAI Codex and other automated contributors working on this repository.

## Project Structure

- `app.py` – main Flask application entry point.
- `static/` – JavaScript, CSS and image assets. Avoid modifying images directly.
- `templates/` – Jinja2 HTML templates used by the Flask app.
- `migrations/` – Alembic database migration scripts.
- `Scripts/` – helper scripts for database maintenance and other tasks.
- `database.db` – local SQLite database (do not commit changes to this file).

## Coding Conventions

- Use **Python 3.10** or later.
- Follow **PEP8** style and format code with `black`.
- Write clear variable and function names. Add docstrings for modules, classes and complex functions.
- Keep functions small and focused. Prefer helper functions over large blocks of inline logic.
- When working with templates, use semantic HTML and keep logic minimal. Place JavaScript in `static/`.
- For database access use SQLAlchemy models defined in `app.py` or migrations.

## Programmatic Checks

Before opening a pull request, run the following commands and ensure they pass:

```bash
black --check .
flake8
pytest
```

If additional setup is required for these commands, document it in the PR description.

## Pull Request Guidelines

1. Provide a clear summary of changes.
2. Reference any related issues.
3. Ensure tests pass and lint checks succeed.
4. Include screenshots for user‑interface changes.
5. Keep the pull request focused on a single purpose.

New automated tests should be added under a `tests/` directory if it does not already exist.
