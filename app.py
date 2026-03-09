import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST 2B Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# -------------------------
# Clean invoice
# A/123/23-24 → 123
# -------------------------
def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    nums = re.findall(r"\d+", str(inv))

    if nums:
        return nums[0]

    return ""


# -------------------------
# Safe numeric
# -------------------------
def num(x):
    return pd.to_numeric(x, errors="coerce").fillna(0)


# -------------------------
# Normalize column names
# -------------------------
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


# =========================
# PROCESS
# =========================
if gstr_file and purchase_file:

    # -------------------------
    # Load B2B Sheet
    # -------------------------
    xl = pd.ExcelFile(gstr_file)

    gstr2b = xl.parse("B2B", header=3)

    gstr2b = normalize(gstr2b)

    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b["GSTIN of supplier"].astype(str).str.strip().str.upper()

    df2b["Party"] = gstr2b["trade/legal name"]

    # invoice details column used
    df2b["Invoice"] = gstr2b["invoice details"].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b["taxable value"])

    df2b["IGST2B"] = num(gstr2b["integrated tax"])
    df2b["CGST2B"] = num(gstr2b["central tax"])
    df2b["SGST2B"] = num(gstr2b["state/ut tax"])


    # -------------------------
    # Purchase Register
    # -------------------------
    purchase = pd.read_excel(purchase_file)

    purchase = normalize(purchase)

    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase["gstin/uin"].astype(str).str.strip().str.upper()

    dfpr["Party"] = purchase["particular"]

    dfpr["Invoice"] = purchase["supplier invoice number"].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase["taxable value"])

    dfpr["IGSTPR"] = num(purchase["igst"])
    dfpr["CGSTPR"] = num(purchase["cgst"])
    dfpr["SGSTPR"] = num(purchase["sgst"])


    # remove empty invoice
    df2b = df2b[df2b["Invoice"]!=""]
    dfpr = dfpr[dfpr["Invoice"]!=""]


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
    # Reconciliation Logic
    # -------------------------
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


    # -------------------------
    # Summary
    # -------------------------
    st.subheader("Summary")

    c1,c2,c3 = st.columns(3)

    c1.metric("Total Records",len(recon))
    c2.metric("Matched",(recon["Status"]=="Matched").sum())
    c3.metric("Mismatch",(recon["Status"]=="Mismatch").sum())


    # result
    st.subheader("Reconciliation Result")

    st.dataframe(recon,use_container_width=True)


    # excel download
    buffer = BytesIO()

    recon.to_excel(buffer,index=False)

    st.download_button(
        "Download Excel Report",
        buffer.getvalue(),
        "GST_Reconciliation_Output.xlsx"
    )
