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

    header("Monthly Comparative Spending")
    months_to_compare = st.selectbox(
        "Compare with previous n months:", [1, 2, 3, 4, 5, 6], index=2
    )
    fig = plot_comparative_spending(transaction_data, months_to_compare)
    st.altair_chart(fig)

    header("Monthly Spending by Category")
    skip_categories = st.multiselect("Exclude categories", categories, default=["Rent"])
    fig = plot_categories_per_month(transaction_data, skip_categories=skip_categories)
    st.plotly_chart(fig)

    header("Monthly Spending")
    skip_categories = st.multiselect(
        "Exclude categories from spending", categories, default=["Rent"]
    )
    fig = plot_total_spending_per_month(
        transaction_data, skip_categories=skip_categories
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
