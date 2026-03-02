import streamlit as st
import pandas as pd

st.set_page_config(page_title="GST Reconciliation System", layout="wide")

st.title("Enterprise GST Reconciliation System")

st.markdown("Upload GSTR-2B and Purchase Register files")

gstr2b_file = st.file_uploader("Upload GSTR 2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])

if gstr2b_file and purchase_file:

    gstr2b = pd.read_excel(gstr2b_file)
    purchase = pd.read_excel(purchase_file)

    gstr2b.columns = gstr2b.columns.str.strip()
    purchase.columns = purchase.columns.str.strip()

    try:
        gstr2b["Invoice No"] = gstr2b["Invoice No"].astype(str).str.strip().str.upper()
        purchase["Bill No"] = purchase["Bill No"].astype(str).str.strip().str.upper()

        gstr2b["GSTIN"] = gstr2b["GSTIN"].astype(str).str.strip()
        purchase["Supplier GSTIN"] = purchase["Supplier GSTIN"].astype(str).str.strip()

        recon = pd.merge(
            purchase,
            gstr2b,
            left_on=["Supplier GSTIN", "Bill No"],
            right_on=["GSTIN", "Invoice No"],
            how="outer",
            indicator=True
        )

        def classify(row):
            if row["_merge"] == "both":
                return "Matched"
            elif row["_merge"] == "left_only":
                return "In Purchase Not in 2B"
            else:
                return "In 2B Not in Purchase"

        recon["Status"] = recon.apply(classify, axis=1)

        st.success("Reconciliation Completed")

        st.dataframe(recon, use_container_width=True)

        st.download_button(
            label="Download Reconciliation Report",
            data=recon.to_csv(index=False),
            file_name="GST_Reconciliation_Report.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error(f"Column mismatch error: {e}")
