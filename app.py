import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Enterprise GST Reconciliation", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR 2B File", type=["xlsx", "xls"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx", "xls"])


# ----------------------------
# AUTO HEADER DETECTION
# ----------------------------

def load_with_auto_header(file):
    temp_df = pd.read_excel(file, header=None)

    for i in range(10):  # Check first 10 rows
        row_values = temp_df.iloc[i].astype(str).str.lower()
        if row_values.str.contains("gstin").any() or row_values.str.contains("invoice").any():
            return pd.read_excel(file, header=i)

    return pd.read_excel(file)  # fallback


# ----------------------------
# AUTO COLUMN DETECTION
# ----------------------------

def detect_column(columns, keywords):
    for col in columns:
        clean_col = col.lower().replace(" ", "").replace(".", "")
        for key in keywords:
            if key in clean_col:
                return col
    return None


if gstr2b_file and purchase_file:

    # Load with auto header detection
    gstr2b = load_with_auto_header(gstr2b_file)
    purchase = load_with_auto_header(purchase_file)

    gstr2b.columns = gstr2b.columns.astype(str).str.strip()
    purchase.columns = purchase.columns.astype(str).str.strip()

    # Detect important columns
    gstin_2b = detect_column(gstr2b.columns, ["gstin"])
    invoice_2b = detect_column(gstr2b.columns, ["invoice"])
    date_2b = detect_column(gstr2b.columns, ["date"])
    igst_2b = detect_column(gstr2b.columns, ["igst", "integrated"])
    cgst_2b = detect_column(gstr2b.columns, ["cgst"])
    sgst_2b = detect_column(gstr2b.columns, ["sgst"])

    gstin_pr = detect_column(purchase.columns, ["gstin"])
    invoice_pr = detect_column(purchase.columns, ["invoice"])
    date_pr = detect_column(purchase.columns, ["date"])
    igst_pr = detect_column(purchase.columns, ["igst"])
    cgst_pr = detect_column(purchase.columns, ["cgst"])
    sgst_pr = detect_column(purchase.columns, ["sgst"])

    required = [gstin_2b, invoice_2b, gstin_pr, invoice_pr]

    if any(col is None for col in required):
        st.error("Required columns not detected automatically.")
        st.write("2B Columns:", list(gstr2b.columns))
        st.write("Purchase Columns:", list(purchase.columns))
        st.stop()

    # Clean key fields
    gstr2b[invoice_2b] = gstr2b[invoice_2b].astype(str).str.strip().str.upper()
    purchase[invoice_pr] = purchase[invoice_pr].astype(str).str.strip().str.upper()

    gstr2b[gstin_2b] = gstr2b[gstin_2b].astype(str).str.strip()
    purchase[gstin_pr] = purchase[gstin_pr].astype(str).str.strip()

    # Convert tax fields
    for col in [igst_2b, cgst_2b, sgst_2b]:
        if col:
            gstr2b[col] = pd.to_numeric(gstr2b[col], errors="coerce").fillna(0)

    for col in [igst_pr, cgst_pr, sgst_pr]:
        if col:
            purchase[col] = pd.to_numeric(purchase[col], errors="coerce").fillna(0)

    # Merge
    recon = pd.merge(
        purchase,
        gstr2b,
        left_on=[gstin_pr, invoice_pr],
        right_on=[gstin_2b, invoice_2b],
        how="outer",
        indicator=True,
        suffixes=("_PR", "_2B")
    )

    # Difference Calculation
    def diff(col_pr, col_2b):
        if col_pr and col_2b:
            return recon[col_pr + "_PR"] - recon[col_2b + "_2B"]
        return 0

    if igst_pr and igst_2b:
        recon["IGST_Diff"] = diff(igst_pr, igst_2b)

    if cgst_pr and cgst_2b:
        recon["CGST_Diff"] = diff(cgst_pr, cgst_2b)

    if sgst_pr and sgst_2b:
        recon["SGST_Diff"] = diff(sgst_pr, sgst_2b)

    # Status Logic
    def classify(row):
        if row["_merge"] == "both":
            if ("IGST_Diff" in row and row.get("IGST_Diff", 0) != 0) or \
               ("CGST_Diff" in row and row.get("CGST_Diff", 0) != 0) or \
               ("SGST_Diff" in row and row.get("SGST_Diff", 0) != 0):
                return "Tax Mismatch"
            return "Matched"
        elif row["_merge"] == "left_only":
            return "Missing in 2B"
        else:
            return "Missing in Purchase"

    recon["Status"] = recon.apply(classify, axis=1)

    # Summary
    st.subheader("Reconciliation Summary")

    col1, col2, col3 = st.columns(3)
    col1.metric("Matched", (recon["Status"] == "Matched").sum())
    col2.metric("Tax Mismatch", (recon["Status"] == "Tax Mismatch").sum())
    col3.metric("Missing in 2B", (recon["Status"] == "Missing in 2B").sum())

    st.subheader("Detailed Reconciliation")

    def highlight(val):
        if val == "Tax Mismatch":
            return "background-color: #ffcccc"
        if val == "Missing in 2B":
            return "background-color: #fff3cd"
        if val == "Missing in Purchase":
            return "background-color: #cce5ff"
        return ""

    st.dataframe(recon.style.applymap(highlight, subset=["Status"]), use_container_width=True)

    st.download_button(
        "Download Reconciliation Report",
        data=recon.to_csv(index=False),
        file_name="GST_Reconciliation_Report.csv",
        mime="text/csv"
    )
