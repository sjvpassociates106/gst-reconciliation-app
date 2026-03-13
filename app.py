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

    inv = str(inv).upper()

    inv = re.sub(r"[^A-Z0-9]", "", inv)

    nums = re.findall(r"\d+", inv)

    if nums:
        return nums[-1]

    return inv


def num(series):

    return (
        series.astype(str)
        .str.replace("₹","",regex=False)
        .str.replace(",","",regex=False)
        .replace("",0)
        .astype(float)
    )


def detect_header(file):

    temp = pd.read_excel(file, header=None)

    for i in range(20):

        row = " ".join(temp.iloc[i].astype(str).str.lower())

        if "invoice" in row or "voucher" in row:
            return i

    return 0


def find_column(columns, keywords):

    for col in columns:

        c = str(col).lower()

        for key in keywords:

            if key in c:
                return col

    return None


# ---------------- PROCESS ----------------

if gstr_file and purchase_file:


    # -------- LOAD GSTR2B --------

    gstr = pd.read_excel(gstr_file, sheet_name="B2B")

    gstin_col = find_column(gstr.columns,["gstin"])
    party_col = find_column(gstr.columns,["trade","legal"])
    invoice_col = find_column(gstr.columns,["invoice"])
    taxable_col = find_column(gstr.columns,["taxable"])
    igst_col = find_column(gstr.columns,["integrated","igst"])
    cgst_col = find_column(gstr.columns,["central","cgst"])
    sgst_col = find_column(gstr.columns,["state","sgst"])


    if invoice_col is None:
        st.error("Invoice column not found in GSTR-2B")
        st.write(gstr.columns)
        st.stop()


    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr[gstin_col].astype(str) if gstin_col else "UNKNOWN"
    df2b["Party"] = gstr[party_col] if party_col else "UNKNOWN"
    df2b["Invoice"] = gstr[invoice_col].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr[taxable_col]) if taxable_col else 0
    df2b["IGST2B"] = num(gstr[igst_col]) if igst_col else 0
    df2b["CGST2B"] = num(gstr[cgst_col]) if cgst_col else 0
    df2b["SGST2B"] = num(gstr[sgst_col]) if sgst_col else 0

    df2b = df2b.dropna(subset=["Invoice"])



    # -------- LOAD PURCHASE REGISTER --------

    header = detect_header(purchase_file)

    purchase = pd.read_excel(purchase_file, header=header)


    gstin_pr = find_column(purchase.columns,["gstin"])
    party_pr = find_column(purchase.columns,["particular","party","supplier"])
    invoice_pr = find_column(purchase.columns,["invoice","voucher"])
    taxable_pr = find_column(purchase.columns,["taxable"])
    igst_pr = find_column(purchase.columns,["igst"])
    cgst_pr = find_column(purchase.columns,["cgst"])
    sgst_pr = find_column(purchase.columns,["sgst"])


    if invoice_pr is None:
        st.error("Invoice column not found in Purchase Register")
        st.write("Columns:", purchase.columns)
        st.stop()


    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstin_pr] if gstin_pr else "UNKNOWN"
    dfpr["Party"] = purchase[party_pr] if party_pr else "UNKNOWN"
    dfpr["Invoice"] = purchase[invoice_pr].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable_pr]) if taxable_pr else 0
    dfpr["IGSTPR"] = num(purchase[igst_pr]) if igst_pr else 0
    dfpr["CGSTPR"] = num(purchase[cgst_pr]) if cgst_pr else 0
    dfpr["SGSTPR"] = num(purchase[sgst_pr]) if sgst_pr else 0

    dfpr = dfpr.dropna(subset=["Invoice"])



    # -------- MERGE --------

    recon = dfpr.merge(df2b, on="Invoice", how="outer", indicator=True)

    recon["Status"] = "Matched"

    recon.loc[recon["_merge"]=="left_only","Status"] = "Missing in 2B"

    recon.loc[recon["_merge"]=="right_only","Status"] = "Missing in Purchase"



    # -------- DASHBOARD --------

    st.subheader("Reconciliation Summary")

    c1,c2,c3,c4 = st.columns(4)

    c1.metric("Total Invoices", len(recon))
    c2.metric("Matched", len(recon[recon["Status"]=="Matched"]))
    c3.metric("Missing in 2B", len(recon[recon["Status"]=="Missing in 2B"]))
    c4.metric("Missing in Purchase", len(recon[recon["Status"]=="Missing in Purchase"]))



    # -------- RESULT --------

    st.subheader("Reconciliation Output")

    st.dataframe(recon, use_container_width=True)



    # -------- EXPORT --------

    buffer = BytesIO()

    with pd.ExcelWriter(buffer) as writer:

        recon.to_excel(writer,"Full Reconciliation",index=False)

        recon[recon["Status"]=="Matched"].to_excel(writer,"Matched",index=False)

        recon[recon["Status"]=="Missing in 2B"].to_excel(writer,"Missing in 2B",index=False)

        recon[recon["Status"]=="Missing in Purchase"].to_excel(writer,"Missing in Purchase",index=False)


    st.download_button(
        label="Download GST Reconciliation Report",
        data=buffer.getvalue(),
        file_name="GST_Reconciliation_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
