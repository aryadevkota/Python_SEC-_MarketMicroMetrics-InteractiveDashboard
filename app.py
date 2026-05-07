import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import os
import requests
from dotenv import load_dotenv

load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")
DB_NAME = "advanced_microstructure.db"

# ---------------------------------------------------------
# METRIC DEFINITIONS
# ---------------------------------------------------------
METRIC_DEFINITIONS = {
    "oddlot_rate": "Odd-lot rate is the percentage of trades executed in quantities smaller than the standard round lot (typically 100 shares). A high odd-lot rate can signal increased retail participation.",
    "oddlot_volume": "Odd-lot volume is the total share volume traded in odd-lot sized orders (less than 100 shares). It is used to gauge retail investor activity.",
    "hidden_rate": "Hidden rate is the proportion of trading volume executed via hidden or non-displayed orders. Higher hidden rates suggest more institutional activity seeking to minimize market impact.",
    "hidden_volume": "Hidden volume is the total share volume traded through non-displayed or iceberg orders, often associated with large institutional trades.",
    "cancel_to_trade": "Cancel-to-trade ratio is the number of order cancellations divided by the number of executed trades. A very high ratio may indicate algorithmic or high-frequency trading activity.",
    "trade_volume": "Trade volume is the total number of shares traded over a given period. It is a core measure of market activity and liquidity.",
    "quantile_bucket": "Quantile bucket is a ranking group (1 to 10) that a security falls into based on the chosen sort variable (e.g. Market Cap, Volatility). Bucket 1 is the lowest and bucket 10 is the highest.",
    "sort_variable": "Sort variable is the characteristic used to rank and group securities into quantile buckets. Options include Market Cap, Volatility, Price, and Turnover.",
    "market cap": "Market capitalization is the total market value of a company's outstanding shares. It is calculated as share price multiplied by shares outstanding.",
    "volatility": "Volatility measures the degree of variation in a security's price over time. Higher volatility indicates larger and more frequent price swings.",
    "turnover": "Turnover (or share turnover) is the ratio of the volume of shares traded to the total shares outstanding. It reflects how actively a stock is being traded.",
    "etp": "ETP stands for Exchange-Traded Product, which includes ETFs (Exchange-Traded Funds) and ETNs (Exchange-Traded Notes). These are securities that track an index, commodity, or basket of assets and trade on an exchange.",
    "stock": "A stock (or equity) represents an ownership share in a company. Unlike ETPs, individual stocks represent a single company rather than a basket of assets.",
}

# ---------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------
def run_query(sql: str) -> pd.DataFrame:
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query(sql, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame({"error": [str(e)]})


def get_schema_context() -> str:
    return """
Database: market_metrics (SQLite)
Columns:
  - trade_date     (TEXT)    : date in YYYYMMDD format
  - asset_class    (TEXT)    : 'stock' or 'etp'
  - metric_name    (TEXT)    : 'hidden_rate', 'oddlot_volume', 'oddlot_rate', 'cancel_to_trade', 'trade_volume', 'hidden_volume'
  - sort_variable  (TEXT)    : 'Market Cap', 'Volatility', 'Price', 'Turnover'
  - quantile_bucket(INTEGER) : 1 (lowest) to 10 (highest)
  - metric_value   (REAL)    : the raw metric value
"""

# ---------------------------------------------------------
# QUESTION CLASSIFIER
# ---------------------------------------------------------
def classify_question(question: str):
    q = question.lower()
    q_normalized = q.replace("_", " ")

    # Definition questions
    for key in METRIC_DEFINITIONS:
        key_spaced = key.replace("_", " ")
        if (key in q or key_spaced in q_normalized) and any(
            w in q for w in ["what", "mean", "define", "explain", "describe", "is a", "is an"]
        ):
            return "definition", key

    # Correlation questions
    if any(w in q for w in ["correlation", "correlate", "relationship between", "related to"]):
        return "correlation", None

    # Comparison questions
    if any(w in q for w in ["compare", "comparison", "versus", "vs", "difference", "differ"]):
        return "comparison", None

    # Ranking
    if any(w in q for w in ["highest", "lowest", "top", "bottom", "rank", "best", "worst", "maximum", "minimum"]):
        return "ranking", None

    # Summary
    if any(w in q for w in ["summarize", "summary", "trend", "overview", "describe the data", "tell me about"]):
        return "summary", None

    return "general", None


# ---------------------------------------------------------
# DATA FETCHERS
# ---------------------------------------------------------
def detect_metric(q: str, default: str = "oddlot_rate") -> str:
    for m in ["oddlot_rate", "oddlot_volume", "hidden_rate", "hidden_volume", "cancel_to_trade", "trade_volume"]:
        if m.replace("_", " ") in q or m in q:
            return m
    return default


def fetch_comparison_data(question: str) -> tuple[str, pd.DataFrame]:
    q = question.lower()
    metric = detect_metric(q)
    sql = f"""
        SELECT asset_class, quantile_bucket, ROUND(AVG(metric_value), 6) as avg_value
        FROM market_metrics
        WHERE metric_name = '{metric}'
        GROUP BY asset_class, quantile_bucket
        ORDER BY asset_class, quantile_bucket
    """
    df = run_query(sql)
    if "error" in df.columns:
        return f"SQL error: {df['error'][0]}", pd.DataFrame()
    context = f"Comparison data for '{metric}' across quantile buckets:\n\n{df.to_string(index=False)}"
    return context, df


def fetch_correlation_data(question: str) -> tuple[str, pd.DataFrame]:
    q = question.lower()
    sort_var = "Volatility"
    for sv in ["market cap", "volatility", "price", "turnover"]:
        if sv in q:
            sort_var = sv.title()
            break
    metric = detect_metric(q)
    sql = f"""
        SELECT quantile_bucket, ROUND(AVG(metric_value), 6) as avg_value
        FROM market_metrics
        WHERE metric_name = '{metric}' AND sort_variable = '{sort_var}'
        GROUP BY quantile_bucket
        ORDER BY quantile_bucket
    """
    df = run_query(sql)
    if "error" in df.columns:
        return f"SQL error: {df['error'][0]}", pd.DataFrame()
    corr_str = ""
    if len(df) > 1:
        corr = df["quantile_bucket"].corr(df["avg_value"])
        corr_str = f"\nPearson correlation between {sort_var} bucket and {metric}: {corr:.4f}"
    context = f"Data for '{metric}' sorted by '{sort_var}':\n\n{df.to_string(index=False)}{corr_str}"
    return context, df


def fetch_ranking_data(question: str) -> tuple[str, pd.DataFrame]:
    q = question.lower()
    metric = detect_metric(q)
    asset = None
    if "etp" in q:
        asset = "etp"
    elif "stock" in q:
        asset = "stock"
    asset_filter = f"AND asset_class = '{asset}'" if asset else ""
    sql = f"""
        SELECT asset_class, quantile_bucket, ROUND(AVG(metric_value), 6) as avg_value
        FROM market_metrics
        WHERE metric_name = '{metric}' {asset_filter}
        GROUP BY asset_class, quantile_bucket
        ORDER BY avg_value DESC
        LIMIT 10
    """
    df = run_query(sql)
    if "error" in df.columns:
        return f"SQL error: {df['error'][0]}", pd.DataFrame()
    context = f"Rankings for '{metric}' (highest average values):\n\n{df.to_string(index=False)}"
    return context, df


def fetch_summary_data(question: str) -> tuple[str, pd.DataFrame]:
    q = question.lower()
    asset = None
    if "etp" in q:
        asset = "etp"
    elif "stock" in q:
        asset = "stock"
    asset_filter = f"WHERE asset_class = '{asset}'" if asset else ""
    sql = f"""
        SELECT metric_name, asset_class, ROUND(AVG(metric_value), 6) as avg_value,
               ROUND(MIN(metric_value), 6) as min_value, ROUND(MAX(metric_value), 6) as max_value
        FROM market_metrics
        {asset_filter}
        GROUP BY metric_name, asset_class
        ORDER BY metric_name, asset_class
    """
    df = run_query(sql)
    if "error" in df.columns:
        return f"SQL error: {df['error'][0]}", pd.DataFrame()
    context = f"Summary statistics:\n\n{df.to_string(index=False)}"
    return context, df


# ---------------------------------------------------------
# FORMAT RAW DATA AS READABLE FALLBACK (no LLM needed)
# ---------------------------------------------------------
def format_data_as_answer(question: str, q_type: str, data_context: str, df: pd.DataFrame) -> str:
    """Returns a clean plain-text answer directly from the data, no API required."""
    q = question.lower()
    metric = detect_metric(q)

    if q_type == "comparison" and not df.empty:
        etp_df = df[df["asset_class"] == "etp"] if "asset_class" in df.columns else pd.DataFrame()
        stock_df = df[df["asset_class"] == "stock"] if "asset_class" in df.columns else pd.DataFrame()

        lines = [f"**Comparison: `{metric.replace('_', ' ').title()}` — ETP vs Stock**\n"]

        if not etp_df.empty:
            etp_avg = etp_df["avg_value"].mean()
            lines.append(f"- **ETP** average across all buckets: `{etp_avg:.6f}`")
        if not stock_df.empty:
            stock_avg = stock_df["avg_value"].mean()
            lines.append(f"- **Stock** average across all buckets: `{stock_avg:.6f}`")

        if not etp_df.empty and not stock_df.empty:
            higher = "ETPs" if etp_avg > stock_avg else "Stocks"
            lines.append(f"\n**{higher}** have a higher average `{metric.replace('_', ' ')}` overall.")

        lines.append(f"\n**Full breakdown by quantile bucket:**\n```\n{df.to_string(index=False)}\n```")
        return "\n".join(lines)

    elif q_type == "correlation" and not df.empty:
        return f"**Correlation Data:**\n```\n{data_context}\n```"

    elif q_type == "ranking" and not df.empty:
        return f"**Rankings:**\n```\n{df.to_string(index=False)}\n```"

    elif q_type == "summary" and not df.empty:
        return f"**Summary Statistics:**\n```\n{df.to_string(index=False)}\n```"

    return data_context


# ---------------------------------------------------------
# HuggingFace LLM CALL
# ---------------------------------------------------------
def call_llm(question: str, data_context: str, ui_context: str, fallback_answer: str) -> str:
    """Calls HF API. If it fails for any reason, returns the formatted fallback answer instead."""
    if not HF_TOKEN:
        return fallback_answer

    prompt = f"""<s>[INST] You are a senior Quantitative Financial Analyst assistant.
Use the data and context below to answer the user's question clearly and professionally.
Do not make up numbers — only use the data provided.

DATABASE SCHEMA:
{get_schema_context()}

CURRENT DASHBOARD VIEW:
{ui_context}

DATA / CONTEXT:
{data_context}

USER QUESTION:
{question}
[/INST]"""

    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 300,
            "temperature": 0.3,
            "return_full_text": False,
        }
    }

    try:
        response = requests.post(
            "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3",
            headers=headers,
            json=payload,
            timeout=60,
        )

        # Empty body = cold start → return fallback immediately
        if not response.text.strip():
            return (
                fallback_answer +
                "\n\n---\n*💡 AI narrative unavailable — model is cold-starting on HuggingFace. "
                "The data above is pulled directly from your database.*"
            )

        result = response.json()

        if isinstance(result, list) and len(result) > 0 and "generated_text" in result[0]:
            return result[0]["generated_text"].strip()
        elif isinstance(result, dict) and "error" in result:
            estimated = result.get("estimated_time", "unknown")
            return (
                fallback_answer +
                f"\n\n---\n*💡 AI narrative unavailable — model loading (~{estimated}s). "
                "The data above is pulled directly from your database.*"
            )
        else:
            return fallback_answer

    except requests.exceptions.Timeout:
        return (
            fallback_answer +
            "\n\n---\n*💡 AI narrative unavailable — request timed out. "
            "The data above is pulled directly from your database.*"
        )
    except Exception:
        return fallback_answer


# ---------------------------------------------------------
# MAIN ANSWER FUNCTION
# ---------------------------------------------------------
def answer_question(question: str, ui_context: str) -> str:
    q_type, key = classify_question(question)

    # Definitions never need the API
    if q_type == "definition":
        definition = METRIC_DEFINITIONS.get(key)
        if definition:
            return f"**{key.replace('_', ' ').title()}**\n\n{definition}"
        else:
            return (
                f"No definition found for '{key}'. Try asking about: "
                "oddlot rate, hidden rate, cancel to trade, trade volume, "
                "etp, stock, volatility, market cap, or turnover."
            )

    elif q_type == "comparison":
        data_context, df = fetch_comparison_data(question)
    elif q_type == "correlation":
        data_context, df = fetch_correlation_data(question)
    elif q_type == "ranking":
        data_context, df = fetch_ranking_data(question)
    elif q_type == "summary":
        data_context, df = fetch_summary_data(question)
    else:
        data_context, df = fetch_summary_data(question)

    # Always build a clean fallback from raw data first
    fallback_answer = format_data_as_answer(question, q_type, data_context, df)

    # Try to enrich with LLM narrative — fall back to raw data if API fails
    return call_llm(question, data_context, ui_context, fallback_answer)


# ---------------------------------------------------------
# STREAMLIT DASHBOARD
# ---------------------------------------------------------
st.set_page_config(page_title="Market Microstructure AI", layout="wide")
st.title("📈 Market Microstructure AI Assistant")

st.sidebar.title("📊 Data Controls")
try:
    conn = sqlite3.connect(DB_NAME)
    assets = pd.read_sql("SELECT DISTINCT asset_class FROM market_metrics", conn)['asset_class'].tolist()
    metrics = pd.read_sql("SELECT DISTINCT metric_name FROM market_metrics", conn)['metric_name'].tolist()
    sorts = pd.read_sql("SELECT DISTINCT sort_variable FROM market_metrics", conn)['sort_variable'].tolist()
    conn.close()

    sel_asset = st.sidebar.selectbox("Asset Class", assets)
    sel_metric = st.sidebar.selectbox("Metric", metrics)
    sel_sort = st.sidebar.selectbox("Sort Variable", sorts)
except Exception:
    st.error("Database not found. Please run your ETL script first.")
    st.stop()

# Visualization
viz_query = f"""
    SELECT quantile_bucket, AVG(metric_value) as val
    FROM market_metrics
    WHERE asset_class='{sel_asset}' AND metric_name='{sel_metric}' AND sort_variable='{sel_sort}'
    GROUP BY 1 ORDER BY 1
"""
df = run_query(viz_query)

if not df.empty and "error" not in df.columns:
    st.subheader(f"Analyzing {sel_metric.title()} by {sel_sort}")
    fig = px.bar(df, x='quantile_bucket', y='val', color='val', color_continuous_scale='Plasma')
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# CHAT INTERFACE
# ---------------------------------------------------------
st.divider()
st.subheader("💬 Financial Data Assistant")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if user_input := st.chat_input("E.g., What does oddlot rate mean? / Compare hidden rates for etp vs stocks"):
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.chat_history.append({"role": "user", "content": user_input})

    ui_context = f"The user is currently viewing '{sel_metric}' for '{sel_asset}' sorted by '{sel_sort}'."

    with st.chat_message("assistant"):
        with st.spinner("Querying database and generating response..."):
            response = answer_question(user_input, ui_context)
            st.markdown(response)
    st.session_state.chat_history.append({"role": "assistant", "content": response})