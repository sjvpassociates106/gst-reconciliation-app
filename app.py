import streamlit as st
import pandas as pd

st.set_page_config(page_title="Enterprise GST Reconciliation", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])


# ---------------------------------------
# LOAD ONLY B2B SHEET FROM GSTR-2B FILE
# ---------------------------------------

def load_b2b_sheet(file):
    excel = pd.ExcelFile(file)

    for sheet in excel.sheet_names:
        if sheet.strip().lower() == "b2b":
            return excel.parse(sheet)

    st.error("B2B sheet not found in GSTR-2B file.")
    st.write("Available sheets:", excel.sheet_names)
    st.stop()


if gstr2b_file and purchase_file:

    # Load correct sheets
    gstr2b = load_b2b_sheet(gstr2b_file)
    purchase = pd.read_excel(purchase_file)

    gstr2b.columns = gstr2b.columns.str.strip()
    purchase.columns = purchase.columns.str.strip()

    # ---------------------------------------
    # SELECT ONLY REQUIRED COLUMNS
    # ---------------------------------------

    required_2b = [
        "GSTIN of supplier",
        "Trade/Legal name",
        "Invoice number",
        "Invoice Date",
        "Taxable Value (₹)",
        "Integrated Tax(₹)",
        "Central Tax(₹)",
        "State/UT Tax(₹)"
    ]

    required_pr = [
        "GSTIN/UIN",
        "Particulars",
        "Supplier Invoice No.",
        "Date",
        "Taxable Amount",
        "IGST",
        "CGST",
        "SGST"
    ]

    # Check existence
    for col in required_2b:
        if col not in gstr2b.columns:
            st.error(f"Column missing in 2B: {col}")
            st.write(gstr2b.columns)
            st.stop()

    for col in required_pr:
        if col not in purchase.columns:
            st.error(f"Column missing in Purchase Register: {col}")
            st.write(purchase.columns)
            st.stop()

    # ---------------------------------------
    # CLEAN & RENAME
    # ---------------------------------------

    df_2b = gstr2b[required_2b].copy()
    df_pr = purchase[required_pr].copy()

    df_2b.columns = [
        "GSTIN", "Party", "Invoice", "Date",
        "Taxable_2B", "IGST_2B", "CGST_2B", "SGST_2B"
    ]

    df_pr.columns = [
        "GSTIN", "Party", "Invoice", "Date",
        "Taxable_PR", "IGST_PR", "CGST_PR", "SGST_PR"
    ]

    # Clean key fields
    df_2b["Invoice"] = df_2b["Invoice"].astype(str).str.strip().str.upper()
    df_pr["Invoice"] = df_pr["Invoice"].astype(str).str.strip().str.upper()

    df_2b["GSTIN"] = df_2b["GSTIN"].astype(str).str.strip()
    df_pr["GSTIN"] = df_pr["GSTIN"].astype(str).str.strip()

    # Convert numeric fields
    for col in ["Taxable_2B", "IGST_2B", "CGST_2B", "SGST_2B"]:
        df_2b[col] = pd.to_numeric(df_2b[col], errors="coerce").fillna(0)

    for col in ["Taxable_PR", "IGST_PR", "CGST_PR", "SGST_PR"]:
        df_pr[col] = pd.to_numeric(df_pr[col], errors="coerce").fillna(0)

    # ---------------------------------------
    # MERGE
    # ---------------------------------------

    recon = pd.merge(
        df_pr,
        df_2b,
        on=["GSTIN", "Invoice"],
        how="outer",
        indicator=True
    )

    # Differences
    recon["Taxable_Diff"] = recon["Taxable_PR"] - recon["Taxable_2B"]
    recon["IGST_Diff"] = recon["IGST_PR"] - recon["IGST_2B"]
    recon["CGST_Diff"] = recon["CGST_PR"] - recon["CGST_2B"]
    recon["SGST_Diff"] = recon["SGST_PR"] - recon["SGST_2B"]

    # Status
    def classify(row):
        if row["_merge"] == "both":
            if row["Taxable_Diff"] != 0 or row["IGST_Diff"] != 0 \
               or row["CGST_Diff"] != 0 or row["SGST_Diff"] != 0:
                return "Tax Mismatch"
            return "Matched"
        elif row["_merge"] == "left_only":
            return "Missing in 2B"
        else:
            return "Missing in Purchase"

    recon["Status"] = recon.apply(classify, axis=1)

    # ---------------------------------------
    # OUTPUT
    # ---------------------------------------

    st.subheader("Reconciliation Summary")

    col1, col2, col3 = st.columns(3)
    col1.metric("Matched", (recon["Status"] == "Matched").sum())
    col2.metric("Tax Mismatch", (recon["Status"] == "Tax Mismatch").sum())
    col3.metric("Missing in 2B", (recon["Status"] == "Missing in 2B").sum())

    st.subheader("Detailed Reconciliation")
    st.dataframe(recon, use_container_width=True)

    st.download_button(
        "Download Reconciliation Report",
        data=recon.to_csv(index=False),
        file_name="GST_Reconciliation_Report.csv",
        mime="text/csv"
    )
