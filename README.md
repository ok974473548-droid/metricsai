# MetricsAI

AI-powered analytics dashboard for product & marketing metrics. Built for the "Artificial Intelligence in Marketing & Product Management" master's program portfolio.

## Features

- Auto-calculated metrics: ARPU, LTV, CAC, AOV, LTV/CAC ratio
- Trend analysis: Monthly revenue and ARPU dynamics
- Funnel visualization: Conversion rates between stages
- Cohort retention analysis: Heatmap + average retention curves
- Channel performance: Revenue and CAC by acquisition channel
- AI Insights: GPT-4o-mini powered recommendations
- SQLite database: Upload history stored locally

## Tech Stack

- Python + Streamlit
- Plotly (interactive charts)
- SQLite (data persistence)
- OpenAI API (AI insights)
- Custom CSS (glassmorphism UI)

## Deploy on Streamlit Cloud

1. Push this repo to GitHub
2. Go to share.streamlit.io
3. Connect your GitHub repo
4. Add OPENAI_API_KEY in Settings -> Secrets
5. Deploy!

## Data Format

Upload a CSV with these columns (names are auto-detected):
- date — event date (YYYY-MM-DD)
- user_id — unique user identifier
- revenue — transaction amount
- channel — acquisition channel (optional)
- event_type — funnel stage: impression, click, visit, add_to_cart, purchase (optional)
- marketing_cost — cost per row (optional, for CAC calculation)

## Sample Data

The app includes a built-in sample data generator for testing.
