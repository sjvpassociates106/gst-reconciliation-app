import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")


gstr_file = st.file_uploader("Upload GSTR-2B", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# -------------------------
# CLEAN INVOICE
# -------------------------

def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    nums = re.findall(r"\d{3,6}", str(inv))

    if nums:
        return nums[-1]

    return ""


# -------------------------
# NUMERIC CLEAN
# -------------------------

def num(series):

    return pd.to_numeric(series, errors="coerce").fillna(0)


# -------------------------
# HEADER DETECT
# -------------------------

def detect_header(file, sheet):

    temp = pd.read_excel(file, sheet_name=sheet, header=None)

    for i in range(20):

        row = " ".join(temp.iloc[i].astype(str).str.lower())

        if "invoice" in row and "gst":
            return i

    return 0


# -------------------------
# COLUMN DETECTION
# -------------------------

def detect_columns(df):

    gstin=None
    party=None
    invoice=None
    taxable=None
    igst=None
    cgst=None
    sgst=None

    for col in df.columns:

        c=str(col).lower()

        if "gstin" in c:
            gstin=col

        elif "particular" in c or "party" in c or "supplier" in c:
            party=col

        elif ("invoice" in c 
              or "inv" in c 
              or "bill" in c):
            invoice=col

        elif "taxable" in c:
            taxable=col

        elif "igst" in c or "integrated" in c:
            igst=col

        elif "cgst" in c or "central" in c:
            cgst=col

        elif "sgst" in c or "state" in c:
            sgst=col

    # fallback protection
    if invoice is None:
        invoice = df.columns[4]

    return gstin,party,invoice,taxable,igst,cgst,sgst

# -------------------------
# MAIN PROCESS
# -------------------------

if gstr_file and purchase_file:

    header2b = detect_header(gstr_file,"B2B")

    gstr2b = pd.read_excel(gstr_file, sheet_name="B2B", header=header2b)

    gstin,party,invoice,taxable,igst,cgst,sgst = detect_columns(gstr2b)

    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin].astype(str).str.upper().str.strip()

    df2b["Party"] = gstr2b[party]

    df2b["Invoice"] = gstr2b[invoice].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[taxable])

    df2b["IGST2B"] = num(gstr2b[igst]) if igst else 0
    df2b["CGST2B"] = num(gstr2b[cgst]) if cgst else 0
    df2b["SGST2B"] = num(gstr2b[sgst]) if sgst else 0


    # Remove duplicates
    df2b = df2b.groupby(["GSTIN","Invoice"], as_index=False).sum()


    # Purchase Register

    headerpr = detect_header(purchase_file,0)

    purchase = pd.read_excel(purchase_file, header=headerpr)

    gstin,party,invoice,taxable,igst,cgst,sgst = detect_columns(purchase)

    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstin].astype(str).str.upper().str.strip()

    dfpr["Party"] = purchase[party]

    dfpr["Invoice"] = purchase[invoice].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable])

    dfpr["IGSTPR"] = num(purchase[igst]) if igst else 0
    dfpr["CGSTPR"] = num(purchase[cgst]) if cgst else 0
    dfpr["SGSTPR"] = num(purchase[sgst]) if sgst else 0


    # -------------------------
    # MERGE
    # -------------------------

    recon = pd.merge(
        dfpr,
        df2b,
        on=["GSTIN","Invoice"],
        how="outer",
        indicator=True
    )


    # -------------------------
    # MATCH LOGIC
    # -------------------------

    def status(r):

        if r["_merge"]=="left_only":
            return "Missing in 2B"

        if r["_merge"]=="right_only":
            return "Missing in Books"

        tol = 1

        if abs(r["TaxablePR"]-r["Taxable2B"])<=tol \
        and abs(r["CGSTPR"]-r["CGST2B"])<=tol \
        and abs(r["SGSTPR"]-r["SGST2B"])<=tol \
        and abs(r["IGSTPR"]-r["IGST2B"])<=tol:

            return "Matched"

        return "Mismatch"


    recon["Status"] = recon.apply(status, axis=1)


    # -------------------------
    # REPORTS
    # -------------------------

    matched = recon[recon["Status"]=="Matched"]

    mismatch = recon[recon["Status"]=="Mismatch"]

    missing2b = recon[recon["Status"]=="Missing in 2B"]

    missingbooks = recon[recon["Status"]=="Missing in Books"]


    st.subheader("Reconciliation Result")

    st.write("Matched ITC", matched.shape[0])
    st.write("Mismatch ITC", mismatch.shape[0])
    st.write("Missing in 2B", missing2b.shape[0])
    st.write("Missing in Books", missingbooks.shape[0])


    st.dataframe(recon,use_container_width=True)


    # -------------------------
    # EXCEL EXPORT
    # -------------------------

    buffer = BytesIO()

    with pd.ExcelWriter(buffer) as writer:

        matched.to_excel(writer,"Matched",index=False)
        mismatch.to_excel(writer,"Mismatch",index=False)
        missing2b.to_excel(writer,"Missing_in_2B",index=False)
        missingbooks.to_excel(writer,"Missing_in_Books",index=False)


    st.download_button(
        "Download Reconciliation Report",
        data=buffer.getvalue(),
        file_name="GST_Reconciliation_Report.xlsx"
    )
