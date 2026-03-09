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
# Example: A/123/23-24 → 123
# -----------------------------
def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    nums = re.findall(r"\d+", str(inv))

    if nums:
        return nums[0]

    return ""


# -----------------------------
# Safe numeric conversion
# -----------------------------
def num(series):

    return pd.to_numeric(series, errors="coerce").fillna(0)


# -----------------------------
# Normalize column names
# -----------------------------
def normalize(df):

    df.columns = (
        df.columns.astype(str)
        .str.lower()
        .str.replace("₹","")
        .str.replace("(","")
        .str.replace(")","")
        .str.strip()
    )

    return df


# -----------------------------
# Safe column finder
# -----------------------------
def find_col(cols, keyword):

    for c in cols:
        if keyword in c.lower():
            return c

    return None


# =============================
# PROCESS
# =============================
if gstr_file and purchase_file:

    # -------- Load GSTR2B --------

    gstr2b = pd.read_excel(gstr_file, sheet_name="B2B", header=3)

    gstr2b = normalize(gstr2b)

    gstin_col = find_col(gstr2b.columns,"gstin")
    party_col = find_col(gstr2b.columns,"trade")
    invoice_col = find_col(gstr2b.columns,"invoice")
    taxable_col = find_col(gstr2b.columns,"taxable")

    igst_col = find_col(gstr2b.columns,"integrated")
    cgst_col = find_col(gstr2b.columns,"central")
    sgst_col = find_col(gstr2b.columns,"state")

    if gstin_col is None or invoice_col is None:

        st.error("GSTIN or Invoice column not found in B2B sheet")

        st.write("Detected columns:", gstr2b.columns)

        st.stop()


    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin_col].astype(str).str.strip().str.upper()
    df2b["Party"] = gstr2b[party_col]
    df2b["Invoice"] = gstr2b[invoice_col].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[taxable_col]) if taxable_col else 0

    df2b["IGST2B"] = num(gstr2b[igst_col]) if igst_col else 0
    df2b["CGST2B"] = num(gstr2b[cgst_col]) if cgst_col else 0
    df2b["SGST2B"] = num(gstr2b[sgst_col]) if sgst_col else 0


    # -------- Load Purchase Register --------

    purchase = pd.read_excel(purchase_file)

    purchase = normalize(purchase)

    gstin_pr = find_col(purchase.columns,"gst")
    party_pr = find_col(purchase.columns,"particular")
    invoice_pr = find_col(purchase.columns,"invoice")
    taxable_pr = find_col(purchase.columns,"taxable")

    igst_pr = find_col(purchase.columns,"igst")
    cgst_pr = find_col(purchase.columns,"cgst")
    sgst_pr = find_col(purchase.columns,"sgst")


    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstin_pr].astype(str).str.strip().str.upper()
    dfpr["Party"] = purchase[party_pr]
    dfpr["Invoice"] = purchase[invoice_pr].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable_pr]) if taxable_pr else 0

    dfpr["IGSTPR"] = num(purchase[igst_pr]) if igst_pr else 0
    dfpr["CGSTPR"] = num(purchase[cgst_pr]) if cgst_pr else 0
    dfpr["SGSTPR"] = num(purchase[sgst_pr]) if sgst_pr else 0


    # Remove empty invoice
    df2b = df2b[df2b["Invoice"]!=""]
    dfpr = dfpr[dfpr["Invoice"]!=""]


    # -------- Merge --------

    recon = pd.merge(
        dfpr,
        df2b,
        on=["GSTIN","Invoice"],
        how="outer",
        indicator=True
    )


    # -------- Reconciliation Logic --------

    def check(row):

        if row["_merge"]=="left_only":
            return pd.Series(["Mismatch","Missing in GSTR2B"])

        if row["_merge"]=="right_only":
            return pd.Series(["Mismatch","Missing in Purchase Register"])

        reasons=[]

        if round(row["IGSTPR"],2)!=round(row["IGST2B"],2):
            reasons.append("IGST mismatch")

        if round(row["CGSTPR"],2)!=round(row["CGST2B"],2):
            reasons.append("CGST mismatch")

        if round(row["SGSTPR"],2)!=round(row["SGST2B"],2):
            reasons.append("SGST mismatch")

        if len(reasons)==0:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]] = recon.apply(check,axis=1)

    recon = recon.drop(columns=["_merge"])


    st.subheader("Reconciliation Result")

    st.dataframe(recon,use_container_width=True)


    # -------- Excel Download --------

    buffer = BytesIO()

    recon.to_excel(buffer,index=False)

    st.download_button(
        "Download Excel",
        buffer.getvalue(),
        "GST_Reconciliation_Output.xlsx"
    )
