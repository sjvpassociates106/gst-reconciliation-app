import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation Tool", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# -----------------------------
# Clean Invoice
# -----------------------------
def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    nums = re.findall(r"\d+", str(inv))

    if len(nums) == 0:
        return ""

    return nums[0]


# -----------------------------
# Find column by keyword
# -----------------------------
def find_col(cols, keyword):

    for c in cols:
        if keyword in c.lower():
            return c

    return None


# -----------------------------
# Numeric conversion
# -----------------------------
def num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


# =============================
# PROCESS
# =============================
if gstr_file and purchase_file:

    # -----------------------------
    # Load GSTR2B B2B Sheet
    # -----------------------------

    xl = pd.ExcelFile(gstr_file)

    gstr2b = xl.parse("B2B", header=3)

    gstr2b.columns = gstr2b.columns.astype(str).str.strip()

    gstin_col = find_col(gstr2b.columns, "gstin")
    party_col = find_col(gstr2b.columns, "trade")
    inv_col = find_col(gstr2b.columns, "invoice")
    tax_col = find_col(gstr2b.columns, "taxable")
    igst_col = find_col(gstr2b.columns, "integrated")
    cgst_col = find_col(gstr2b.columns, "central")
    sgst_col = find_col(gstr2b.columns, "state")

    if gstin_col is None or inv_col is None:
        st.error("Required columns not found in GSTR2B B2B sheet")
        st.write(gstr2b.columns)
        st.stop()

    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin_col].astype(str).str.upper().str.strip()
    df2b["Party"] = gstr2b[party_col]
    df2b["Invoice"] = gstr2b[inv_col].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[tax_col])
    df2b["IGST2B"] = num(gstr2b[igst_col])
    df2b["CGST2B"] = num(gstr2b[cgst_col])
    df2b["SGST2B"] = num(gstr2b[sgst_col])


    # -----------------------------
    # Load Purchase Register
    # -----------------------------

    purchase = pd.read_excel(purchase_file)

    purchase.columns = purchase.columns.astype(str).str.strip()

    gstin_pr = find_col(purchase.columns, "gst")
    party_pr = find_col(purchase.columns, "particular")
    inv_pr = find_col(purchase.columns, "invoice")
    tax_pr = find_col(purchase.columns, "taxable")
    igst_pr = find_col(purchase.columns, "igst")
    cgst_pr = find_col(purchase.columns, "cgst")
    sgst_pr = find_col(purchase.columns, "sgst")

    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstin_pr].astype(str).str.upper().str.strip()
    dfpr["Party"] = purchase[party_pr]
    dfpr["Invoice"] = purchase[inv_pr].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[tax_pr])
    dfpr["IGSTPR"] = num(purchase[igst_pr])
    dfpr["CGSTPR"] = num(purchase[cgst_pr])
    dfpr["SGSTPR"] = num(purchase[sgst_pr])


    # -----------------------------
    # Remove blank invoices
    # -----------------------------

    df2b = df2b[df2b["Invoice"] != ""]
    dfpr = dfpr[dfpr["Invoice"] != ""]


    # -----------------------------
    # Merge Data
    # -----------------------------

    recon = pd.merge(
        dfpr,
        df2b,
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
            reasons.append("IGST mismatch")

        if round(row["CGSTPR"],2) != round(row["CGST2B"],2):
            reasons.append("CGST mismatch")

        if round(row["SGSTPR"],2) != round(row["SGST2B"],2):
            reasons.append("SGST mismatch")

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
        "GST_Reconciliation_Output.xlsx"
    )
