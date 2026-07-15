# MetricsAI v2.0

Enterprise-grade AI analytics for product & marketing metrics.

## What's New in v2.0

### Phase 1: MVP Core
- **Multi-source data**: CSV, Excel (.xlsx), JSON, Google Sheets, Manual input, Demo data
- **Custom dashboards**: Real-time metrics with period comparison (YoY, MoM)
- **White-label**: Custom company name and logo text
- **PDF export**: Generate and download professional reports

### Phase 2: Pro Analytics
- **RFM segmentation**: Customer segmentation with AI recommendations
- **A/B test calculator**: Statistical significance calculator with Z-score
- **Anomaly detection**: AI-powered anomaly detection in revenue trends
- **Forecasting**: 3-month revenue forecast using linear regression
- **AI insights**: GPT-4o-mini powered analysis for metrics, RFM, and anomalies

### Phase 3: Enterprise Ready
- **Role-based navigation**: Modular sidebar navigation
- **Multi-format export**: CSV, Excel, JSON, PDF
- **Public dashboard ready**: Architecture prepared for public sharing

## Tech Stack
- Python + Streamlit
- Plotly (interactive charts)
- SQLite (data persistence)
- OpenAI API (AI insights)
- FPDF2 (PDF generation)
- OpenPyXL (Excel support)

## Deploy
1. Push to GitHub
2. Connect to Streamlit Cloud
3. Add OPENAI_API_KEY in Secrets
4. Deploy

## Data Format
Upload CSV/Excel with columns: date, user_id, revenue, channel, event_type, marketing_cost, product_category

All column names are auto-detected (supports Russian and English variants).
