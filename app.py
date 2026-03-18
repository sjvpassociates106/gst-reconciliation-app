import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST AI Reconciliation", layout="wide")
st.title("GST 2B vs Purchase Register (AI Reconciliation)")


gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# ================= FUNCTIONS =================

def clean_invoice(inv):
    if pd.isna(inv):
        return ""
    inv = str(inv).upper()

    # remove symbols
    inv = re.sub(r"[^A-Z0-9]", "", inv)

    # remove year
    inv = re.sub(r"20[0-9]{2}", "", inv)

    # extract numeric part
    nums = re.findall(r"\d+", inv)

    return nums[-1] if nums else inv


def num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


# ================= PROCESS =================

if gstr_file and purchase_file:

    # -------- LOAD GSTR2B --------
    gstr2b = pd.read_excel(gstr_file, sheet_name="B2B", header=2)
    gstr2b.columns = [' '.join([str(i) for i in col]).lower() for col in gstr2b.columns]

    gstin_col = party_col = invoice_col = None
    taxable_col = igst_col = cgst_col = sgst_col = None

for col in gstr2b.columns:

    c = str(col).lower()

    # clean
    c = c.replace("₹","")
    c = c.replace("(", "").replace(")", "")
    c = c.replace("/", " ")
    c = c.replace("-", " ")
    c = " ".join(c.split())

    # detection
    if "gstin" in c:
        gstin_col = col

    elif "trade" in c or "legal" in c:
        party_col = col

    elif "invoice" in c:
        invoice_col = col

    elif "taxable" in c:
        taxable_col = col

    elif "integrated" in c:
        igst_col = col

    elif "central" in c:
        cgst_col = col

    elif "state" in c or "ut" in c:
        sgst_col = col
    df2b = pd.DataFrame()

    df2b["GSTIN of Supplier"] = gstr2b[gstin_col]
    df2b["Party"] = gstr2b[party_col]
    df2b["Invoice"] = gstr2b[invoice_col].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[taxable_col])
    df2b["CGST2B"] = num(gstr2b[cgst_col])
    df2b["SGST2B"] = num(gstr2b[sgst_col])
    df2b["IGST2B"] = num(gstr2b[igst_col])

    # 🔥 REMOVE DUPLICATES (IMPORTANT)
    df2b = df2b.groupby(["GSTIN","Invoice"], as_index=False).sum()


    # -------- LOAD PURCHASE --------
    purchase = pd.read_excel(purchase_file)

    gstin_pr = party_pr = invoice_pr = None
    taxable_pr = igst_pr = cgst_pr = sgst_pr = None

    for col in purchase.columns:

        c = str(col).lower()

        if "gstin" in c:
            gstin_pr = col
        if "party" in c:
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

    dfpr["GSTIN"] = purchase[gstin_pr].astype(str).str.strip()
    dfpr["Party"] = purchase[party_pr]
    dfpr["Invoice"] = purchase[invoice_pr].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable_pr])
    dfpr["CGSTPR"] = num(purchase[cgst_pr])
    dfpr["SGSTPR"] = num(purchase[sgst_pr])
    dfpr["IGSTPR"] = num(purchase[igst_pr])

    # 🔥 REMOVE DUPLICATES
    dfpr = dfpr.groupby(["GSTIN","Invoice"], as_index=False).sum()


    # -------- MERGE --------
    recon = pd.merge(dfpr, df2b, on=["GSTIN","Invoice"], how="outer", indicator=True)


    # -------- CLEAN --------
    num_cols = [
        "TaxablePR","CGSTPR","SGSTPR","IGSTPR",
        "Taxable2B","CGST2B","SGST2B","IGST2B"
    ]

    for col in num_cols:
        if col in recon.columns:
            recon[col] = pd.to_numeric(recon[col], errors="coerce").fillna(0)

    recon["GSTIN"] = recon["GSTIN"].fillna("")
    recon["Invoice"] = recon["Invoice"].fillna("")


    # Party fix
    recon["Party"] = recon["Party_x"].fillna("")
    recon.loc[recon["Party"]=="","Party"] = recon["Party_y"]
    recon = recon.drop(columns=["Party_x","Party_y"])


    # -------- CHECK --------
    def check(r):

        if r["_merge"] == "left_only":
            return pd.Series(["Missing in 2B"])

        if r["_merge"] == "right_only":
            return pd.Series(["Missing in Purchase"])

        tol = 1
        reasons = []

        if abs(r["TaxablePR"] - r["Taxable2B"]) > tol:
            reasons.append("Taxable")

        if abs(r["CGSTPR"] - r["CGST2B"]) > tol:
            reasons.append("CGST")

        if abs(r["SGSTPR"] - r["SGST2B"]) > tol:
            reasons.append("SGST")

        if abs(r["IGSTPR"] - r["IGST2B"]) > tol:
            reasons.append("IGST")

        return pd.Series(["Matched" if not reasons else "Mismatch",
                          ",".join(reasons)])


    recon[["Status","Reason"]] = recon.apply(check, axis=1)
    recon = recon.drop(columns=["_merge"])


    # -------- FINAL FORMAT --------
    recon = recon.sort_values(by=["GSTIN","Invoice"])


    st.dataframe(recon, use_container_width=True)


    # -------- DOWNLOAD --------
    buffer = BytesIO()
    recon.to_excel(buffer, index=False)

    st.download_button(
        label="Download Final Reconciliation",
        data=buffer.getvalue(),
        file_name="GST_Final_Reconciliation.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="final_download"
    )
