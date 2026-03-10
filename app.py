import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST 2B Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# -----------------------------
# Clean invoice number
# Example: 258/25-26 → 258
# -----------------------------
def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    nums = re.findall(r'\d{3,5}', str(inv))

    return nums[0] if nums else ""


# -----------------------------
# Numeric conversion
# -----------------------------
def num(x):
    return pd.to_numeric(x, errors="coerce").fillna(0)


# -----------------------------
# Normalize columns
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
# Find column
# -----------------------------
def find_col(cols, word):

    for c in cols:
        if word in c:
            return c

    return None


# -----------------------------
# Detect header row
# -----------------------------
def detect_header(file, sheet):

    temp = pd.read_excel(file, sheet_name=sheet, header=None)

    for i in range(20):

        row = " ".join(temp.iloc[i].astype(str).str.lower())

        if "invoice" in row and "gst" in row:
            return i

    return 0


# =============================
# PROCESS
# =============================

if gstr_file and purchase_file:

    # -------------------------
    # Load GSTR-2B
    # -------------------------

    header2b = detect_header(gstr_file, "B2B")

    gstr2b = pd.read_excel(gstr_file, sheet_name="B2B", header=header2b)

    gstr2b = normalize(gstr2b)


    gstin_col = find_col(gstr2b.columns,"gstin")
    party_col = find_col(gstr2b.columns,"trade")
    invoice_col = find_col(gstr2b.columns,"invoice")
    taxable_col = find_col(gstr2b.columns,"taxable")

    igst_col = find_col(gstr2b.columns,"integrated")
    cgst_col = find_col(gstr2b.columns,"central")
    sgst_col = find_col(gstr2b.columns,"state")


    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin_col].astype(str).str.upper().str.strip()
    df2b["Party"] = gstr2b[party_col]
    df2b["Invoice"] = gstr2b[invoice_col].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[taxable_col])

    df2b["IGST2B"] = num(gstr2b[igst_col]) if igst_col in gstr2b.columns else 0
    df2b["CGST2B"] = num(gstr2b[cgst_col]) if cgst_col in gstr2b.columns else 0
    df2b["SGST2B"] = num(gstr2b[sgst_col]) if sgst_col in gstr2b.columns else 0

    # Remove duplicates
    df2b = df2b.groupby(["GSTIN","Invoice"], as_index=False).sum()


    # -------------------------
    # Load Purchase Register
    # -------------------------

    headerpr = detect_header(purchase_file,0)

    purchase = pd.read_excel(purchase_file, header=headerpr)

    purchase = normalize(purchase)


    gstin_pr = find_col(purchase.columns,"gstin") or find_col(purchase.columns,"gst")
    party_pr = find_col(purchase.columns,"particular")
    invoice_pr = find_col(purchase.columns,"invoice")
    taxable_pr = find_col(purchase.columns,"taxable")

    igst_pr = find_col(purchase.columns,"igst")
    cgst_pr = find_col(purchase.columns,"cgst")
    sgst_pr = find_col(purchase.columns,"sgst")


    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstin_pr].astype(str).str.upper().str.strip()
    dfpr["Party"] = purchase[party_pr]
    dfpr["Invoice"] = purchase[invoice_pr].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable_pr])

    dfpr["IGSTPR"] = num(purchase[igst_pr]) if igst_pr else 0
    dfpr["CGSTPR"] = num(purchase[cgst_pr]) if cgst_pr else 0
    dfpr["SGSTPR"] = num(purchase[sgst_pr]) if sgst_pr else 0


    # -------------------------
    # Merge
    # -------------------------

    recon = pd.merge(
        dfpr,
        df2b,
        on=["GSTIN","Invoice"],
        how="outer",
        indicator=True
    )


    # -------------------------
    # Reconciliation logic
    # -------------------------

    def check(r):

        if r["_merge"]=="left_only":
            return pd.Series(["Mismatch","Missing in 2B"])

        if r["_merge"]=="right_only":
            return pd.Series(["Mismatch","Missing in Purchase"])

        reasons=[]

        if r["TaxablePR"]!=r["Taxable2B"]:
            reasons.append("Taxable mismatch")

        if r["IGSTPR"]!=r["IGST2B"]:
            reasons.append("IGST mismatch")

        if r["CGSTPR"]!=r["CGST2B"]:
            reasons.append("CGST mismatch")

        if r["SGSTPR"]!=r["SGST2B"]:
            reasons.append("SGST mismatch")

        if len(reasons)==0:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]] = recon.apply(check,axis=1)

    recon = recon.drop(columns=["_merge"])


    st.subheader("Reconciliation Result")

    st.dataframe(recon,use_container_width=True)


    # Excel download
    buffer = BytesIO()

    recon.to_excel(buffer,index=False)

    st.download_button(
        "Download Excel Report",
        buffer.getvalue(),
        "GST_Reconciliation_Output.xlsx"
    )
