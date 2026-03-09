import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation Tool", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# ------------------------------
# Invoice cleaning
# A/123/23-24 → 123
# ------------------------------
def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    nums = re.findall(r"\d+", str(inv))

    if nums:
        return nums[0]

    return ""


# ------------------------------
# Safe numeric
# ------------------------------
def num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


# ------------------------------
# Normalize column names
# ------------------------------
def normalize(df):

    cols = []

    for c in df.columns:

        c = str(c).lower()
        c = c.replace("₹","")
        c = c.replace("(","")
        c = c.replace(")","")
        c = c.strip()

        cols.append(c)

    df.columns = cols

    return df


# ------------------------------
# Find column
# ------------------------------
def find_column(columns, keyword):

    for c in columns:

        if keyword in c:
            return c

    return None


# ===============================
# PROCESS
# ===============================
if gstr_file and purchase_file:

    # ------------------------------
    # Load GSTR-2B B2B
    # ------------------------------
    xl = pd.ExcelFile(gstr_file)

    raw = xl.parse("B2B", header=None)

    header_row = 0

    for i in range(10):

        row = raw.iloc[i].astype(str).str.lower()

        if "gstin" in " ".join(row) and "invoice" in " ".join(row):

            header_row = i
            break


    gstr2b = xl.parse("B2B", header=header_row)

    gstr2b = normalize(gstr2b)


    gstin_col = find_column(gstr2b.columns,"gstin")
    party_col = find_column(gstr2b.columns,"trade")
    invoice_col = find_column(gstr2b.columns,"invoice")
    taxable_col = find_column(gstr2b.columns,"taxable")
    igst_col = find_column(gstr2b.columns,"integrated")
    cgst_col = find_column(gstr2b.columns,"central")
    sgst_col = find_column(gstr2b.columns,"state")


    # Validate columns
    required = [gstin_col,invoice_col,taxable_col,igst_col,cgst_col,sgst_col]

    if None in required:

        st.error("Some required columns missing in GSTR-2B B2B sheet")

        st.write("Detected Columns:", gstr2b.columns)

        st.stop()


    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin_col].astype(str).str.upper().str.strip()
    df2b["Party"] = gstr2b[party_col]
    df2b["Invoice"] = gstr2b[invoice_col].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[taxable_col])
    df2b["IGST2B"] = num(gstr2b[igst_col])
    df2b["CGST2B"] = num(gstr2b[cgst_col])
    df2b["SGST2B"] = num(gstr2b[sgst_col])


    # ------------------------------
    # Load Purchase Register
    # ------------------------------
    purchase = pd.read_excel(purchase_file)

    purchase = normalize(purchase)


    gstin_pr = find_column(purchase.columns,"gst")
    party_pr = find_column(purchase.columns,"particular")
    invoice_pr = find_column(purchase.columns,"invoice")
    taxable_pr = find_column(purchase.columns,"taxable")
    igst_pr = find_column(purchase.columns,"igst")
    cgst_pr = find_column(purchase.columns,"cgst")
    sgst_pr = find_column(purchase.columns,"sgst")


    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstin_pr].astype(str).str.upper().str.strip()
    dfpr["Party"] = purchase[party_pr]
    dfpr["Invoice"] = purchase[invoice_pr].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable_pr])
    dfpr["IGSTPR"] = num(purchase[igst_pr])
    dfpr["CGSTPR"] = num(purchase[cgst_pr])
    dfpr["SGSTPR"] = num(purchase[sgst_pr])


    # remove empty invoices
    df2b = df2b[df2b["Invoice"]!=""]
    dfpr = dfpr[dfpr["Invoice"]!=""]


    # ------------------------------
    # Merge
    # ------------------------------
    recon = pd.merge(
        dfpr,
        df2b,
        on=["GSTIN","Invoice"],
        how="outer",
        indicator=True
    )


    # ------------------------------
    # Reconciliation logic
    # ------------------------------
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


    # ------------------------------
    # Dashboard
    # ------------------------------
    st.subheader("Summary")

    c1,c2,c3 = st.columns(3)

    c1.metric("Total Records",len(recon))
    c2.metric("Matched",(recon["Status"]=="Matched").sum())
    c3.metric("Mismatch",(recon["Status"]=="Mismatch").sum())


    st.subheader("Reconciliation Result")

    st.dataframe(recon,use_container_width=True)


    # ------------------------------
    # Excel Download
    # ------------------------------
    buffer = BytesIO()

    recon.to_excel(buffer,index=False)

    st.download_button(
        "Download Excel Report",
        buffer.getvalue(),
        "GST_Reconciliation_Output.xlsx"
    )
