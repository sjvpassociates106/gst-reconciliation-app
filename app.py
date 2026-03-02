import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Enterprise GST Reconciliation", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR 2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])


def auto_detect_column(columns, keywords):
    for col in columns:
        col_clean = col.lower().replace(" ", "")
        for key in keywords:
            if key in col_clean:
                return col
    return None


if gstr2b_file and purchase_file:

    gstr2b = pd.read_excel(gstr2b_file)
    purchase = pd.read_excel(purchase_file)

    gstr2b.columns = gstr2b.columns.str.strip()
    purchase.columns = purchase.columns.str.strip()

    # ----------------------------
    # AUTO DETECT COLUMNS
    # ----------------------------

    gstin_2b = auto_detect_column(gstr2b.columns, ["gstin"])
    invoice_2b = auto_detect_column(gstr2b.columns, ["invoice", "invoicenumber"])
    igst_2b = auto_detect_column(gstr2b.columns, ["integratedtax", "igst"])
    cgst_2b = auto_detect_column(gstr2b.columns, ["cgst"])
    sgst_2b = auto_detect_column(gstr2b.columns, ["sgst"])
    value_2b = auto_detect_column(gstr2b.columns, ["taxablevalue", "invoicevalue"])

    gstin_pr = auto_detect_column(purchase.columns, ["gstin"])
    invoice_pr = auto_detect_column(purchase.columns, ["supplierinvoiceno", "invoiceno"])
    igst_pr = auto_detect_column(purchase.columns, ["igst"])
    cgst_pr = auto_detect_column(purchase.columns, ["cgst"])
    sgst_pr = auto_detect_column(purchase.columns, ["sgst"])
    value_pr = auto_detect_column(purchase.columns, ["taxablevalue", "gross"])

    if not gstin_2b or not invoice_2b or not gstin_pr or not invoice_pr:
        st.error("Required columns not detected automatically.")
        st.write("2B Columns:", list(gstr2b.columns))
        st.write("Purchase Columns:", list(purchase.columns))
        st.stop()

    # ----------------------------
    # CLEAN DATA
    # ----------------------------

    gstr2b[invoice_2b] = gstr2b[invoice_2b].astype(str).str.strip().str.upper()
    purchase[invoice_pr] = purchase[invoice_pr].astype(str).str.strip().str.upper()

    gstr2b[gstin_2b] = gstr2b[gstin_2b].astype(str).str.strip()
    purchase[gstin_pr] = purchase[gstin_pr].astype(str).str.strip()

    # Fill tax columns
    for col in [igst_2b, cgst_2b, sgst_2b, value_2b]:
        if col:
            gstr2b[col] = pd.to_numeric(gstr2b[col], errors="coerce").fillna(0)

    for col in [igst_pr, cgst_pr, sgst_pr, value_pr]:
        if col:
            purchase[col] = pd.to_numeric(purchase[col], errors="coerce").fillna(0)

    # ----------------------------
    # MERGE
    # ----------------------------

    recon = pd.merge(
        purchase,
        gstr2b,
        left_on=[gstin_pr, invoice_pr],
        right_on=[gstin_2b, invoice_2b],
        how="outer",
        indicator=True,
        suffixes=("_PR", "_2B")
    )

    # ----------------------------
    # TAX DIFFERENCE
    # ----------------------------

    def calculate_difference(row, col_pr, col_2b):
        if col_pr and col_2b:
            return row.get(col_pr, 0) - row.get(col_2b, 0)
        return 0

    recon["IGST_Diff"] = recon.apply(lambda r: calculate_difference(r, igst_pr+"_PR", igst_2b+"_2B"), axis=1) if igst_pr and igst_2b else 0
    recon["CGST_Diff"] = recon.apply(lambda r: calculate_difference(r, cgst_pr+"_PR", cgst_2b+"_2B"), axis=1) if cgst_pr and cgst_2b else 0
    recon["SGST_Diff"] = recon.apply(lambda r: calculate_difference(r, sgst_pr+"_PR", sgst_2b+"_2B"), axis=1) if sgst_pr and sgst_2b else 0

    # ----------------------------
    # STATUS & REASON
    # ----------------------------

    def classify(row):
        if row["_merge"] == "both":
            if row["IGST_Diff"] != 0 or row["CGST_Diff"] != 0 or row["SGST_Diff"] != 0:
                return "Tax Mismatch"
            return "Matched"
        elif row["_merge"] == "left_only":
            return "Missing in 2B"
        else:
            return "Missing in Purchase"

    recon["Status"] = recon.apply(classify, axis=1)

    # ----------------------------
    # DISPLAY SUMMARY
    # ----------------------------

    st.subheader("Summary")

    col1, col2, col3 = st.columns(3)
    col1.metric("Matched", (recon["Status"] == "Matched").sum())
    col2.metric("Tax Mismatch", (recon["Status"] == "Tax Mismatch").sum())
    col3.metric("Missing In 2B", (recon["Status"] == "Missing in 2B").sum())

    st.subheader("Detailed Reconciliation")

    def highlight_status(val):
        if val == "Tax Mismatch":
            return "background-color: #ffcccc"
        elif val == "Missing in 2B":
            return "background-color: #fff3cd"
        elif val == "Missing in Purchase":
            return "background-color: #cce5ff"
        return ""

    st.dataframe(recon.style.applymap(highlight_status, subset=["Status"]), use_container_width=True)

    st.download_button(
        "Download Full Reconciliation Report",
        data=recon.to_csv(index=False),
        file_name="GST_Reconciliation_Enterprise_Report.csv",
        mime="text/csv"
    )
