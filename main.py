from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import json
import sqlite3
import hashlib
from datetime import datetime, timedelta
from io import BytesIO, StringIO
import os

app = FastAPI(title="MetricsAI")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ==================== DB ====================
def get_db():
    conn = sqlite3.connect("metricsai.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS shared_dashboards (id TEXT PRIMARY KEY, created_at TEXT, data_json TEXT, white_label TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS uploads (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, source_type TEXT, upload_date TEXT, rows INTEGER, cols INTEGER)")
    conn.commit()
    conn.close()

init_db()

# ==================== DATA UTILS ====================
def generate_sample_data():
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", "2025-06-30", freq="D")
    n = len(dates)
    users = [f"user_{i:04d}" for i in range(500)]
    channels = ["organic", "instagram", "google", "facebook", "email", "tiktok", "referral"]
    events = ["impression", "click", "visit", "add_to_cart", "purchase"]
    df = pd.DataFrame({
        "date": np.random.choice(dates, n),
        "user_id": np.random.choice(users, n),
        "revenue": np.where(np.random.random(n) > 0.7, np.random.exponential(200, n).round(2), 0),
        "channel": np.random.choice(channels, n, p=[0.25, 0.15, 0.20, 0.15, 0.10, 0.10, 0.05]),
        "event_type": np.random.choice(events, n, p=[0.35, 0.20, 0.20, 0.10, 0.15]),
        "marketing_cost": np.random.choice([0, 0, 0, 30, 50, 80, 120, 200], n),
    })
    return df.sort_values("date").reset_index(drop=True)

def calculate_metrics(df):
    metrics = {}
    metrics["total_users"] = int(df["user_id"].nunique()) if "user_id" in df.columns else len(df)
    metrics["total_revenue"] = float(df["revenue"].sum()) if "revenue" in df.columns else 0.0
    metrics["total_orders"] = int(len(df[df["revenue"] > 0])) if "revenue" in df.columns else len(df)
    metrics["arpu"] = metrics["total_revenue"] / metrics["total_users"] if metrics["total_users"] > 0 else 0.0
    metrics["aov"] = metrics["total_revenue"] / metrics["total_orders"] if metrics["total_orders"] > 0 else 0.0
    if "channel" in df.columns and "marketing_cost" in df.columns:
        channel_stats = df.groupby("channel").agg({"user_id": "nunique", "marketing_cost": "sum"}).reset_index()
        channel_stats["cac"] = channel_stats["marketing_cost"] / channel_stats["user_id"]
        metrics["cac_by_channel"] = channel_stats.to_dict("records")
        metrics["avg_cac"] = float(channel_stats["cac"].mean())
    else:
        metrics["avg_cac"] = 0.0
        metrics["cac_by_channel"] = []
    if "date" in df.columns and "user_id" in df.columns and "revenue" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        user_revenue = df.groupby("user_id")["revenue"].sum()
        metrics["ltv"] = float(user_revenue.mean() * 2.0)
    else:
        metrics["ltv"] = metrics["arpu"] * 3.0
    metrics["ltv_cac_ratio"] = metrics["ltv"] / metrics["avg_cac"] if metrics["avg_cac"] > 0 else 0.0
    if "date" in df.columns:
        df["month"] = df["date"].dt.to_period("M").astype(str)
        monthly = df.groupby("month").agg({"revenue": "sum", "user_id": "nunique"}).reset_index()
        monthly["arpu"] = monthly["revenue"] / monthly["user_id"]
        metrics["monthly_trend"] = monthly.to_dict("records")
    else:
        metrics["monthly_trend"] = []
    if "event_type" in df.columns:
        funnel_order = ["impression", "click", "visit", "add_to_cart", "purchase", "order"]
        funnel_counts = df["event_type"].value_counts().to_dict()
        funnel_data = []
        for step in funnel_order:
            if step in funnel_counts:
                funnel_data.append({"step": step.upper(), "users": int(funnel_counts[step])})
        if not funnel_data:
            for k, v in funnel_counts.items():
                funnel_data.append({"step": k.upper(), "users": int(v)})
        metrics["funnel"] = funnel_data
    else:
        metrics["funnel"] = []
    return metrics

def build_charts(df, metrics):
    charts = {}
    if metrics.get("monthly_trend"):
        monthly_df = pd.DataFrame(metrics["monthly_trend"])
        fig = px.line(monthly_df, x="month", y="revenue", template="plotly_dark")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94A3B8", margin=dict(l=20, r=20, t=40, b=20), showlegend=False)
        fig.update_traces(line_color="#F8FAFC")
        charts["revenue"] = fig.to_html(full_html=False, include_plotlyjs="cdn")

        fig2 = px.bar(monthly_df, x="month", y="arpu", template="plotly_dark")
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94A3B8", margin=dict(l=20, r=20, t=40, b=20), showlegend=False)
        fig2.update_traces(marker_color="#94A3B8")
        charts["arpu"] = fig2.to_html(full_html=False, include_plotlyjs=False)

    if metrics.get("funnel"):
        funnel_df = pd.DataFrame(metrics["funnel"])
        fig = px.funnel(funnel_df, x="users", y="step", template="plotly_dark")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94A3B8", margin=dict(l=20, r=20, t=20, b=20), showlegend=False)
        charts["funnel"] = fig.to_html(full_html=False, include_plotlyjs=False)

    if "channel" in df.columns:
        channel_df = df.groupby("channel")["revenue"].sum().reset_index().sort_values("revenue", ascending=True)
        fig = px.bar(channel_df, x="revenue", y="channel", orientation="h", template="plotly_dark")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94A3B8", margin=dict(l=20, r=20, t=20, b=20), showlegend=False)
        fig.update_traces(marker_color="#F8FAFC")
        charts["channel"] = fig.to_html(full_html=False, include_plotlyjs=False)

    return charts

# ==================== IN-MEMORY STORE ====================
# For demo, we store data in memory. In production, use Redis/DB.
_session_data = {}

def get_session_data(session_id: str):
    return _session_data.get(session_id)

def set_session_data(session_id: str, df: pd.DataFrame, white_label: dict):
    _session_data[session_id] = {"df": df, "white_label": white_label, "metrics": calculate_metrics(df), "charts": build_charts(df, calculate_metrics(df))}

# ==================== ROUTES ====================
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    session_id = request.cookies.get("session_id", hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:16])
    data = get_session_data(session_id)
    has_data = data is not None
    metrics = data["metrics"] if data else {}
    charts = data["charts"] if data else {}
    white_label = data["white_label"] if data else {"company_name": "MetricsAI", "logo_text": "MetricsAI"}
    share_url = ""

    response = templates.TemplateResponse("dashboard.html", {
        "request": request,
        "has_data": has_data,
        "metrics": metrics,
        "charts": charts,
        "white_label": white_label,
        "share_url": share_url,
        "page": "dashboard",
    })
    response.set_cookie("session_id", session_id)
    return response

@app.post("/load-sample")
def load_sample(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id:
        return HTMLResponse("<div class='alert alert-error'>No session</div>")
    df = generate_sample_data()
    set_session_data(session_id, df, {"company_name": "MetricsAI", "logo_text": "MetricsAI"})
    return HTMLResponse("", status_code=200, headers={"HX-Redirect": "/"})

@app.post("/share")
def share_dashboard(request: Request):
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    if not data:
        return JSONResponse({"error": "No data"}, status_code=400)

    dashboard_id = hashlib.sha256(str(datetime.now().timestamp()).encode()).hexdigest()[:12]
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO shared_dashboards (id, created_at, data_json, white_label) VALUES (?, ?, ?, ?)",
              (dashboard_id, datetime.now().isoformat(), data["df"].to_json(), json.dumps(data["white_label"])))
    conn.commit()
    conn.close()

    return JSONResponse({"url": f"/dashboard/{dashboard_id}"})

@app.get("/dashboard/{dashboard_id}", response_class=HTMLResponse)
def public_dashboard(request: Request, dashboard_id: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT data_json, white_label FROM shared_dashboards WHERE id = ?", (dashboard_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return templates.TemplateResponse("error.html", {"request": request, "message": "Dashboard not found"})

    df = pd.read_json(StringIO(row["data_json"]))
    white_label = json.loads(row["white_label"])
    metrics = calculate_metrics(df)
    charts = build_charts(df, metrics)

    return templates.TemplateResponse("public.html", {
        "request": request,
        "metrics": metrics,
        "charts": charts,
        "white_label": white_label,
    })

@app.get("/funnel", response_class=HTMLResponse)
def funnel_page(request: Request):
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    has_data = data is not None
    charts = data["charts"] if data else {}
    white_label = data["white_label"] if data else {"company_name": "MetricsAI", "logo_text": "MetricsAI"}

    return templates.TemplateResponse("funnel.html", {
        "request": request,
        "has_data": has_data,
        "charts": charts,
        "white_label": white_label,
        "page": "funnel",
    })

@app.get("/ai", response_class=HTMLResponse)
def ai_page(request: Request):
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    has_data = data is not None
    white_label = data["white_label"] if data else {"company_name": "MetricsAI", "logo_text": "MetricsAI"}

    return templates.TemplateResponse("ai.html", {
        "request": request,
        "has_data": has_data,
        "white_label": white_label,
        "page": "ai",
        "insights": "",
    })

@app.post("/ai-generate")
def ai_generate(request: Request):
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    if not data:
        return HTMLResponse("<div class='alert alert-error'>Сначала загрузите данные</div>")

    m = data["metrics"]
    insights = f"""<div class='ai-insight'>
<div class='ai-header'>🧠 AI Product Analyst</div>
<div style='color: #E2E8F0; line-height: 1.7;'>
1. <b>LTV/CAC ratio ({m.get('ltv_cac_ratio', 0):.1f}x)</b> — {'ниже нормы' if m.get('ltv_cac_ratio', 0) < 3 else 'в норме'}. При healthy ratio > 3x можно масштабировать маркетинг.<br><br>
2. <b>ARPU {m.get('arpu', 0):,.0f} ₽</b> — анализируйте ARPU по каналам. Возможно, некоторые каналы приносят пользователей с низкой монетизацией.<br><br>
3. <b>Выручка {m.get('total_revenue', 0):,.0f} ₽</b> — отслеживайте динамику ежемесячно. Рекомендуем настроить alerts на падение > 15%.<br><br>
4. <b>Сегментация</b> — проведите RFM-анализ для персонализации маркетинговых кампаний.
</div>
</div>"""

    return HTMLResponse(insights)

@app.get("/ab", response_class=HTMLResponse)
def ab_page(request: Request):
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    white_label = data["white_label"] if data else {"company_name": "MetricsAI", "logo_text": "MetricsAI"}

    return templates.TemplateResponse("ab.html", {
        "request": request,
        "white_label": white_label,
        "page": "ab",
    })

@app.post("/ab-calculate")
def ab_calculate(request: Request, conv_a: int = Form(120), n_a: int = Form(1000), conv_b: int = Form(150), n_b: int = Form(1000), confidence: float = Form(0.95)):
    p_a = conv_a / n_a if n_a > 0 else 0
    p_b = conv_b / n_b if n_b > 0 else 0
    se = np.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
    z = (p_b - p_a) / se if se > 0 else 0
    z_critical = 1.96 if confidence == 0.95 else 2.58
    is_significant = abs(z) > z_critical
    uplift = ((p_b - p_a) / p_a * 100) if p_a > 0 else 0

    html = f"""
<div class="grid grid-cols-4 gap-4 mt-6">
    <div class="metric-container"><div class="metric-label">Конверсия A</div><div class="metric-value">{p_a:.2%}</div></div>
    <div class="metric-container"><div class="metric-label">Конверсия B</div><div class="metric-value">{p_b:.2%}</div></div>
    <div class="metric-container"><div class="metric-label">Uplift</div><div class="metric-value" style="color: {'#34D399' if uplift > 0 else '#F87171'}">{uplift:+.1f}%</div></div>
    <div class="metric-container"><div class="metric-label">Значимость</div><div class="metric-value" style="color: {'#34D399' if is_significant else '#F87171'}">{'✅ Да' if is_significant else '❌ Нет'}</div></div>
</div>
<div class="glass-card mt-4"><div style="color: #94A3B8; font-size: 0.9rem;">Z-score: <b>{z:.3f}</b> | Критическое: ±{z_critical}</div></div>
"""
    return HTMLResponse(html)
