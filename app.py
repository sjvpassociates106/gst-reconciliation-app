import streamlit as st
import pandas as pd

st.set_page_config(page_title="Enterprise GST Reconciliation", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])


# ---------------------------
# LOAD B2B SHEET FROM 2B
# ---------------------------

def load_gstr2b(file):
    excel = pd.ExcelFile(file)

    # Try to find B2B sheet automatically
    for sheet in excel.sheet_names:
        if "b2b" in sheet.lower():
            df = excel.parse(sheet)
            return df

    # If not found, use first sheet
    return excel.parse(excel.sheet_names[0])


if gstr2b_file and purchase_file:

    # Load files
    gstr2b = load_gstr2b(gstr2b_file)
    purchase = pd.read_excel(purchase_file)

    # Clean column names
    gstr2b.columns = gstr2b.columns.str.strip()
    purchase.columns = purchase.columns.str.strip()

    # ---------------------------
    # SELECT REQUIRED COLUMNS
    # ---------------------------

    # GSTR-2B columns
    gstr2b = gstr2b[[
        "GSTIN of supplier",
        "Trade/Legal name",
        "Invoice number",
        "Invoice Date",
        "Taxable Value (₹)",
        "Integrated Tax(₹)",
        "Central Tax(₹)",
        "State/UT Tax(₹)"
    ]]

    # Rename for simplicity
    gstr2b.columns = [
        "GSTIN",
        "Party Name",
        "Invoice No",
        "Date",
        "Taxable_2B",
        "IGST_2B",
        "CGST_2B",
        "SGST_2B"
    ]

    # Purchase columns
    purchase = purchase[[
        "GSTIN/UIN",
        "Particulars",
        "Supplier Invoice No.",
        "Date",
        "Taxable Amount",
        "IGST",
        "CGST",
        "SGST"
    ]]

    purchase.columns = [
        "GSTIN",
        "Party Name",
        "Invoice No",
        "Date",
        "Taxable_PR",
        "IGST_PR",
        "CGST_PR",
        "SGST_PR"
    ]

    # ---------------------------
    # CLEAN DATA
    # ---------------------------

    gstr2b["Invoice No"] = gstr2b["Invoice No"].astype(str).str.strip().str.upper()
    purchase["Invoice No"] = purchase["Invoice No"].astype(str).str.strip().str.upper()

    gstr2b["GSTIN"] = gstr2b["GSTIN"].astype(str).str.strip()
    purchase["GSTIN"] = purchase["GSTIN"].astype(str).str.strip()

    for col in ["Taxable_2B", "IGST_2B", "CGST_2B", "SGST_2B"]:
        gstr2b[col] = pd.to_numeric(gstr2b[col], errors="coerce").fillna(0)

    for col in ["Taxable_PR", "IGST_PR", "CGST_PR", "SGST_PR"]:
        purchase[col] = pd.to_numeric(purchase[col], errors="coerce").fillna(0)

    # ---------------------------
    # MERGE
    # ---------------------------

    recon = pd.merge(
        purchase,
        gstr2b,
        on=["GSTIN", "Invoice No"],
        how="outer",
        indicator=True
    )

    # ---------------------------
    # DIFFERENCE CALCULATION
    # ---------------------------

    recon["Taxable_Diff"] = recon["Taxable_PR"] - recon["Taxable_2B"]
    recon["IGST_Diff"] = recon["IGST_PR"] - recon["IGST_2B"]
    recon["CGST_Diff"] = recon["CGST_PR"] - recon["CGST_2B"]
    recon["SGST_Diff"] = recon["SGST_PR"] - recon["SGST_2B"]

    # ---------------------------
    # STATUS
    # ---------------------------

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

    # ---------------------------
    # SUMMARY
    # ---------------------------

    st.subheader("Summary")

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
