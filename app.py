import streamlit as st
import pandas as pd

st.set_page_config(page_title="GST Reconciliation System", layout="wide")

st.title("Enterprise GST Reconciliation System")

st.markdown("Upload GSTR-2B and Purchase Register files")

gstr2b_file = st.file_uploader("Upload GSTR 2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])

if gstr2b_file and purchase_file:

    # Load files
    gstr2b = pd.read_excel(gstr2b_file)
    purchase = pd.read_excel(purchase_file)

    # Clean column names
    gstr2b.columns = gstr2b.columns.str.strip()
    purchase.columns = purchase.columns.str.strip()

    # -------------------------
    # SMART COLUMN DETECTION
    # -------------------------

    def find_column(columns, possible_names):
        for col in columns:
            if col.strip().lower() in possible_names:
                return col
        return None

    invoice_col_2b = find_column(gstr2b.columns, ["invoice no", "invoice number", "inv no", "document no"])
    invoice_col_pr = find_column(purchase.columns, ["bill no", "invoice no", "invoice number"])
    gstin_col_2b = find_column(gstr2b.columns, ["gstin"])
    gstin_col_pr = find_column(purchase.columns, ["supplier gstin", "gstin"])

    if not invoice_col_2b or not invoice_col_pr or not gstin_col_2b or not gstin_col_pr:
        st.error("Required columns not found.")
        st.write("GSTR2B Columns:", list(gstr2b.columns))
        st.write("Purchase Columns:", list(purchase.columns))
        st.stop()

    # Clean values
    gstr2b[invoice_col_2b] = gstr2b[invoice_col_2b].astype(str).str.strip().str.upper()
    purchase[invoice_col_pr] = purchase[invoice_col_pr].astype(str).str.strip().str.upper()
    gstr2b[gstin_col_2b] = gstr2b[gstin_col_2b].astype(str).str.strip()
    purchase[gstin_col_pr] = purchase[gstin_col_pr].astype(str).str.strip()

    # Merge
    recon = pd.merge(
        purchase,
        gstr2b,
        left_on=[gstin_col_pr, invoice_col_pr],
        right_on=[gstin_col_2b, invoice_col_2b],
        how="outer",
        indicator=True
    )

    # Status
    def classify(row):
        if row["_merge"] == "both":
            return "Matched"
        elif row["_merge"] == "left_only":
            return "In Purchase Not in 2B"
        else:
            return "In 2B Not in Purchase"

    recon["Status"] = recon.apply(classify, axis=1)

    st.success("Reconciliation Completed Successfully")

    st.dataframe(recon, use_container_width=True)

    st.download_button(
        label="Download Reconciliation Report",
        data=recon.to_csv(index=False),
        file_name="GST_Reconciliation_Report.csv",
        mime="text/csv"
    )
