import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")


gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx","xls"])


# -----------------------------
# CLEAN COLUMN NAME
# -----------------------------
def clean(col):

    col = str(col).lower()
    col = col.replace("₹","")

    col = re.sub(r'[^a-z0-9]','',col)

    return col


# -----------------------------
# FIND COLUMN
# -----------------------------
def find_column(columns, keys):

    for col in columns:

        c = clean(col)

        for k in keys:

            if k in c:
                return col

    return None


# -----------------------------
# SAFE NUMBER COLUMN
# -----------------------------
def safe_get(df, col):

    if col is None:
        return pd.Series([0]*len(df))

    if col not in df.columns:
        return pd.Series([0]*len(df))

    return pd.to_numeric(df[col], errors="coerce").fillna(0)


# -----------------------------
# CLEAN INVOICE
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
# LOAD GSTR2B B2B SHEET
# -----------------------------
def load_2b(file):

    xl = pd.ExcelFile(file)

    df = xl.parse("B2B")

    df.columns = df.columns.str.strip()

    return df


# -----------------------------
# LOAD PURCHASE REGISTER
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
# PROCESS
# -----------------------------
if gstr2b_file and purchase_file:

    gstr2b = load_2b(gstr2b_file)

    purchase = load_purchase(purchase_file)


    # -------- detect columns --------

    gstin2b = find_column(gstr2b.columns, ["gstin"])

    inv2b = find_column(gstr2b.columns, ["invoice"])

    igst2b = find_column(gstr2b.columns, ["integratedtax"])

    cgst2b = find_column(gstr2b.columns, ["centraltax"])

    sgst2b = find_column(gstr2b.columns, ["statetax","uttax"])


    gstinpr = find_column(purchase.columns, ["gstinuin","gstin"])

    invpr = find_column(purchase.columns, ["invoice"])

    igstpr = find_column(purchase.columns, ["igst"])

    cgstpr = find_column(purchase.columns, ["cgst"])

    sgstpr = find_column(purchase.columns, ["sgst"])


    # -------- build dataframe safely --------

    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin2b].astype(str).str.upper().str.strip() if gstin2b else pd.Series()

    df2b["Invoice"] = gstr2b[inv2b].apply(clean_invoice) if inv2b else pd.Series()

    df2b["IGST2B"] = safe_get(gstr2b, igst2b)

    df2b["CGST2B"] = safe_get(gstr2b, cgst2b)

    df2b["SGST2B"] = safe_get(gstr2b, sgst2b)



    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstinpr].astype(str).str.upper().str.strip() if gstinpr else pd.Series()

    dfpr["Invoice"] = purchase[invpr].apply(clean_invoice) if invpr else pd.Series()

    dfpr["IGSTPR"] = safe_get(purchase, igstpr)

    dfpr["CGSTPR"] = safe_get(purchase, cgstpr)

    dfpr["SGSTPR"] = safe_get(purchase, sgstpr)


    # -------- merge --------

    recon = pd.merge(dfpr, df2b, on=["GSTIN","Invoice"], how="outer", indicator=True)


    # -------- mismatch logic --------

    def check(r):

        if r["_merge"] == "left_only":
            return pd.Series(["Mismatch","Missing in 2B"])

        if r["_merge"] == "right_only":
            return pd.Series(["Mismatch","Missing in Purchase"])

        reasons = []

        if round(r["IGSTPR"],2) != round(r["IGST2B"],2):
            reasons.append("IGST mismatch")

        if round(r["CGSTPR"],2) != round(r["CGST2B"],2):
            reasons.append("CGST mismatch")

        if round(r["SGSTPR"],2) != round(r["SGST2B"],2):
            reasons.append("SGST mismatch")

        if len(reasons) == 0:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]] = recon.apply(check, axis=1)

    recon = recon.drop(columns=["_merge"])


    st.subheader("Reconciliation Result")

    st.dataframe(recon, use_container_width=True)


    # -------- export --------

    output = "GST_Reconciliation_Output.xlsx"

    recon.to_excel(output, index=False)

    with open(output,"rb") as f:

        st.download_button(
            "Download Excel",
            data=f,
            file_name=output
        )
