import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST 2B Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# -----------------------------
# Clean Invoice Number
# -----------------------------
def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    inv = str(inv)

    nums = re.findall(r'\d+', inv)

    if len(nums) == 0:
        return ""

    return nums[0]


# -----------------------------
# Safe Numeric Conversion
# -----------------------------
def num(col):

    return pd.to_numeric(col, errors="coerce").fillna(0)


# =============================
# PROCESS
# =============================
if gstr_file and purchase_file:

    # -----------------------------
    # Load GSTR-2B
    # -----------------------------

    gstr2b = pd.read_excel(gstr_file, sheet_name="B2B", header=3)

    gstr2b = gstr2b[[
        "GSTIN of supplier",
        "Trade/Legal name",
        "Invoice number",
        "Invoice Date",
        "Taxable Value",
        "Integrated Tax(₹)",
        "Central Tax(₹)",
        "State/UT Tax(₹)"
    ]]

    gstr2b.columns = [
        "GSTIN",
        "Party",
        "Invoice",
        "Date",
        "Taxable2B",
        "IGST2B",
        "CGST2B",
        "SGST2B"
    ]

    gstr2b["GSTIN"] = gstr2b["GSTIN"].astype(str).str.strip().str.upper()
    gstr2b["Invoice"] = gstr2b["Invoice"].apply(clean_invoice)

    gstr2b["IGST2B"] = num(gstr2b["IGST2B"])
    gstr2b["CGST2B"] = num(gstr2b["CGST2B"])
    gstr2b["SGST2B"] = num(gstr2b["SGST2B"])


    # -----------------------------
    # Load Purchase Register
    # -----------------------------

    purchase = pd.read_excel(purchase_file)

    purchase = purchase[[
        "Date",
        "Particular",
        "Supplier Invoice Number",
        "GSTiN/UIN",
        "Taxable Value",
        "IGST",
        "CGST",
        "SGST"
    ]]

    purchase.columns = [
        "Date",
        "Party",
        "Invoice",
        "GSTIN",
        "TaxablePR",
        "IGSTPR",
        "CGSTPR",
        "SGSTPR"
    ]

    purchase["GSTIN"] = purchase["GSTIN"].astype(str).str.strip().str.upper()
    purchase["Invoice"] = purchase["Invoice"].apply(clean_invoice)

    purchase["IGSTPR"] = num(purchase["IGSTPR"])
    purchase["CGSTPR"] = num(purchase["CGSTPR"])
    purchase["SGSTPR"] = num(purchase["SGSTPR"])


    # -----------------------------
    # Remove blank invoices
    # -----------------------------

    gstr2b = gstr2b[gstr2b["Invoice"]!=""]
    purchase = purchase[purchase["Invoice"]!=""]


    # -----------------------------
    # Merge Data
    # -----------------------------

    recon = pd.merge(
        purchase,
        gstr2b,
        on=["GSTIN","Invoice"],
        how="outer",
        indicator=True
    )


    # -----------------------------
    # Reconciliation Logic
    # -----------------------------

    def check(row):

        if row["_merge"] == "left_only":
            return pd.Series(["Mismatch","Missing in GSTR2B"])

        if row["_merge"] == "right_only":
            return pd.Series(["Mismatch","Missing in Purchase Register"])

        reasons = []

        if round(row["IGSTPR"],2) != round(row["IGST2B"],2):
            reasons.append("IGST Difference")

        if round(row["CGSTPR"],2) != round(row["CGST2B"],2):
            reasons.append("CGST Difference")

        if round(row["SGSTPR"],2) != round(row["SGST2B"],2):
            reasons.append("SGST Difference")

        if len(reasons) == 0:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]] = recon.apply(check, axis=1)

    recon = recon.drop(columns=["_merge"])


    # -----------------------------
    # Dashboard
    # -----------------------------

    st.subheader("Summary")

    c1,c2,c3 = st.columns(3)

    c1.metric("Total Records",len(recon))
    c2.metric("Matched",(recon["Status"]=="Matched").sum())
    c3.metric("Mismatch",(recon["Status"]=="Mismatch").sum())


    # -----------------------------
    # Result Table
    # -----------------------------

    st.subheader("Reconciliation Result")

    st.dataframe(recon,use_container_width=True)


    # -----------------------------
    # Excel Download
    # -----------------------------

    buffer = BytesIO()

    recon.to_excel(buffer,index=False)

    st.download_button(
        "Download Excel Report",
        buffer.getvalue(),
        "GST_Reconciliation_Report.xlsx"
    )
