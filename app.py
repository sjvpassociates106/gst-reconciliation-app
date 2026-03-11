import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# -------- Functions --------

def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    inv = str(inv).upper()

    # remove symbols
    inv = re.sub(r"[^A-Z0-9]", "", inv)

    # remove years
    inv = re.sub(r"20[2-3][0-9]", "", inv)

    return inv[-6:]


def num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def detect_header(file, sheet):
    temp = pd.read_excel(file, sheet_name=sheet, header=None)

    for i in range(15):
        row = " ".join(temp.iloc[i].astype(str).str.lower())
        if "invoice" in row and "gst" in row:
            return i

    return 0


# -------- Process --------

if gstr_file and purchase_file:

    # ----- Load GSTR2B -----

    header2b = detect_header(gstr_file,"B2B")

    gstr2b = pd.read_excel(gstr_file,sheet_name="B2B",header=header2b)

    # Detect columns
    gstin_col=None
    party_col=None
    invoice_col=None
    taxable_col=None
    igst_col=None
    cgst_col=None
    sgst_col=None

    for col in gstr2b.columns:

        c=str(col).lower().replace("₹","")

        if "gstin" in c:
            gstin_col=col

        if "trade" in c or "legal" in c:
            party_col=col

        if "invoice" in c:
            invoice_col=col

        if "taxable" in c:
            taxable_col=col

        if "integrated" in c:
            igst_col=col

        if "central" in c:
            cgst_col=col

        if "state" in c or "ut" in c:
            sgst_col=col


    df2b=pd.DataFrame()

    df2b["GSTIN"]=gstr2b[gstin_col].astype(str).str.upper().str.strip()
    df2b["Party"]=gstr2b[party_col]
    df2b["Invoice"]=gstr2b[invoice_col].apply(clean_invoice)

    df2b["Taxable2B"]=num(gstr2b[taxable_col])

    df2b["IGST2B"]=num(gstr2b[igst_col]) if igst_col else 0
    df2b["CGST2B"]=num(gstr2b[cgst_col]) if cgst_col else 0
    df2b["SGST2B"]=num(gstr2b[sgst_col]) if sgst_col else 0


    # Remove duplicate invoices
    df2b=df2b.groupby(["GSTIN","Invoice"],as_index=False).sum()


    # ----- Load Purchase Register -----

    headerpr=detect_header(purchase_file,0)

    purchase=pd.read_excel(purchase_file,header=headerpr)

    gstin_pr=None
    party_pr=None
    invoice_pr=None
    taxable_pr=None
    igst_pr=None
    cgst_pr=None
    sgst_pr=None

    for col in purchase.columns:

        c=str(col).lower()

        if "gstin" in c or "uin" in c:
            gstin_pr=col

        if "particular" in c or "party" in c:
            party_pr=col

        if "invoice" in c:
            invoice_pr=col

        if "taxable" in c:
            taxable_pr=col

        if "igst" in c:
            igst_pr=col

        if "cgst" in c:
            cgst_pr=col

        if "sgst" in c:
            sgst_pr=col


    dfpr=pd.DataFrame()

    dfpr["GSTIN"]=purchase[gstin_pr].astype(str).str.upper().str.strip()
    dfpr["Party"]=purchase[party_pr]
    dfpr["Invoice"]=purchase[invoice_pr].apply(clean_invoice)

    dfpr["TaxablePR"]=num(purchase[taxable_pr])

    dfpr["IGSTPR"]=num(purchase[igst_pr]) if igst_pr else 0
    dfpr["CGSTPR"]=num(purchase[cgst_pr]) if cgst_pr else 0
    dfpr["SGSTPR"]=num(purchase[sgst_pr]) if sgst_pr else 0


    # ----- Merge -----

    recon=pd.merge(
        dfpr,
        df2b,
        on=["GSTIN","Invoice"],
        how="outer",
        indicator=True
    )


    # ----- Reconciliation -----

    def check(r):

        if r["_merge"]=="left_only":
            return pd.Series(["Mismatch","Missing in 2B"])

        if r["_merge"]=="right_only":
            return pd.Series(["Mismatch","Missing in Purchase"])

        tol=1
        reasons=[]

        if abs(r["TaxablePR"]-r["Taxable2B"])>tol:
            reasons.append("Taxable mismatch")

        if abs(r["IGSTPR"]-r["IGST2B"])>tol:
            reasons.append("IGST mismatch")

        if abs(r["CGSTPR"]-r["CGST2B"])>tol:
            reasons.append("CGST mismatch")

        if abs(r["SGSTPR"]-r["SGST2B"])>tol:
            reasons.append("SGST mismatch")

        if len(reasons)==0:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]]=recon.apply(check,axis=1)

    recon=recon.drop(columns=["_merge"])


    st.subheader("Reconciliation Result")

    st.dataframe(recon,use_container_width=True)


    # ----- Excel Download -----

    buffer=BytesIO()

    recon.to_excel(buffer,index=False)

    st.download_button(
        label="Download Excel Report",
        data=buffer.getvalue(),
        file_name="GST_Reconciliation_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_excel"
    )
