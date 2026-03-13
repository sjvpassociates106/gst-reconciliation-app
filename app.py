import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# ---------------- Functions ----------------

def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    inv = str(inv).upper()

    inv = re.sub(r"[^A-Z0-9]", "", inv)

    inv = re.sub(r"20[0-9]{2}", "", inv)

    return inv[-6:]


def num(series):

    return (
        series.astype(str)
        .str.replace("₹","",regex=False)
        .str.replace(",","",regex=False)
        .str.strip()
        .replace("",0)
        .astype(float)
    )


def detect_header(file, sheet):

    temp = pd.read_excel(file, sheet_name=sheet, header=None)

    for i in range(20):

        row = " ".join(temp.iloc[i].astype(str).str.lower())

        if "gstin of supplier" in row:
            return i

    return 0


# ---------------- Process ----------------

if gstr_file and purchase_file:

    # -------- Load GSTR-2B --------

    header2b = detect_header(gstr_file,"B2B")

    gstr2b = pd.read_excel(
        gstr_file,
        sheet_name="B2B",
        header=[header2b, header2b+1]
    )

    gstr2b.columns = [' '.join([str(i) for i in col]).strip() for col in gstr2b.columns]

    gstr2b.columns = gstr2b.columns.str.replace("₹","")

    # Detect columns
    gstin_col = None
    party_col = None
    invoice_col = None
    taxable_col = None
    igst_col = None
    cgst_col = None
    sgst_col = None

    for col in gstr2b.columns:

        c = str(col).lower()

        if "gstin" in c:
            gstin_col = col

        elif "trade" in c or "legal" in c:
            party_col = col

        elif "invoice" in c:
            invoice_col = col

        elif "taxable" in c:
            taxable_col = col

        elif "integrated" in c or "igst" in c:
            igst_col = col

        elif "central" in c or "cgst" in c:
            cgst_col = col

        elif "state" in c or "sgst" in c:
            sgst_col = col


    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin_col].astype(str).str.upper().str.strip()
    df2b["Party"] = gstr2b[party_col]
    df2b["Invoice"] = gstr2b[invoice_col].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[taxable_col])

    df2b["IGST2B"] = num(gstr2b[igst_col]) if igst_col else 0
    df2b["CGST2B"] = num(gstr2b[cgst_col]) if cgst_col else 0
    df2b["SGST2B"] = num(gstr2b[sgst_col]) if sgst_col else 0


    df2b = (
        df2b.groupby(["GSTIN","Invoice"],as_index=False)
        .agg({
            "Party":"first",
            "Taxable2B":"sum",
            "IGST2B":"sum",
            "CGST2B":"sum",
            "SGST2B":"sum"
        })
    )


    # -------- Load Purchase Register --------

    purchase = pd.read_excel(purchase_file)

    gstin_pr = None
    party_pr = None
    invoice_pr = None
    taxable_pr = None
    igst_pr = None
    cgst_pr = None
    sgst_pr = None

    for col in purchase.columns:

        c = str(col).lower()

        if "gstin" in c:
            gstin_pr = col

        elif "party" in c or "vendor" in c or "supplier" in c:
            party_pr = col

        elif "invoice" in c or "bill" in c:
            invoice_pr = col

        elif "taxable" in c:
            taxable_pr = col

        elif "igst" in c:
            igst_pr = col

        elif "cgst" in c:
            cgst_pr = col

        elif "sgst" in c:
            sgst_pr = col


    dfpr = pd.DataFrame()

    if gstin_pr:
        dfpr["GSTIN"] = purchase[gstin_pr].astype(str).str.upper().str.strip()
    else:
        dfpr["GSTIN"] = "UNKNOWN"

    dfpr["Party"] = purchase[party_pr] if party_pr else "UNKNOWN"

    dfpr["Invoice"] = purchase[invoice_pr].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable_pr]) if taxable_pr else 0

    dfpr["IGSTPR"] = num(purchase[igst_pr]) if igst_pr else 0
    dfpr["CGSTPR"] = num(purchase[cgst_pr]) if cgst_pr else 0
    dfpr["SGSTPR"] = num(purchase[sgst_pr]) if sgst_pr else 0


    # -------- Merge --------

    recon = pd.merge(
        dfpr,
        df2b,
        on=["Invoice"],
        how="outer",
        indicator=True
    )


    # -------- Reconciliation --------

    def check(r):

        if r["_merge"] == "left_only":
            return pd.Series(["Mismatch","Missing in 2B"])

        if r["_merge"] == "right_only":
            return pd.Series(["Mismatch","Missing in Purchase"])

        tol = 2
        reasons = []

        if abs(r["TaxablePR"] - r["Taxable2B"]) > tol:
            reasons.append("Taxable mismatch")

        if abs(r["IGSTPR"] - r["IGST2B"]) > tol:
            reasons.append("IGST mismatch")

        if abs(r["CGSTPR"] - r["CGST2B"]) > tol:
            reasons.append("CGST mismatch")

        if abs(r["SGSTPR"] - r["SGST2B"]) > tol:
            reasons.append("SGST mismatch")

        if len(reasons) == 0:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]] = recon.apply(check, axis=1)

    recon = recon.drop(columns=["_merge"])


    st.subheader("Reconciliation Result")

    st.dataframe(recon, use_container_width=True)


    # -------- Excel Download --------

    buffer = BytesIO()

    recon.to_excel(buffer, index=False)

    st.download_button(
        label="Download Excel Report",
        data=buffer.getvalue(),
        file_name="GST_Reconciliation_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
