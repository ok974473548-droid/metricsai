# MetricsAI on Reflex

Full-stack Python analytics dashboard built with Reflex (Pynecone).

## Why Reflex?

- **Python everywhere**: Backend + frontend in one language
- **React compiler**: Python code compiles to React components
- **Full control**: Custom CSS, routing, state management
- **Real-time**: WebSocket state sync out of the box
- **Production ready**: Deploy to Reflex Cloud or self-host

## Stack

- Reflex (Python → React)
- Pandas / NumPy (data processing)
- Plotly (interactive charts)
- OpenAI (AI insights)
- SQLite (data persistence)

## Quick Start

```bash
pip install -r requirements.txt
reflex init
reflex run
```

Open http://localhost:3000

## Deploy

```bash
reflex deploy
```

Or self-host with Docker.

## Project Structure

```
metricsai/
├── rxconfig.py          # Reflex config
├── requirements.txt
└── metricsai/
    ├── __init__.py
    └── metricsai.py     # Main app (state + pages + styles)
```
