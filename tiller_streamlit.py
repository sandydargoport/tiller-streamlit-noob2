import os

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import plotly
import plotly.express as px
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import altair as alt

load_dotenv()

SERVICE_ACCOUNT_FILE = os.environ["SERVICE_ACCOUNT_FILE"]
SCOPES = os.environ["SCOPES"].split(",")
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]


def get_sheet(range: str) -> dict:
    credentials = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=credentials)
    sheet = service.spreadsheets()  # Call the Sheets API
    return sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range).execute()


def sheet_as_df(range: str) -> pd.DataFrame:
    values = get_sheet(range)["values"]
    return pd.DataFrame(values[1:], columns=values[0])


def get_categories() -> tuple[dict[str, str], dict[str, list[str]]]:
    df = sheet_as_df("Categories")
    category_to_group: dict[str, str] = {}
    group_to_category: dict[str, list[str]] = {}
    for i, row in df.iterrows():
        category_to_group[row.Category] = row.Group
        group_to_category.setdefault(row.Group, []).append(row.Category)
    return category_to_group, group_to_category


def _add_category_group(transaction_data: pd.DataFrame) -> pd.DataFrame:
    category_to_group, group_to_category = get_categories()
    transaction_data["Group"] = transaction_data["Category"].apply(
        lambda x: category_to_group.get(x, "")
    )
    return transaction_data


def get_transaction_data_df() -> pd.DataFrame:
    df = sheet_as_df("Transactions")
    df["Date"] = pd.to_datetime(df["Date"])
    df["Amount"] = df["Amount"].apply(clean_amount)
    _add_per_category_amount(df)
    _add_category_group(df)
    df["month_year"] = df["Date"].dt.to_period("M")
    return df


def clean_amount(x: str) -> float:
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
    total = df["Amount"].sum()
    df["amount_category_pct"] = df["amount_category"] / total * 100
    df["Amount"] = -df["Amount"]
    return df


def plot_categories(
    transaction_data: pd.DataFrame,
    month: int | None = None,
    year: int | None = None,
    with_group: bool = False,
) -> plotly.graph_objs.Figure:
    df = _to_spending(transaction_data)
    if month is not None:
        df = df[df["Date"].dt.month == month]
    if year is not None:
        df = df[df["Date"].dt.year == year]
    df["Percent"] = df["amount_category_pct"].apply(lambda x: f"{x:.2f}%")
    path = ["Category"] if not with_group else ["Group", "Category"]
    return px.sunburst(
        df,
        path=path,
        values="Amount",
        hover_data=["Amount", "Percent"],
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
) -> matplotlib.figure.Figure:
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


def plot_comparative_spending(df: pd.DataFrame, n_last_months: int = 3) -> alt.Chart:
    df = df[df["Category"] != "Paycheck"]
    df = df[df["Category"] != "Investments in Stocks"]
    df = df[df["Category"] != "Investments in Crypto"]
    df["Amount"] = -df["Amount"]

    df_ = df.groupby(df["Date"].dt.date)["Amount"].sum().reset_index()
    df_["Date"] = pd.to_datetime(df_["Date"])
    df_["day"] = df_["Date"].dt.day
    df_["cumsum"] = df_.groupby(df_["Date"].dt.to_period("M"))["Amount"].cumsum()

    most_recent_month = df_["Date"].dt.to_period("M").max()
    df_["Relative Month"] = (most_recent_month - df_["Date"].dt.to_period("M")).apply(
        lambda x: f"{x.n} months ago"
    )
    df_["Relative Month"] += ", " + df_["Date"].dt.strftime("%Y-%m")
    this_month_str = f"This Month, {most_recent_month.strftime('%Y-%m')}"
    df_.loc[
        df_["Relative Month"].str.contains("0 months ago"), "Relative Month"
    ] = this_month_str
    df_ = df_[df_["Date"] >= df_["Date"].max() - pd.DateOffset(months=n_last_months)]

    chart = (
        alt.Chart(df_[["day", "cumsum", "Relative Month"]])
        .mark_line(point=True)
        .encode(
            x="day:Q",
            y="cumsum:Q",
            color=alt.Color(
                "Relative Month:N", legend=alt.Legend(title="Relative Month")
            ),
            tooltip=["day", "cumsum", "Relative Month"],
            strokeDash=alt.condition(
                alt.datum["Relative Month"] == this_month_str,
                alt.value([0]),  # solid line for current month
                alt.value([5, 5]),  # dashed line for previous months
            ),
            opacity=alt.condition(
                alt.datum["Relative Month"] == this_month_str,
                alt.value(1),  # full opacity for current month
                alt.value(0.5),  # half opacity for previous months
            ),
        )
        .properties(
            title="Cumulative Spending Per Day Over the Last N Months",
            width=600,
            height=400,
        )
    )
    return chart
