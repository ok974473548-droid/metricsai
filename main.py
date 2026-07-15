from fastapi import FastAPI, Request, Form, UploadFile, File, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.io import to_image
import json
import sqlite3
import hashlib
from datetime import datetime, timedelta
from io import BytesIO, StringIO
import os
import asyncio
from typing import Optional, List, Dict
import base64

# ==================== CONFIG ====================
SECRET_KEY = "metricsai-super-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

app = FastAPI(title="MetricsAI v3.1")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# ==================== DB ====================
def get_db():
    conn = sqlite3.connect("metricsai.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # Existing tables
    c.execute("CREATE TABLE IF NOT EXISTS shared_dashboards (id TEXT PRIMARY KEY, created_at TEXT, data_json TEXT, white_label TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS uploads (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, source_type TEXT, upload_date TEXT, rows INTEGER, cols INTEGER, user_id INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS custom_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, config_json TEXT, created_at TEXT, user_id INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS api_keys (id INTEGER PRIMARY KEY AUTOINCREMENT, service TEXT, key_value TEXT, created_at TEXT)")

    # NEW: Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            full_name TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # NEW: User dashboards (multi-user)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_dashboards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            data_json TEXT,
            white_label TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # NEW: Export history
    c.execute("""
        CREATE TABLE IF NOT EXISTS exports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            export_type TEXT,
            filename TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ==================== AUTH UTILS ====================
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        if user:
            return dict(user)
        return None
    except JWTError:
        return None

# ==================== WEBSOCKET MANAGER ====================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# ==================== DATA UTILS (unchanged core) ====================
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
        "subscription": np.random.choice(["monthly", "annual", "none"], n, p=[0.15, 0.05, 0.80]),
    })
    df["date"] = pd.to_datetime(df["date"])
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
        user_revenue = df.groupby("user_id")["revenue"].sum()
        metrics["ltv"] = float(user_revenue.mean() * 2.0)
    else:
        metrics["ltv"] = metrics["arpu"] * 3.0
    metrics["ltv_cac_ratio"] = metrics["ltv"] / metrics["avg_cac"] if metrics["avg_cac"] > 0 else 0.0
    if "date" in df.columns:
        df["month_str"] = df["date"].dt.strftime("%Y-%m")
        monthly = df.groupby("month_str").agg({"revenue": "sum", "user_id": "nunique"}).reset_index()
        monthly["arpu"] = monthly["revenue"] / monthly["user_id"]
        monthly = monthly.rename(columns={"month_str": "month"})
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
        fig.update_traces(line_color="#F8FAFC", line_width=3)
        charts["revenue"] = fig.to_html(full_html=False, include_plotlyjs="cdn")

        fig2 = px.bar(monthly_df, x="month", y="arpu", template="plotly_dark")
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94A3B8", margin=dict(l=20, r=20, t=40, b=20), showlegend=False)
        fig2.update_traces(marker_color="#94A3B8", marker_opacity=0.7)
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
        fig.update_traces(marker_color="#F8FAFC", marker_opacity=0.8)
        charts["channel"] = fig.to_html(full_html=False, include_plotlyjs=False)

    return charts

def calculate_revenue_metrics(df):
    rev = {}
    if df.empty or "date" not in df.columns or "revenue" not in df.columns:
        rev["mrr"] = 0
        rev["arr"] = 0
        rev["mrr_growth"] = 0
        rev["waterfall"] = []
        rev["ltv_curve"] = []
        rev["subscription"] = []
        return rev
    df["month_str"] = df["date"].dt.strftime("%Y-%m").astype(str)
    monthly_rev = df.groupby("month_str")["revenue"].sum().reset_index()
    monthly_rev["month"] = monthly_rev["month_str"].astype(str)
    monthly_rev = monthly_rev[["month", "revenue"]]
    rev["mrr"] = float(monthly_rev["revenue"].iloc[-1]) if len(monthly_rev) > 0 else 0
    rev["arr"] = rev["mrr"] * 12
    rev["mrr_growth"] = float((monthly_rev["revenue"].iloc[-1] - monthly_rev["revenue"].iloc[-2]) / monthly_rev["revenue"].iloc[-2] * 100) if len(monthly_rev) >= 2 and monthly_rev["revenue"].iloc[-2] > 0 else 0
    rev["waterfall"] = monthly_rev.to_dict("records")
    if "user_id" in df.columns:
        user_ltv = df.groupby("user_id")["revenue"].sum().sort_values(ascending=False)
        rev["ltv_curve"] = [{"percentile": i, "ltv": float(user_ltv.quantile(i/100))} for i in range(0, 101, 5)]
    else:
        rev["ltv_curve"] = []
    if "subscription" in df.columns:
        sub_breakdown = df.groupby("subscription")["revenue"].sum().reset_index().to_dict("records")
        rev["subscription"] = sub_breakdown
    else:
        rev["subscription"] = []
    return rev

def build_revenue_charts(df, rev_metrics):
    charts = {}
    if rev_metrics.get("waterfall") and len(rev_metrics["waterfall"]) > 0:
        try:
            water_df = pd.DataFrame(rev_metrics["waterfall"])
            if len(water_df) > 0 and "month" in water_df.columns and "revenue" in water_df.columns:
                water_df["month"] = water_df["month"].astype(str)
                water_df["revenue"] = pd.to_numeric(water_df["revenue"], errors="coerce").fillna(0)
                fig = px.area(water_df, x="month", y="revenue", template="plotly_dark", color_discrete_sequence=["#34D399"])
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94A3B8", margin=dict(l=20, r=20, t=40, b=20), showlegend=False)
                charts["mrr_trend"] = fig.to_html(full_html=False, include_plotlyjs="cdn")
        except Exception as e:
            print(f"MRR chart error: {e}")
    if rev_metrics.get("ltv_curve") and len(rev_metrics["ltv_curve"]) > 0:
        try:
            ltv_df = pd.DataFrame(rev_metrics["ltv_curve"])
            if len(ltv_df) > 0:
                ltv_df["percentile"] = pd.to_numeric(ltv_df["percentile"], errors="coerce").fillna(0).astype(int)
                ltv_df["ltv"] = pd.to_numeric(ltv_df["ltv"], errors="coerce").fillna(0)
                fig = px.line(ltv_df, x="percentile", y="ltv", template="plotly_dark")
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94A3B8", margin=dict(l=20, r=20, t=40, b=20), showlegend=False)
                fig.update_traces(line_color="#60A5FA", fill="tozeroy", fillcolor="rgba(96,165,250,0.1)")
                charts["ltv_curve"] = fig.to_html(full_html=False, include_plotlyjs=False)
        except Exception as e:
            print(f"LTV chart error: {e}")
    if rev_metrics.get("subscription") and len(rev_metrics["subscription"]) > 0:
        try:
            sub_df = pd.DataFrame(rev_metrics["subscription"])
            if len(sub_df) > 0 and "revenue" in sub_df.columns and "subscription" in sub_df.columns:
                sub_df["revenue"] = pd.to_numeric(sub_df["revenue"], errors="coerce").fillna(0)
                fig = px.pie(sub_df, values="revenue", names="subscription", template="plotly_dark", hole=0.5)
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94A3B8", margin=dict(l=20, r=20, t=20, b=20), showlegend=False)
                fig.update_traces(marker_colors=["#34D399", "#60A5FA", "#94A3B8"])
                charts["subscription"] = fig.to_html(full_html=False, include_plotlyjs=False)
        except Exception as e:
            print(f"Subscription chart error: {e}")
    return charts

# ==================== IN-MEMORY STORE ====================
_session_data = {}

def get_session_data(session_id: str):
    return _session_data.get(session_id)

def set_session_data(session_id: str, df: pd.DataFrame, white_label: dict):
    metrics = calculate_metrics(df)
    rev_metrics = calculate_revenue_metrics(df)
    _session_data[session_id] = {
        "df": df, "white_label": white_label,
        "metrics": metrics, "charts": build_charts(df, metrics),
        "rev_metrics": rev_metrics, "rev_charts": build_revenue_charts(df, rev_metrics)
    }

# ==================== AUTH ROUTES ====================
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, username))
    user = c.fetchone()
    conn.close()

    if not user or not verify_password(password, user["hashed_password"]):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин или пароль"})

    access_token = create_access_token(data={"sub": user["username"]}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("access_token", access_token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    return response

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@app.post("/register")
async def register_post(request: Request, username: str = Form(...), email: str = Form(...), password: str = Form(...), full_name: str = Form("")):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, email))
    if c.fetchone():
        conn.close()
        return templates.TemplateResponse("register.html", {"request": request, "error": "Пользователь уже существует"})

    hashed = get_password_hash(password)
    c.execute("INSERT INTO users (username, email, hashed_password, full_name) VALUES (?, ?, ?, ?)",
              (username, email, hashed, full_name))
    conn.commit()
    conn.close()

    access_token = create_access_token(data={"sub": username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("access_token", access_token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    return response

@app.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response

@app.get("/token")
async def token(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (form_data.username,))
    user = c.fetchone()
    conn.close()
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user["username"]}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": access_token, "token_type": "bearer"}

# ==================== WEBSOCKET ====================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("action") == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
            elif msg.get("action") == "subscribe_metrics":
                await websocket.send_json({"type": "subscribed", "channel": "metrics"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def broadcast_metrics_update(session_id: str):
    data = get_session_data(session_id)
    if data:
        await manager.broadcast({
            "type": "metrics_update",
            "session_id": session_id,
            "metrics": data["metrics"],
            "timestamp": datetime.now().isoformat()
        })

# ==================== EXPORT ROUTES ====================
@app.get("/export", response_class=HTMLResponse)
def export_page(request: Request):
    user = get_current_user(request)
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    has_data = data is not None
    white_label = data["white_label"] if data else {"company_name": "MetricsAI", "logo_text": "MetricsAI"}
    return templates.TemplateResponse("export.html", {
        "request": request, "has_data": has_data, "white_label": white_label,
        "user": user, "page": "export"
    })

@app.post("/export/png")
async def export_png(request: Request, chart_name: str = Form("revenue")):
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    if not data:
        return JSONResponse({"error": "No data"}, status_code=400)

    df = data["df"]
    metrics = data["metrics"]

    if chart_name == "revenue" and metrics.get("monthly_trend"):
        monthly_df = pd.DataFrame(metrics["monthly_trend"])
        fig = px.line(monthly_df, x="month", y="revenue", template="plotly_dark")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94A3B8", margin=dict(l=20, r=20, t=40, b=20), showlegend=False)
        fig.update_traces(line_color="#F8FAFC", line_width=3)
    elif chart_name == "funnel" and metrics.get("funnel"):
        funnel_df = pd.DataFrame(metrics["funnel"])
        fig = px.funnel(funnel_df, x="users", y="step", template="plotly_dark")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94A3B8", margin=dict(l=20, r=20, t=20, b=20), showlegend=False)
    elif chart_name == "channel" and "channel" in df.columns:
        channel_df = df.groupby("channel")["revenue"].sum().reset_index().sort_values("revenue", ascending=True)
        fig = px.bar(channel_df, x="revenue", y="channel", orientation="h", template="plotly_dark")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#94A3B8", margin=dict(l=20, r=20, t=20, b=20), showlegend=False)
        fig.update_traces(marker_color="#F8FAFC", marker_opacity=0.8)
    else:
        return JSONResponse({"error": "Chart not available"}, status_code=400)

    try:
        img_bytes = fig.to_image(format="png", width=1200, height=600, scale=2)
        return StreamingResponse(BytesIO(img_bytes), media_type="image/png", headers={"Content-Disposition": f"attachment; filename={chart_name}.png"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/export/pdf")
async def export_pdf(request: Request):
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    if not data:
        return JSONResponse({"error": "No data"}, status_code=400)

    try:
        from weasyprint import HTML as WeasyHTML
        metrics = data["metrics"]
        charts = data["charts"]
        white_label = data["white_label"]

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head><style>
        body {{ font-family: 'Inter', sans-serif; background: #000; color: #F5F5F7; padding: 40px; }}
        .header {{ font-size: 28px; font-weight: 800; margin-bottom: 20px; }}
        .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 30px; }}
        .card {{ background: rgba(28,28,30,0.6); border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 20px; }}
        .label {{ font-size: 11px; color: #86868B; text-transform: uppercase; letter-spacing: 0.1em; }}
        .value {{ font-size: 24px; font-weight: 700; margin-top: 8px; }}
        .chart {{ margin-top: 20px; }}
        </style></head>
        <body>
        <div class="header">{white_label['company_name']} — Dashboard Report</div>
        <div class="grid">
            <div class="card"><div class="label">Revenue</div><div class="value">{metrics['total_revenue']:,.0f} ₽</div></div>
            <div class="card"><div class="label">Users</div><div class="value">{metrics['total_users']:,}</div></div>
            <div class="card"><div class="label">ARPU</div><div class="value">{metrics['arpu']:,.0f} ₽</div></div>
        </div>
        <div class="chart">{charts.get('revenue', '')}</div>
        </body></html>
        """
        pdf = WeasyHTML(string=html_content).write_pdf()
        return StreamingResponse(BytesIO(pdf), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=dashboard.pdf"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/export/pptx")
async def export_pptx(request: Request):
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    if not data:
        return JSONResponse({"error": "No data"}, status_code=400)

    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # Title slide
        blank_layout = prs.slide_layouts[6]  # blank
        slide = prs.slides.add_slide(blank_layout)

        # Background
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(0, 0, 0)

        # Title
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(12), Inches(1))
        tf = title_box.text_frame
        p = tf.paragraphs[0]
        p.text = f"{data['white_label']['company_name']} — Analytics Report"
        p.font.size = Pt(32)
        p.font.bold = True
        p.font.color.rgb = RGBColor(245, 245, 247)

        # Metrics
        metrics = data["metrics"]
        y_pos = 1.8
        for label, value, color in [
            ("Revenue", f"{metrics['total_revenue']:,.0f} ₽", RGBColor(52, 211, 153)),
            ("Users", f"{metrics['total_users']:,}", RGBColor(96, 165, 250)),
            ("ARPU", f"{metrics['arpu']:,.0f} ₽", RGBColor(255, 159, 10)),
            ("LTV/CAC", f"{metrics['ltv_cac_ratio']:.1f}x", RGBColor(191, 90, 242)),
        ]:
            box = slide.shapes.add_textbox(Inches(0.5), Inches(y_pos), Inches(3), Inches(1.2))
            tf = box.text_frame
            p = tf.paragraphs[0]
            p.text = label
            p.font.size = Pt(12)
            p.font.color.rgb = RGBColor(134, 134, 139)

            p2 = tf.add_paragraph()
            p2.text = value
            p2.font.size = Pt(28)
            p2.font.bold = True
            p2.font.color.rgb = color
            y_pos += 1.5

        # Date
        date_box = slide.shapes.add_textbox(Inches(0.5), Inches(6.5), Inches(4), Inches(0.5))
        tf = date_box.text_frame
        p = tf.paragraphs[0]
        p.text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        p.font.size = Pt(10)
        p.font.color.rgb = RGBColor(99, 99, 102)

        output = BytesIO()
        prs.save(output)
        output.seek(0)
        return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                headers={"Content-Disposition": "attachment; filename=dashboard.pptx"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ==================== EXISTING ROUTES (with auth context) ====================
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    session_id = request.cookies.get("session_id", hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:16])
    user = get_current_user(request)
    data = get_session_data(session_id)
    has_data = data is not None
    metrics = data["metrics"] if data else {}
    charts = data["charts"] if data else {}
    white_label = data["white_label"] if data else {"company_name": "MetricsAI", "logo_text": "MetricsAI"}

    response = templates.TemplateResponse("dashboard.html", {
        "request": request, "has_data": has_data, "metrics": metrics,
        "charts": charts, "white_label": white_label, "page": "dashboard", "user": user
    })
    response.set_cookie("session_id", session_id)
    return response

@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request):
    user = get_current_user(request)
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    white_label = data["white_label"] if data else {"company_name": "MetricsAI", "logo_text": "MetricsAI"}
    return templates.TemplateResponse("sources.html", {
        "request": request, "white_label": white_label, "page": "sources", "user": user
    })

@app.post("/load-sample")
def load_sample(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:16]
    df = generate_sample_data()
    set_session_data(session_id, df, {"company_name": "MetricsAI", "logo_text": "MetricsAI"})
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("session_id", session_id)
    return response

@app.post("/upload-csv")
async def upload_csv(request: Request, file: UploadFile = File(...)):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:16]
    contents = await file.read()
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(contents))
        elif file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(BytesIO(contents))
        else:
            return HTMLResponse("<div class='glass-card text-red-400 p-4'>❌ Поддерживаются только CSV и Excel</div>")

        date_col = next((c for c in df.columns if 'date' in c.lower()), None)
        if date_col and date_col != 'date':
            df = df.rename(columns={date_col: 'date'})
        user_col = next((c for c in df.columns if any(x in c.lower() for x in ['user', 'customer', 'client'])), None)
        if user_col and user_col != 'user_id':
            df = df.rename(columns={user_col: 'user_id'})
        revenue_col = next((c for c in df.columns if any(x in c.lower() for x in ['revenue', 'amount', 'sum', 'price', 'value'])), None)
        if revenue_col and revenue_col != 'revenue':
            df = df.rename(columns={revenue_col: 'revenue'})
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])

        set_session_data(session_id, df, {"company_name": "MetricsAI", "logo_text": "MetricsAI"})

        conn = get_db()
        c = conn.cursor()
        user = get_current_user(request)
        user_id = user["id"] if user else None
        c.execute("INSERT INTO uploads (filename, source_type, upload_date, rows, cols, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                  (file.filename, "upload", datetime.now().isoformat(), len(df), len(df.columns), user_id))
        conn.commit()
        conn.close()

        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie("session_id", session_id)
        return response
    except Exception as e:
        return HTMLResponse(f"<div class='glass-card text-red-400 p-4'>❌ Ошибка: {str(e)}</div>")

@app.post("/connect-google-sheets")
async def connect_google_sheets(request: Request, url: str = Form(...)):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:16]
    try:
        if '/edit' in url:
            csv_url = url.replace('/edit', '/export?format=csv')
        elif 'export?format=csv' not in url:
            csv_url = url + '/export?format=csv'
        else:
            csv_url = url
        df = pd.read_csv(csv_url)
        date_col = next((c for c in df.columns if 'date' in c.lower()), None)
        if date_col and date_col != 'date':
            df = df.rename(columns={date_col: 'date'})
        user_col = next((c for c in df.columns if any(x in c.lower() for x in ['user', 'customer', 'client'])), None)
        if user_col and user_col != 'user_id':
            df = df.rename(columns={user_col: 'user_id'})
        revenue_col = next((c for c in df.columns if any(x in c.lower() for x in ['revenue', 'amount', 'sum', 'price', 'value'])), None)
        if revenue_col and revenue_col != 'revenue':
            df = df.rename(columns={revenue_col: 'revenue'})
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        set_session_data(session_id, df, {"company_name": "MetricsAI", "logo_text": "MetricsAI"})

        conn = get_db()
        c = conn.cursor()
        user = get_current_user(request)
        user_id = user["id"] if user else None
        c.execute("INSERT INTO uploads (filename, source_type, upload_date, rows, cols, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                  ("google_sheets", "google_sheets", datetime.now().isoformat(), len(df), len(df.columns), user_id))
        conn.commit()
        conn.close()

        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie("session_id", session_id)
        return response
    except Exception as e:
        return HTMLResponse(f"<div class='glass-card text-red-400 p-4'>❌ Ошибка загрузки Google Sheets: {str(e)}<br><br>Проверьте, что таблица опубликована (File → Share → Anyone with link)</div>")

@app.post("/connect-postgresql")
async def connect_postgresql(request: Request, host: str = Form(...), port: str = Form("5432"), database: str = Form(...), user: str = Form(...), password: str = Form(...), query: str = Form(...)):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:16]
    try:
        import psycopg2
        conn = psycopg2.connect(host=host, port=port, database=database, user=user, password=password)
        df = pd.read_sql(query, conn)
        conn.close()
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        set_session_data(session_id, df, {"company_name": "MetricsAI", "logo_text": "MetricsAI"})
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie("session_id", session_id)
        return response
    except ImportError:
        return HTMLResponse("<div class='glass-card text-red-400 p-4'>❌ Установите psycopg2: <code>pip install psycopg2-binary</code></div>")
    except Exception as e:
        return HTMLResponse(f"<div class='glass-card text-red-400 p-4'>❌ Ошибка подключения: {str(e)}</div>")

@app.post("/api/v1/ingest")
async def api_ingest(request: Request):
    try:
        body = await request.json()
        session_id = request.headers.get("X-Session-ID", hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:16])
        if isinstance(body, list):
            df = pd.DataFrame(body)
        elif isinstance(body, dict) and "data" in body:
            df = pd.DataFrame(body["data"])
        else:
            return JSONResponse({"error": "Expected JSON array or {data: [...]}"}, status_code=400)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        set_session_data(session_id, df, {"company_name": "MetricsAI", "logo_text": "MetricsAI"})
        return JSONResponse({
            "success": True, "session_id": session_id, "rows": len(df), "cols": len(df.columns),
            "dashboard_url": f"/?session_id={session_id}"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/v1/health")
def api_health():
    return {"status": "ok", "version": "3.1", "timestamp": datetime.now().isoformat()}

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
        "request": request, "metrics": metrics, "charts": charts, "white_label": white_label,
    })

@app.get("/funnel", response_class=HTMLResponse)
def funnel_page(request: Request):
    user = get_current_user(request)
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    has_data = data is not None
    charts = data["charts"] if data else {}
    white_label = data["white_label"] if data else {"company_name": "MetricsAI", "logo_text": "MetricsAI"}
    return templates.TemplateResponse("funnel.html", {
        "request": request, "has_data": has_data, "charts": charts,
        "white_label": white_label, "page": "funnel", "user": user
    })

@app.get("/ai", response_class=HTMLResponse)
def ai_page(request: Request):
    user = get_current_user(request)
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    has_data = data is not None
    white_label = data["white_label"] if data else {"company_name": "MetricsAI", "logo_text": "MetricsAI"}
    return templates.TemplateResponse("ai.html", {
        "request": request, "has_data": has_data, "white_label": white_label, "page": "ai", "insights": "", "user": user
    })

@app.post("/ai-generate")
def ai_generate(request: Request):
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    if not data:
        return HTMLResponse("<div class='glass-card text-red-400 p-4'>Сначала загрузите данные</div>")
    m = data["metrics"]
    insights = f"""<div class='ai-insight'><div class='ai-header'>🧠 AI Product Analyst</div><div style='color: #E2E8F0; line-height: 1.7;'><b>1. LTV/CAC ratio ({m.get('ltv_cac_ratio', 0):.1f}x)</b> — {'ниже нормы' if m.get('ltv_cac_ratio', 0) < 3 else 'в норме'}. При healthy ratio > 3x можно масштабировать маркетинг.<br><br><b>2. ARPU {m.get('arpu', 0):,.0f} ₽</b> — анализируйте ARPU по каналам. Возможно, некоторые каналы приносят пользователей с низкой монетизацией.<br><br><b>3. Выручка {m.get('total_revenue', 0):,.0f} ₽</b> — отслеживайте динамику ежемесячно. Рекомендуем настроить alerts на падение > 15%.<br><br><b>4. Сегментация</b> — проведите RFM-анализ для персонализации маркетинговых кампаний.</div></div>"""
    return HTMLResponse(insights)

@app.get("/ab", response_class=HTMLResponse)
def ab_page(request: Request):
    user = get_current_user(request)
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    white_label = data["white_label"] if data else {"company_name": "MetricsAI", "logo_text": "MetricsAI"}
    return templates.TemplateResponse("ab.html", {
        "request": request, "white_label": white_label, "page": "ab", "user": user
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
    html = f"""<div class="grid grid-cols-4 gap-4 mt-6"><div class="metric-container"><div class="metric-label">Конверсия A</div><div class="metric-value">{p_a:.2%}</div></div><div class="metric-container"><div class="metric-label">Конверсия B</div><div class="metric-value">{p_b:.2%}</div></div><div class="metric-container"><div class="metric-label">Uplift</div><div class="metric-value" style="color:{'#34D399' if uplift>0 else '#F87171'}">{uplift:+.1f}%</div></div><div class="metric-container"><div class="metric-label">Значимость</div><div class="metric-value" style="color:{'#34D399' if is_significant else '#F87171'}">{'✅ Да' if is_significant else '❌ Нет'}</div></div></div><div class="glass-card mt-4"><div style="color:#94A3B8;font-size:0.9rem">Z-score: <b>{z:.3f}</b> | Критическое: ±{z_critical}</div></div>"""
    return HTMLResponse(html)

@app.get("/revenue", response_class=HTMLResponse)
def revenue_page(request: Request):
    user = get_current_user(request)
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    has_data = data is not None
    rev_metrics = data["rev_metrics"] if data else {}
    rev_charts = data["rev_charts"] if data else {}
    metrics = data["metrics"] if data else {}
    charts = data["charts"] if data else {}
    white_label = data["white_label"] if data else {"company_name": "MetricsAI", "logo_text": "MetricsAI"}
    return templates.TemplateResponse("revenue.html", {
        "request": request, "has_data": has_data, "rev_metrics": rev_metrics,
        "rev_charts": rev_charts, "metrics": metrics, "charts": charts, "white_label": white_label, "page": "revenue", "user": user
    })

@app.get("/builder", response_class=HTMLResponse)
def builder_page(request: Request):
    user = get_current_user(request)
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    has_data = data is not None
    white_label = data["white_label"] if data else {"company_name": "MetricsAI", "logo_text": "MetricsAI"}
    return templates.TemplateResponse("builder.html", {
        "request": request, "has_data": has_data, "white_label": white_label, "page": "builder", "user": user
    })

@app.post("/builder-generate")
def builder_generate(request: Request, metric: str = Form("revenue"), period: str = Form("monthly"), chart_type: str = Form("line"), layout: str = Form("standard")):
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    if not data:
        return HTMLResponse("<div class='glass-card text-red-400 p-4'>Сначала загрузите данные</div>")
    df = data["df"]
    df["date"] = pd.to_datetime(df["date"])
    if period == "monthly":
        df["period"] = df["date"].dt.strftime("%Y-%m")
    elif period == "weekly":
        df["period"] = df["date"].dt.strftime("%Y-W%W")
    else:
        df["period"] = df["date"].dt.strftime("%Y-%m-%d")
    grouped = df.groupby("period")[metric].sum().reset_index()
    if chart_type == "line":
        fig = px.line(grouped, x="period", y=metric, template="plotly_dark")
        fig.update_traces(line_color="#F8FAFC", line_width=3)
    elif chart_type == "bar":
        fig = px.bar(grouped, x="period", y=metric, template="plotly_dark")
        fig.update_traces(marker_color="#94A3B8", marker_opacity=0.7)
    elif chart_type == "area":
        fig = px.area(grouped, x="period", y=metric, template="plotly_dark")
        fig.update_traces(line_color="#34D399", fillcolor="rgba(52,211,153,0.1)")
    else:
        fig = px.scatter(grouped, x="period", y=metric, template="plotly_dark")
        fig.update_traces(marker_color="#60A5FA")
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#94A3B8", margin=dict(l=20, r=20, t=40, b=20), showlegend=False,
        title=dict(text=f"{metric.upper()} — {period}", font_color="#F8FAFC", font_size=14)
    )
    chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")
    return HTMLResponse(f"""<div class="glass-card"><h3 class="text-lg font-bold text-white mb-4">📊 {metric.upper()} ({period})</h3><div style="height: 400px;">{chart_html}</div></div>""")

# ==================== LIVE METRICS SIMULATION (for WebSocket demo) ====================
@app.post("/simulate-live")
async def simulate_live(request: Request):
    """Generate a live data point and broadcast to all connected clients"""
    session_id = request.cookies.get("session_id")
    data = get_session_data(session_id)
    if not data:
        return JSONResponse({"error": "No data"}, status_code=400)

    # Simulate a new data point
    df = data["df"]
    new_row = {
        "date": datetime.now(),
        "user_id": f"user_{np.random.randint(0, 500):04d}",
        "revenue": np.random.exponential(200) if np.random.random() > 0.7 else 0,
        "channel": np.random.choice(["organic", "instagram", "google", "facebook", "email", "tiktok", "referral"]),
        "event_type": np.random.choice(["impression", "click", "visit", "add_to_cart", "purchase"]),
        "marketing_cost": np.random.choice([0, 0, 0, 30, 50, 80, 120, 200]),
        "subscription": np.random.choice(["monthly", "annual", "none"], p=[0.15, 0.05, 0.80]),
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    set_session_data(session_id, df, data["white_label"])

    await broadcast_metrics_update(session_id)
    return JSONResponse({"success": True, "new_rows": 1})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
