from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
import plotly
import matplotlib.pyplot as plt
from dotenv import load_dotenv
import os

load_dotenv()


def get_transaction_data():
    SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")
    SCOPES = os.getenv("SCOPES").split(",")
    SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

    credentials = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )

    service = build("sheets", "v4", credentials=credentials)

    # Call the Sheets API
    sheet = service.spreadsheets()
    result = (
        sheet.values().get(spreadsheetId=SPREADSHEET_ID, range="Transactions").execute()
    )

    values = result.get("values", [])
    return values


def get_transaction_data_df():
    values = get_transaction_data()
    df = pd.DataFrame(values[1:], columns=values[0])
    df["Date"] = pd.to_datetime(df["Date"])
    df["Amount"] = df["Amount"].apply(clean_amount)
    _add_per_category_amount(df)
    df["month_year"] = df["Date"].dt.to_period("M")
    return df


def clean_amount(x):
    # change e.g., $3,200.00 to 3200.00 in Amount column
    return float(x.replace("$", "").replace(",", ""))


def _add_per_category_amount(transaction_data: pd.DataFrame) -> pd.DataFrame:
    gb = transaction_data.groupby(["Category"])["Amount"].sum().reset_index()
    for i, row in transaction_data.iterrows():
        sel = gb["Category"] == row["Category"]
        transaction_data.loc[i, "amount_category"] = gb[sel].Amount.item()


def _to_spending(transaction_data: pd.DataFrame) -> pd.DataFrame:
    df = transaction_data[transaction_data.amount_category < 0].copy()
    df = df[
        (df["Category"] != "Transfer")
        & (df["Category"] != "Investments in Stocks")
        & (df["Category"] != "Investments in Crypto")
    ]
    df["amount_pct"] = df["Amount"] / df["Amount"].sum() * 100
    df["amount_category_pct"] = (
        df["amount_category"] / df["amount_category"].sum() * 100
    )
    df["Amount"] = -df["Amount"]
    return df


def plot_categories(transaction_data: pd.DataFrame) -> plotly.graph_objs.Figure:
    df = _to_spending(transaction_data)
    return px.sunburst(
        df,
        path=[
            "Category",
        ],
        values="Amount",
    )


def single_category(
    transaction_data: pd.DataFrame, category: str = "Groceries"
) -> pd.DataFrame:
    return transaction_data[(transaction_data["Category"] == category)].sort_values(
        "Amount"
    )[["Description", "Date", "Amount"]]


def plot_category_histogram(
    transaction_data: pd.DataFrame, category: str = "Groceries", nbins: int = 30
) -> plotly.graph_objs.Figure:
    cat = single_category(transaction_data, category)
    fig = px.histogram(cat, x="Amount", nbins=nbins)
    fig.update_layout(
        title=category.capitalize(),
        xaxis_title="Amount",
        yaxis_title="Frequency",
    )
    return fig


def plot_monthly_income(transaction_data: pd.DataFrame) -> plotly.graph_objs.Figure:
    df = (
        single_category(transaction_data, "Paycheck")
        .set_index("Date")
        .groupby(pd.Grouper(freq="ME"))["Amount"]
        .sum()
    )
    df.index = df.index.strftime("%Y-%m")
    fig = px.bar(df)
    return fig


def plot_spending_per_subcategory(transaction_data) -> plotly.graph_objs.Figure:
    df = _to_spending(transaction_data)

    df["Date"] = pd.to_datetime(df["Date"]).dt.to_period("M").astype(str)
    df = df.groupby(["Date", "Category"])["Amount"].sum().reset_index()
    fig = px.line(
        df,
        x="Date",
        y="Amount",
        color="Category",
        title="Monthly Spending by Subcategory",
    )
    return fig


def plot_single_category_by_month_plotly(
    transaction_data, category: str = "Shopping"
) -> plotly.graph_objs.Figure:
    df = transaction_data
    df = df[df["Category"] == category]
    df["Date"] = pd.to_datetime(df["Date"]).dt.to_period("M").astype(str)
    df = df.groupby(["Date"])["Amount"].sum().reset_index()
    fig = px.bar(df, x="Date", y="Amount", title=f"Monthly Spending by {category}")
    return fig


def plot_single_category_by_month(
    df: pd.DataFrame, category: str = "Groceries"
) -> None:
    groceries = single_category(df, category)
    groceries["month_year"] = groceries["Date"].dt.to_period("M")
    df_grouped = groceries.groupby("month_year")["Amount"].sum()

    # Plot a histogram
    fig, ax = plt.subplots(figsize=(10, 6))
    df_grouped.plot(kind="bar", ax=ax)
    ax.set_xlabel("Month")
    ax.set_ylabel("Total Amount")
    ax.set_title("Total Amount by Month")
    return fig


def plot_categories_per_month(
    transaction_data: pd.DataFrame, skip_categories: list[str] | None = None
) -> plotly.graph_objs.Figure:
    df = _to_spending(transaction_data)
    if skip_categories:
        df = df[~df["Category"].isin(skip_categories)]

    df["Date"] = pd.to_datetime(df["Date"]).dt.to_period("M").astype(str)

    df = df.groupby(["Date", "Category"])["Amount"].sum().reset_index()
    fig = px.bar(
        df, x="Date", y="Amount", color="Category", title="Monthly Spending by Category"
    )
    return fig


def plot_total_spending_per_month(
    transaction_data: pd.DataFrame, skip_categories: list[str] | None = None
) -> plotly.graph_objs.Figure:
    df = _to_spending(transaction_data)
    if skip_categories:
        df = df[~df["Category"].isin(skip_categories)]
    df["Date"] = pd.to_datetime(df["Date"]).dt.to_period("M").astype(str)
    df = df.groupby("Date")["Amount"].sum().reset_index()
    fig = px.bar(df, x="Date", y="Amount", title="Monthly Spending")
    return fig
