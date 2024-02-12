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


def get_balance_history() -> pd.DataFrame:
    df = sheet_as_df("Balance History")
    df["Balance"] = df.Balance.str.replace(",", "").str.replace("$", "").astype(float)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


def resampled_balance_history(df: pd.DataFrame) -> pd.DataFrame:
    # Resolve duplicates by taking the last snapshot for each day for each account
    df_ = df.drop_duplicates(subset=["Account ID", "Date"], keep="last")

    # Sort by 'Account ID' and 'Date'
    df_ = df_.sort_values(by=["Account ID", "Date"])

    # Extend the DataFrame to include the current date for each account
    current_date = pd.to_datetime("today").normalize()  # Normalize to remove time
    idx = pd.date_range(start=df_["Date"].min(), end=current_date, freq="D")
    df_ = df_.set_index("Date")

    # Function to process each group
    def process_group(group):
        group = group.reindex(idx)  # Reindex without filling
        # Forward fill the non-balance columns if there are any
        non_balance_columns = group.drop(columns=["Balance"]).columns
        group[non_balance_columns] = (
            group[non_balance_columns].infer_objects(copy=False).ffill().bfill()
        )
        # Interpolate the 'Balance' column
        group["Balance"] = group["Balance"].interpolate(
            method="linear", limit_direction="forward"
        )
        group["Balance"] = group["Balance"].fillna(0)
        return group

    # Apply the function to each account group
    df_processed = df_.groupby("Account ID", group_keys=True).apply(
        process_group, include_groups=False
    )

    # Reset index to bring 'Date' back as a column
    df_processed.reset_index(inplace=True)
    df_processed["Date"] = df_processed.pop("level_1")
    return df_processed


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


def plot_monthly_total_and_account_balances(
    balance_data: pd.DataFrame, skip_accounts: list[str] | None = None
) -> plotly.graph_objs.Figure:
    balance_data = balance_data[balance_data["Balance"] >= 0]
    if skip_accounts:
        balance_data = balance_data[~balance_data["Account"].isin(skip_accounts)]

    # Convert date to month and ensure it's in a suitable format for grouping
    balance_data["Month"] = (
        pd.to_datetime(balance_data["Date"]).dt.to_period("M").astype(str)
    )

    # Group by month and account, summing balances
    df = balance_data.groupby(["Month", "Account"])["Balance"].first().reset_index()

    # Plot using Plotly Express
    fig = px.bar(
        df,
        x="Month",
        y="Balance",
        color="Account",
        title="Monthly Total and Account Balances",
        labels={"Balance": "Total Balance", "Month": "Month", "Account": "Account"},
        text="Balance",
    )

    # Make the bars stacked
    fig.update_layout(
        barmode="stack",
        xaxis_tickangle=-45,
        xaxis_title="Month",
        yaxis_title="Total Balance",
        xaxis=dict(type="category"),
        yaxis=dict(type="linear"),
    )

    # Optional: Format the balance text on the bars for better readability
    fig.update_traces(texttemplate="%{text:.2s}", textposition="inside")

    return fig


def plot_net_worth_over_time(df_resampled_balance_history: pd.DataFrame) -> px.line:
    net_worth_over_time = (
        df_resampled_balance_history.groupby("Date")["Balance"].sum().reset_index()
    )

    fig = px.line(
        net_worth_over_time,  # Data
        x="Date",  # X-axis
        y="Balance",  # Y-axis
        title="Net Worth Over Time",
        labels={"Balance": "Net Worth", "Date": "Date"},  # Customizing axis labels
    )

    # Customize the layout
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Net Worth",
        xaxis=dict(tickangle=-45),  # Rotate labels for better readability
        yaxis=dict(range=[0, net_worth_over_time["Balance"].max() * 1.1]),
    )

    # Adding grid lines for better readability, similar to plt.grid(True) in matplotlib
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="lightgrey")
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="lightgrey")

    return fig
