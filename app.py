# File: app.py

import streamlit as st
from tiller_streamlit import (
    get_transaction_data_df,
    plot_categories_per_month,
    plot_total_spending_per_month,
    plot_category_histogram,
    plot_categories,
    plot_spending_per_subcategory,
    plot_single_category_by_month_plotly,
    plot_monthly_income,
    plot_comparative_spending,
    get_balance_history,
    resampled_balance_history,
    plot_net_worth_over_time,
    plot_monthly_total_and_account_balances,
)


def toc(headers):
    # Iterate over existing headers and create a TOC
    st.sidebar.title("Table of contents")
    st.sidebar.markdown(
        "\n".join([f"- [{i}](#{i.lower().replace(' ', '-')})" for i in headers])
    )


def main():
    st.title("Tiller Money Streamlit App")

    headers = []

    def header(s):
        headers.append(s)
        st.header(s)

    transaction_data = get_transaction_data_df()
    categories = sorted(transaction_data["Category"].unique())

    header("Net worth over time")
    df_balance_history = get_balance_history()
    df_nw = resampled_balance_history(df_balance_history)
    fig = plot_monthly_total_and_account_balances(df_nw)
    st.plotly_chart(fig)

    fig = plot_net_worth_over_time(df_nw)
    st.plotly_chart(fig)

    header("Monthly Comparative Spending")
    months_to_compare = st.selectbox(
        "Compare with previous n months:", [1, 2, 3, 4, 5, 6], index=2
    )
    fig = plot_comparative_spending(transaction_data, months_to_compare)
    st.altair_chart(fig)

    # Allow users to exclude certain categories
    skip_categories = st.multiselect("Exclude categories", categories, default=["Rent"])

    # Checkbox to enable moving average
    enable_ma = st.checkbox("Add moving average to each category")

    # Initialize moving average variable
    n_months_ma = None

    if enable_ma:
        # Number input for specifying 'N months moving average'
        n_months_ma = st.number_input(
            "Number of months for moving average",
            min_value=2,
            max_value=12,
            value=3,
            step=1,
            help="Select the number of months for calculating the moving average.",
        )

    # Pass the moving average parameter to the plotting function
    fig = plot_categories_per_month(
        transaction_data,
        skip_categories=skip_categories,
        n_months_ma=n_months_ma,  # Ensure this parameter is passed
    )

    st.plotly_chart(fig)

    header("Monthly Spending")
    skip_categories = st.multiselect(
        "Exclude categories from spending", categories, default=["Rent"]
    )
    fig = plot_total_spending_per_month(
        transaction_data,
        skip_categories=skip_categories,
        n_months_moving_avg=[3, 6, 12],
    )
    st.plotly_chart(fig)

    header("Histogram of amount per category")
    category = st.selectbox(
        "Select a category", categories, index=categories.index("Shopping")
    )
    fig = plot_category_histogram(transaction_data, category)
    st.plotly_chart(fig)

    header("Spending by Subcategory")
    category = st.selectbox(
        "Select a category", categories, index=categories.index("Shopping"), key=0
    )
    fig = plot_single_category_by_month_plotly(transaction_data, category)
    st.plotly_chart(fig)
    fig = plot_spending_per_subcategory(transaction_data)
    st.plotly_chart(fig)

    header("Monthly Income")
    fig = plot_monthly_income(transaction_data)
    st.plotly_chart(fig)

    header("Total Spending Pie Chart")
    year = st.selectbox(
        "Select a year",
        [None] + sorted(transaction_data["Date"].dt.year.unique(), reverse=True),
    )
    month = st.selectbox("Select a month", [None] + list(range(1, 13)))
    with_group = st.checkbox("Group by category", value=False)
    fig = plot_categories(transaction_data, month, year, with_group=with_group)
    st.plotly_chart(fig)

    toc(headers)


if __name__ == "__main__":
    main()
