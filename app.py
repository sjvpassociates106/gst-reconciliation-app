import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST 2B Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# -------------------------
# Clean invoice number
# A/123/23-24 -> 123
# -------------------------
def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    nums = re.findall(r"\d+", str(inv))

    return nums[0] if nums else ""


# -------------------------
# Safe numeric conversion
# -------------------------
def num(series):

    return pd.to_numeric(series, errors="coerce").fillna(0)


# -------------------------
# Normalize column names
# -------------------------
def normalize_columns(df):

    df.columns = (
        df.columns.astype(str)
        .str.lower()
        .str.replace("₹","", regex=False)
        .str.replace("(","", regex=False)
        .str.replace(")","", regex=False)
        .str.strip()
    )

    return df


# -------------------------
# Detect header row automatically
# -------------------------
def detect_header(file):

    temp = pd.read_excel(file, sheet_name="B2B", header=None)

    for i in range(20):

        row = " ".join(temp.iloc[i].astype(str).str.lower())

        if "gstin" in row and "invoice" in row:
            return i

    return None


# =========================
# PROCESS
# =========================
if gstr_file and purchase_file:

    header_row = detect_header(gstr_file)

    if header_row is None:
        st.error("Header row not found in B2B sheet")
        st.stop()

    gstr2b = pd.read_excel(gstr_file, sheet_name="B2B", header=header_row)

    gstr2b = normalize_columns(gstr2b)

    # detect columns
    gstin_col = [c for c in gstr2b.columns if "gstin" in c][0]
    invoice_col = [c for c in gstr2b.columns if "invoice" in c][0]
    taxable_col = [c for c in gstr2b.columns if "taxable" in c][0]
    igst_col = [c for c in gstr2b.columns if "integrated" in c][0]
    cgst_col = [c for c in gstr2b.columns if "central" in c][0]
    sgst_col = [c for c in gstr2b.columns if "state" in c][0]
    party_col = [c for c in gstr2b.columns if "trade" in c][0]

    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin_col].astype(str).str.upper().str.strip()
    df2b["Party"] = gstr2b[party_col]
    df2b["Invoice"] = gstr2b[invoice_col].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[taxable_col])
    df2b["IGST2B"] = num(gstr2b[igst_col])
    df2b["CGST2B"] = num(gstr2b[cgst_col])
    df2b["SGST2B"] = num(gstr2b[sgst_col])


    # -------------------------
    # Purchase Register
    # -------------------------
    purchase = pd.read_excel(purchase_file)

    purchase = normalize_columns(purchase)

    gstin_pr = [c for c in purchase.columns if "gst" in c][0]
    invoice_pr = [c for c in purchase.columns if "invoice" in c][0]
    taxable_pr = [c for c in purchase.columns if "taxable" in c][0]
    igst_pr = [c for c in purchase.columns if "igst" in c][0]
    cgst_pr = [c for c in purchase.columns if "cgst" in c][0]
    sgst_pr = [c for c in purchase.columns if "sgst" in c][0]
    party_pr = [c for c in purchase.columns if "particular" in c][0]

    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstin_pr].astype(str).str.upper().str.strip()
    dfpr["Party"] = purchase[party_pr]
    dfpr["Invoice"] = purchase[invoice_pr].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable_pr])
    dfpr["IGSTPR"] = num(purchase[igst_pr])
    dfpr["CGSTPR"] = num(purchase[cgst_pr])
    dfpr["SGSTPR"] = num(purchase[sgst_pr])


    # remove blank invoice
    df2b = df2b[df2b["Invoice"]!=""]
    dfpr = dfpr[dfpr["Invoice"]!=""]


    # merge
    recon = pd.merge(dfpr, df2b, on=["GSTIN","Invoice"], how="outer", indicator=True)


    # reconciliation logic
    def check(row):

        if row["_merge"] == "left_only":
            return pd.Series(["Mismatch","Missing in GSTR2B"])

        if row["_merge"] == "right_only":
            return pd.Series(["Mismatch","Missing in Purchase Register"])

        reasons = []

        if round(row["IGSTPR"],2) != round(row["IGST2B"],2):
            reasons.append("IGST mismatch")

        if round(row["CGSTPR"],2) != round(row["CGST2B"],2):
            reasons.append("CGST mismatch")

        if round(row["SGSTPR"],2) != round(row["SGST2B"],2):
            reasons.append("SGST mismatch")

        if not reasons:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]] = recon.apply(check, axis=1)

    recon = recon.drop(columns=["_merge"])


    st.subheader("Reconciliation Result")

    st.dataframe(recon, use_container_width=True)


    buffer = BytesIO()

    recon.to_excel(buffer, index=False)

    st.download_button(
        "Download Excel",
        buffer.getvalue(),
        "GST_Reconciliation_Output.xlsx"
    )
