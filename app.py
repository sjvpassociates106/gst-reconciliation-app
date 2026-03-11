import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# --------------------------
# CLEAN INVOICE
# --------------------------

def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    nums = re.findall(r"\d{2,6}", str(inv))

    if nums:
        return nums[-1]

    return ""


# --------------------------
# NUMERIC SAFE
# --------------------------

def num(series):

    return pd.to_numeric(series, errors="coerce").fillna(0)


# --------------------------
# DETECT HEADER ROW
# --------------------------

def detect_header(file, sheet):

    temp = pd.read_excel(file, sheet_name=sheet, header=None)

    for i in range(25):

        row = " ".join(temp.iloc[i].astype(str).str.lower())

        if "invoice" in row or "gstin" in row:
            return i

    return 0


# --------------------------
# COLUMN DETECTION
# --------------------------

def detect_columns(df):

    gstin=None
    party=None
    invoice=None
    taxable=None
    igst=None
    cgst=None
    sgst=None

    for col in df.columns:

        c=str(col).lower().replace("₹","").strip()

        if "gstin" in c:
            gstin=col

        elif ("trade" in c or "legal" in c or "party" in c
              or "supplier" in c or "vendor" in c
              or "particular" in c or "name" in c):
            party=col

        elif ("invoice" in c or "inv" in c
              or "bill" in c or "voucher" in c):
            invoice=col

        elif "taxable" in c:
            taxable=col

        elif "integrated" in c or "igst" in c:
            igst=col

        elif "central" in c or "cgst" in c:
            cgst=col

        elif "state" in c or "ut" in c or "sgst" in c:
            sgst=col


    # ---------- FALLBACK PROTECTION ----------

    cols=list(df.columns)

    if gstin is None and len(cols)>0:
        gstin=cols[0]

    if party is None and len(cols)>1:
        party=cols[1]

    if invoice is None and len(cols)>2:
        invoice=cols[2]

    return gstin,party,invoice,taxable,igst,cgst,sgst


# --------------------------
# MAIN PROCESS
# --------------------------

if gstr_file and purchase_file:

    # ---------- LOAD GSTR2B ----------

    header2b = detect_header(gstr_file,"B2B")

    gstr2b = pd.read_excel(gstr_file, sheet_name="B2B", header=header2b)

    gstin,party,invoice,taxable,igst,cgst,sgst = detect_columns(gstr2b)

    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin].astype(str).str.upper().str.strip()
    df2b["Party"] = gstr2b[party]
    df2b["Invoice"] = gstr2b[invoice].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[taxable]) if taxable else 0
    df2b["IGST2B"] = num(gstr2b[igst]) if igst else 0
    df2b["CGST2B"] = num(gstr2b[cgst]) if cgst else 0
    df2b["SGST2B"] = num(gstr2b[sgst]) if sgst else 0


    # ---------- REMOVE DUPLICATE INVOICES ----------

    df2b = df2b.groupby(["GSTIN","Invoice"], as_index=False).sum()


    # ---------- LOAD PURCHASE REGISTER ----------

    headerpr = detect_header(purchase_file,0)

    purchase = pd.read_excel(purchase_file, header=headerpr)

    gstin,party,invoice,taxable,igst,cgst,sgst = detect_columns(purchase)

    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstin].astype(str).str.upper().str.strip()
    dfpr["Party"] = purchase[party]
    dfpr["Invoice"] = purchase[invoice].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable]) if taxable else 0
    dfpr["IGSTPR"] = num(purchase[igst]) if igst else 0
    dfpr["CGSTPR"] = num(purchase[cgst]) if cgst else 0
    dfpr["SGSTPR"] = num(purchase[sgst]) if sgst else 0


    # ---------- MERGE ----------

    recon = pd.merge(
        dfpr,
        df2b,
        on=["GSTIN","Invoice"],
        how="outer",
        indicator=True
    )


    # ---------- RECON LOGIC ----------

    def status(r):

        if r["_merge"]=="left_only":
            return "Missing in 2B"

        if r["_merge"]=="right_only":
            return "Missing in Books"

        tol=1

        if abs(r["TaxablePR"]-r["Taxable2B"])<=tol \
        and abs(r["CGSTPR"]-r["CGST2B"])<=tol \
        and abs(r["SGSTPR"]-r["SGST2B"])<=tol \
        and abs(r["IGSTPR"]-r["IGST2B"])<=tol:

            return "Matched"

        return "Mismatch"


    recon["Status"] = recon.apply(status, axis=1)

    recon = recon.drop(columns=["_merge"])


    # ---------- DISPLAY ----------

    st.subheader("Reconciliation Result")

    st.dataframe(recon, use_container_width=True)


    # ---------- EXCEL DOWNLOAD ----------

    buffer = BytesIO()

    recon.to_excel(buffer, index=False)

    st.download_button(
        "Download Excel Report",
        data=buffer.getvalue(),
        file_name="GST_Reconciliation_Output.xlsx"
    )
