import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# ---------------- FUNCTIONS ----------------

def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    inv = str(inv).upper().strip()

    inv = re.sub(r"[^A-Z0-9]", "", inv)

    inv = re.sub(r"20[0-9]{2}", "", inv)

    nums = re.findall(r"\d+", inv)

    if nums:
        return nums[-1]

    return inv


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


# ---------------- PROCESS ----------------

if gstr_file and purchase_file:

    # -------- LOAD GSTR-2B --------

    header2b = detect_header(gstr_file,"B2B")

    gstr2b = pd.read_excel(
        gstr_file,
        sheet_name="B2B",
        header=[header2b,header2b+1]
    )

    gstr2b.columns = [' '.join([str(i) for i in col]).strip() for col in gstr2b.columns]

    gstr2b.columns = gstr2b.columns.str.replace("₹","")

    gstin_col=None
    party_col=None
    invoice_col=None
    taxable_col=None
    igst_col=None
    cgst_col=None
    sgst_col=None

    for col in gstr2b.columns:

        c=str(col).lower()

        if "gstin" in c:
            gstin_col=col

        elif "trade" in c or "legal" in c:
            party_col=col

        elif "invoice" in c:
            invoice_col=col

        elif "taxable" in c:
            taxable_col=col

        elif "integrated" in c or "igst" in c:
            igst_col=col

        elif "central" in c or "cgst" in c:
            cgst_col=col

        elif "state" in c or "sgst" in c:
            sgst_col=col


    df2b=pd.DataFrame()

    df2b["GSTIN"]=gstr2b[gstin_col].astype(str).str.upper().str.strip()
    df2b["Party"]=gstr2b[party_col]
    df2b["Invoice"]=gstr2b[invoice_col].apply(clean_invoice)

    df2b["Taxable2B"]=num(gstr2b[taxable_col])

    df2b["IGST2B"]=num(gstr2b[igst_col]) if igst_col else 0
    df2b["CGST2B"]=num(gstr2b[cgst_col]) if cgst_col else 0
    df2b["SGST2B"]=num(gstr2b[sgst_col]) if sgst_col else 0

    df2b = df2b.dropna(subset=["Invoice"])

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


    # -------- LOAD PURCHASE REGISTER --------

    purchase_raw = pd.read_excel(purchase_file, header=None)

    header_row = 0

    for i in range(20):

        row = " ".join(purchase_raw.iloc[i].astype(str).str.lower())

        if "invoice" in row or "bill" in row:
            header_row=i
            break

    purchase = pd.read_excel(purchase_file, header=header_row)

    purchase.columns = purchase.columns.astype(str).str.replace("₹","")

    gstin_pr=None
    party_pr=None
    invoice_pr=None
    taxable_pr=None
    igst_pr=None
    cgst_pr=None
    sgst_pr=None

    for col in purchase.columns:

        c=str(col).lower()

        if "gstin" in c:
            gstin_pr=col

        elif "party" in c or "vendor" in c or "supplier" in c:
            party_pr=col

        elif "invoice" in c or "bill" in c:
            invoice_pr=col

        elif "taxable" in c:
            taxable_pr=col

        elif "igst" in c:
            igst_pr=col

        elif "cgst" in c:
            cgst_pr=col

        elif "sgst" in c:
            sgst_pr=col


    dfpr=pd.DataFrame()

    if gstin_pr and gstin_pr in purchase.columns:
        dfpr["GSTIN"]=purchase[gstin_pr].astype(str).str.upper().str.strip()
    else:
        dfpr["GSTIN"]="UNKNOWN"

    if party_pr and party_pr in purchase.columns:
        dfpr["Party"]=purchase[party_pr]
    else:
        dfpr["Party"]="UNKNOWN"

    if invoice_pr and invoice_pr in purchase.columns:
        dfpr["Invoice"]=purchase[invoice_pr].apply(clean_invoice)
    else:
        st.error("Invoice column not found in Purchase Register")
        st.write("Columns:",purchase.columns)
        st.stop()

    dfpr["TaxablePR"]=num(purchase[taxable_pr]) if taxable_pr else 0
    dfpr["IGSTPR"]=num(purchase[igst_pr]) if igst_pr else 0
    dfpr["CGSTPR"]=num(purchase[cgst_pr]) if cgst_pr else 0
    dfpr["SGSTPR"]=num(purchase[sgst_pr]) if sgst_pr else 0

    dfpr = dfpr.dropna(subset=["Invoice"])


    # -------- MERGE --------

    recon=dfpr.merge(df2b,on="Invoice",how="outer",indicator=True)

    tol=2

    recon["Status"]="Matched"

    recon.loc[recon["_merge"]=="left_only","Status"]="Missing in 2B"

    recon.loc[recon["_merge"]=="right_only","Status"]="Missing in Purchase"

    recon["Tax Diff"]=recon["TaxablePR"]-recon["Taxable2B"]


    # -------- DASHBOARD --------

    total=len(recon)

    matched=len(recon[recon["Status"]=="Matched"])

    missing2b=len(recon[recon["Status"]=="Missing in 2B"])

    missingpr=len(recon[recon["Status"]=="Missing in Purchase"])

    st.subheader("Reconciliation Summary")

    c1,c2,c3,c4=st.columns(4)

    c1.metric("Total Invoices",total)

    c2.metric("Matched",matched)

    c3.metric("Missing in 2B",missing2b)

    c4.metric("Missing in Purchase",missingpr)


    st.subheader("Full Reconciliation")

    st.dataframe(recon,use_container_width=True)


    # -------- PARTY SUMMARY --------

    party_summary=recon.groupby("Party_x").agg({

        "TaxablePR":"sum",
        "Taxable2B":"sum",
        "CGSTPR":"sum",
        "CGST2B":"sum",
        "SGSTPR":"sum",
        "SGST2B":"sum",
        "IGSTPR":"sum",
        "IGST2B":"sum"

    }).reset_index()

    party_summary["Taxable Diff"]=party_summary["TaxablePR"]-party_summary["Taxable2B"]

    st.subheader("Party Wise ITC Difference")

    st.dataframe(party_summary,use_container_width=True)


    # -------- EXPORT --------

    buffer=BytesIO()

    with pd.ExcelWriter(buffer) as writer:

        recon.to_excel(writer,"Full Reconciliation",index=False)

        recon[recon["Status"]=="Matched"].to_excel(writer,"Matched",index=False)

        recon[recon["Status"]=="Missing in 2B"].to_excel(writer,"Missing in 2B",index=False)

        recon[recon["Status"]=="Missing in Purchase"].to_excel(writer,"Missing in Purchase",index=False)

        party_summary.to_excel(writer,"Party Summary",index=False)

    st.download_button(

        label="Download GST Reconciliation Report",

        data=buffer.getvalue(),

        file_name="GST_Reconciliation_Report.xlsx",

        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
