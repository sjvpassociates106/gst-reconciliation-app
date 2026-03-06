import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="GST Reconciliation", layout="wide")
st.title("GST 2B vs Purchase Register Reconciliation")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx","xls"])


# -----------------------------
# Clean column names
# -----------------------------
def clean(col):
    col = str(col).lower()
    col = col.replace("₹","")
    col = re.sub(r'[^a-z0-9]','',col)
    return col


# -----------------------------
# Find column
# -----------------------------
def find_column(columns, keys):

    for col in columns:

        c = clean(col)

        for k in keys:

            if k in c:
                return col

    return None


# -----------------------------
# Safe number column
# -----------------------------
def safe_get(df, col):

    if col is None:
        return pd.Series([0]*len(df))

    if col not in df.columns:
        return pd.Series([0]*len(df))

    return pd.to_numeric(df[col], errors="coerce").fillna(0)


# -----------------------------
# Clean invoice number
# -----------------------------
def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    inv = str(inv)

    parts = re.split(r'[/-]', inv)

    numbers = []

    for p in parts:

        num = re.sub(r'\D','',p)

        if num:
            numbers.append(num)

    if len(numbers) >= 2:
        return numbers[0] + numbers[1]

    if len(numbers) == 1:
        return numbers[0]

    return ""


# -----------------------------
# Load GSTR2B
# -----------------------------
def load_2b(file):

    xl = pd.ExcelFile(file)

    if "B2B" not in xl.sheet_names:
        st.error("B2B sheet not found in GSTR2B")
        st.stop()

    df = xl.parse("B2B")

    df.columns = df.columns.str.strip()

    return df


# -----------------------------
# Load Purchase Register
# -----------------------------
def load_purchase(file):

    raw = pd.read_excel(file, header=None)

    header = 0

    for i in range(len(raw)):

        row = raw.iloc[i].astype(str).str.lower()

        if any("gstin" in x for x in row):
            header = i
            break

    df = pd.read_excel(file, header=header)

    df.columns = df.columns.str.strip()

    return df


# -----------------------------
# MAIN PROCESS
# -----------------------------
if gstr2b_file and purchase_file:

    gstr2b = load_2b(gstr2b_file)
    purchase = load_purchase(purchase_file)


    # Detect columns in GSTR2B

    gstin2b = find_column(gstr2b.columns, ["gstin"])
    inv2b = find_column(gstr2b.columns, ["invoicenumber","invoice"])

    igst2b = find_column(gstr2b.columns, ["integratedtax"])
    cgst2b = find_column(gstr2b.columns, ["centraltax"])
    sgst2b = find_column(gstr2b.columns, ["statetax","uttax"])


    # Detect columns in Purchase Register

    gstinpr = find_column(purchase.columns, ["gstinuin","gstin"])
    invpr = find_column(purchase.columns, ["invoice"])

    igstpr = find_column(purchase.columns, ["igst"])
    cgstpr = find_column(purchase.columns, ["cgst"])
    sgstpr = find_column(purchase.columns, ["sgst"])


    # Create standardized tables

    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin2b].astype(str).str.upper().str.strip()
    df2b["Invoice"] = gstr2b[inv2b].apply(clean_invoice)

    df2b["IGST2B"] = safe_get(gstr2b, igst2b)
    df2b["CGST2B"] = safe_get(gstr2b, cgst2b)
    df2b["SGST2B"] = safe_get(gstr2b, sgst2b)


    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstinpr].astype(str).str.upper().str.strip()
    dfpr["Invoice"] = purchase[invpr].apply(clean_invoice)

    dfpr["IGSTPR"] = safe_get(purchase, igstpr)
    dfpr["CGSTPR"] = safe_get(purchase, cgstpr)
    dfpr["SGSTPR"] = safe_get(purchase, sgstpr)


    # Remove blank rows

    df2b = df2b.dropna(subset=["GSTIN","Invoice"])
    dfpr = dfpr.dropna(subset=["GSTIN","Invoice"])


    # Merge data

    recon = pd.merge(
        dfpr,
        df2b,
        on=["GSTIN","Invoice"],
        how="outer",
        indicator=True
    )


    # Reconciliation logic

    def check(row):

        if row["_merge"] == "left_only":
            return pd.Series(["Mismatch","Missing in 2B"])

        if row["_merge"] == "right_only":
            return pd.Series(["Mismatch","Missing in Purchase"])

        reasons = []

        if round(row["IGSTPR"],2) != round(row["IGST2B"],2):
            reasons.append("IGST mismatch")

        if round(row["CGSTPR"],2) != round(row["CGST2B"],2):
            reasons.append("CGST mismatch")

        if round(row["SGSTPR"],2) != round(row["SGST2B"],2):
            reasons.append("SGST mismatch")

        if len(reasons) == 0:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]] = recon.apply(check, axis=1)

    recon = recon.drop(columns=["_merge"])


    st.subheader("Reconciliation Result")

    st.dataframe(recon, use_container_width=True)


    # Export Excel

    output_file = "GST_Reconciliation_Output.xlsx"

    recon.to_excel(output_file, index=False)

    with open(output_file,"rb") as f:

        st.download_button(
            "Download Excel",
            data=f,
            file_name=output_file
        )
