import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation", layout="wide")
st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# -------- FUNCTIONS --------

def clean_invoice(inv):
    if pd.isna(inv):
        return ""
    inv = str(inv).upper()
    inv = re.sub(r"[^A-Z0-9]", "", inv)
    inv = re.sub(r"20[2-3][0-9]", "", inv)
    return inv[-6:]


def num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def detect_header(file, sheet):
    temp = pd.read_excel(file, sheet_name=sheet, header=None)

    for i in range(20):
        row = " ".join(temp.iloc[i].astype(str).str.lower())
        if "invoice" in row and "gst" in row:
            return i
    return 0


# -------- PROCESS --------

if gstr_file and purchase_file:

    # ----- LOAD GSTR2B -----
    header2b = detect_header(gstr_file, "B2B")
    gstr2b = pd.read_excel(gstr_file, sheet_name="B2B", header=header2b)

    gstin_col = party_col = invoice_col = None
    taxable_col = igst_col = cgst_col = sgst_col = None

    for col in gstr2b.columns:

        c = str(col).lower()
        c = c.replace("₹","").replace("(", "").replace(")", "")
        c = c.replace("_", " ").replace("-", " ")
        c = " ".join(c.split())

        if "gstin" in c:
            gstin_col = col

        if "trade" in c or "legal" in c:
            party_col = col

        if "invoice" in c:
            invoice_col = col

        if "taxable" in c:
            taxable_col = col

        if "integrated tax" in c or "igst" in c:
            igst_col = col

        if "central tax" in c or "cgst" in c:
            cgst_col = col

        if "state" in c or "sgst" in c or "ut" in c:
            sgst_col = col


    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin_col].astype(str).str.upper().str.strip()
    df2b["Party"] = gstr2b[party_col].astype(str).str.upper().str.strip()
    df2b["Invoice"] = gstr2b[invoice_col].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[taxable_col]) if taxable_col else 0
    df2b["IGST2B"] = num(gstr2b[igst_col]) if igst_col else 0
    df2b["CGST2B"] = num(gstr2b[cgst_col]) if cgst_col else 0
    df2b["SGST2B"] = num(gstr2b[sgst_col]) if sgst_col else 0

    # fix None → 0
    df2b["Taxable2B"] = num(df2b["Taxable2B"])
    df2b["IGST2B"] = num(df2b["IGST2B"])
    df2b["CGST2B"] = num(df2b["CGST2B"])
    df2b["SGST2B"] = num(df2b["SGST2B"])

    df2b = df2b.groupby(["GSTIN","Invoice"], as_index=False).sum()


    # ----- LOAD PURCHASE -----
    headerpr = detect_header(purchase_file, 0)
    purchase = pd.read_excel(purchase_file, header=headerpr)

    gstin_pr = party_pr = invoice_pr = None
    taxable_pr = igst_pr = cgst_pr = sgst_pr = None

    for col in purchase.columns:

        c = str(col).lower()

        if "gstin" in c or "uin" in c:
            gstin_pr = col

        if "party" in c or "particular" in c:
            party_pr = col

        if "invoice" in c:
            invoice_pr = col

        if "taxable" in c:
            taxable_pr = col

        if "igst" in c:
            igst_pr = col

        if "cgst" in c:
            cgst_pr = col

        if "sgst" in c:
            sgst_pr = col


    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstin_pr].astype(str).str.upper().str.strip()
    dfpr["Party"] = purchase[party_pr].astype(str).str.upper().str.strip()
    dfpr["Invoice"] = purchase[invoice_pr].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable_pr]) if taxable_pr else 0
    dfpr["IGSTPR"] = num(purchase[igst_pr]) if igst_pr else 0
    dfpr["CGSTPR"] = num(purchase[cgst_pr]) if cgst_pr else 0
    dfpr["SGSTPR"] = num(purchase[sgst_pr]) if sgst_pr else 0

    # fix None → 0
    dfpr["TaxablePR"] = num(dfpr["TaxablePR"])
    dfpr["IGSTPR"] = num(dfpr["IGSTPR"])
    dfpr["CGSTPR"] = num(dfpr["CGSTPR"])
    dfpr["SGSTPR"] = num(dfpr["SGSTPR"])

    dfpr = dfpr.groupby(["GSTIN","Invoice"], as_index=False).sum()


    # ----- MERGE -----
    recon = pd.merge(dfpr, df2b, on=["GSTIN","Invoice"], how="outer", indicator=True)


    # ----- CHECK -----
    def check(r):

        if r["_merge"] == "left_only":
            return pd.Series(["Mismatch","Missing in 2B"])

        if r["_merge"] == "right_only":
            return pd.Series(["Mismatch","Missing in Purchase"])

        tol = 1
        reasons = []

        if abs(r["TaxablePR"] - r["Taxable2B"]) > tol:
            reasons.append("Taxable mismatch")

        if abs(r["CGSTPR"] - r["CGST2B"]) > tol:
            reasons.append("CGST mismatch")

        if abs(r["SGSTPR"] - r["SGST2B"]) > tol:
            reasons.append("SGST mismatch")

        if abs(r["IGSTPR"] - r["IGST2B"]) > tol:
            reasons.append("IGST mismatch")

        if not reasons:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]] = recon.apply(check, axis=1)
    recon = recon.drop(columns=["_merge"])


    # ----- OUTPUT -----
    st.subheader("Reconciliation Result")
    st.dataframe(recon, use_container_width=True)


    # ----- DOWNLOAD -----
    buffer = BytesIO()
    recon.to_excel(buffer, index=False)

    st.download_button(
        label="Download Excel Report",
        data=buffer.getvalue(),
        file_name="GST_Reconciliation_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
