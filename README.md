# MetricsAI — FastAPI + HTMX + Tailwind

Production-ready analytics dashboard.
## Stack
- **FastAPI** — backend API
- **Jinja2** — HTML templates
- **HTMX** — dynamic UI without JavaScript
- **Tailwind CSS** — modern styling
- **Plotly** — interactive charts (embedded as HTML)
- **Pandas/NumPy** — data processing
- **SQLite** — data persistence

## Quick Start
```bash
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Open http://localhost:8000

## Deploy
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```
