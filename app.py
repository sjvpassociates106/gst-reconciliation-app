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

    # Clean column names (remove extra spaces)
    gstr2b.columns = gstr2b.columns.str.strip()
    purchase.columns = purchase.columns.str.strip()

    # Exact column names from your Excel
    invoice_col = "Supplier Invoice No."
    gstin_col = "GSTIN"

    # Check required columns exist
    if invoice_col not in gstr2b.columns or invoice_col not in purchase.columns:
        st.error("Supplier Invoice No. column not found in one of the files.")
        st.write("GSTR2B Columns:", list(gstr2b.columns))
        st.write("Purchase Columns:", list(purchase.columns))
        st.stop()

    if gstin_col not in gstr2b.columns or gstin_col not in purchase.columns:
        st.error("GSTIN column not found in one of the files.")
        st.stop()

    # Clean values
    gstr2b[invoice_col] = gstr2b[invoice_col].astype(str).str.strip().str.upper()
    purchase[invoice_col] = purchase[invoice_col].astype(str).str.strip().str.upper()

    gstr2b[gstin_col] = gstr2b[gstin_col].astype(str).str.strip()
    purchase[gstin_col] = purchase[gstin_col].astype(str).str.strip()

    # Merge
    recon = pd.merge(
        purchase,
        gstr2b,
        on=[gstin_col, invoice_col],
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
