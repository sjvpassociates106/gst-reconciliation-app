import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST 2B Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# ---------- Helper Functions ----------

def clean_invoice(inv):
    if pd.isna(inv):
        return ""
    nums = re.findall(r"\d{3,6}", str(inv))
    return nums[0] if nums else ""


def num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def detect_header(file, sheet):
    temp = pd.read_excel(file, sheet_name=sheet, header=None)

    for i in range(20):
        row = " ".join(temp.iloc[i].astype(str).str.lower())
        if "invoice" in row and "gst" in row:
            return i
    return 0


def detect_columns(df):

    gstin_col=None
    party_col=None
    invoice_col=None
    taxable_col=None
    igst_col=None
    cgst_col=None
    sgst_col=None

    for col in df.columns:

        c=str(col).lower().replace("₹","")

        if "gstin" in c:
            gstin_col=col

        if "trade" in c or "legal" in c or "party" in c:
            party_col=col

        if "invoice" in c:
            invoice_col=col

        if "taxable" in c:
            taxable_col=col

        if "integrated" in c or "igst" in c:
            igst_col=col

        if "central" in c or "cgst" in c:
            cgst_col=col

        if "state" in c or "ut" in c or "sgst" in c:
            sgst_col=col

    return gstin_col,party_col,invoice_col,taxable_col,igst_col,cgst_col,sgst_col


# ---------- Main Processing ----------

if gstr_file and purchase_file:

    # ---------- Load GSTR2B ----------

    header2b=detect_header(gstr_file,"B2B")

    gstr2b=pd.read_excel(gstr_file,sheet_name="B2B",header=header2b)

    gstin_col,party_col,invoice_col,taxable_col,igst_col,cgst_col,sgst_col = detect_columns(gstr2b)

    df2b=pd.DataFrame()

    df2b["GSTIN"]=gstr2b[gstin_col].astype(str).str.upper().str.strip()
    df2b["Party"]=gstr2b[party_col]
    df2b["Invoice"]=gstr2b[invoice_col].apply(clean_invoice)

    df2b["Taxable2B"]=num(gstr2b[taxable_col])

    df2b["IGST2B"]=num(gstr2b[igst_col]) if igst_col else 0
    df2b["CGST2B"]=num(gstr2b[cgst_col]) if cgst_col else 0
    df2b["SGST2B"]=num(gstr2b[sgst_col]) if sgst_col else 0


    # ---------- Remove duplicate invoices ----------
    df2b=df2b.groupby(["GSTIN","Invoice"],as_index=False).sum()


    # ---------- Load Purchase Register ----------

    headerpr=detect_header(purchase_file,0)

    purchase=pd.read_excel(purchase_file,header=headerpr)

    gstin_col,party_col,invoice_col,taxable_col,igst_col,cgst_col,sgst_col = detect_columns(purchase)

    dfpr=pd.DataFrame()

    dfpr["GSTIN"]=purchase[gstin_col].astype(str).str.upper().str.strip()
    if party_col is None:
    party_col = df.columns[1] "trade" in c or "legal" in c or "party" in c or "supplier" in c or "vendor" in c or "name" in c or "particular" in c:
    party_col = col
    dfpr["Invoice"]=purchase[invoice_col].apply(clean_invoice)

    dfpr["TaxablePR"]=num(purchase[taxable_col])

    dfpr["IGSTPR"]=num(purchase[igst_col]) if igst_col else 0
    dfpr["CGSTPR"]=num(purchase[cgst_col]) if cgst_col else 0
    dfpr["SGSTPR"]=num(purchase[sgst_col]) if sgst_col else 0


    # ---------- Merge ----------
    recon=pd.merge(
        dfpr,
        df2b,
        on=["GSTIN","Invoice"],
        how="outer",
        indicator=True
    )


    # ---------- Reconciliation Logic ----------

    def check(row):

        if row["_merge"]=="left_only":
            return pd.Series(["Mismatch","Missing in 2B"])

        if row["_merge"]=="right_only":
            return pd.Series(["Mismatch","Missing in Purchase"])

        tol=1
        reasons=[]

        if abs(row["TaxablePR"]-row["Taxable2B"])>tol:
            reasons.append("Taxable mismatch")

        if abs(row["IGSTPR"]-row["IGST2B"])>tol:
            reasons.append("IGST mismatch")

        if abs(row["CGSTPR"]-row["CGST2B"])>tol:
            reasons.append("CGST mismatch")

        if abs(row["SGSTPR"]-row["SGST2B"])>tol:
            reasons.append("SGST mismatch")

        if len(reasons)==0:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]]=recon.apply(check,axis=1)

    recon=recon.drop(columns=["_merge"])


    # ---------- Show Result ----------
    st.subheader("Reconciliation Result")

    st.dataframe(recon,use_container_width=True)


    # ---------- Download Excel ----------

    buffer=BytesIO()

    recon.to_excel(buffer,index=False)

    st.download_button(
        label="Download Excel Report",
        data=buffer.getvalue(),
        file_name="GST_Reconciliation_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
