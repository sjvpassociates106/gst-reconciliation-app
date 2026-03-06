import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="GST Reconciliation Tool", layout="wide")
st.title("GST 2B vs Purchase Register Reconciliation")


gstr_file = st.file_uploader("Upload GSTR-2B Excel", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# -------------------------------------------------
# Clean Invoice Function
# -------------------------------------------------

def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    inv = str(inv)

    parts = re.split(r"[/-]", inv)

    nums = []

    for p in parts:

        n = re.sub(r"\D","",p)

        if n:
            nums.append(n)

    if len(nums) >= 2:
        return nums[0] + nums[1]

    if len(nums) == 1:
        return nums[0]

    return ""


# -------------------------------------------------
# Column Finder
# -------------------------------------------------

def find_col(columns, keywords):

    for col in columns:

        name = str(col).lower()

        for k in keywords:
            if k in name:
                return col

    return None


# -------------------------------------------------
# Safe Numeric Conversion
# -------------------------------------------------

def safe_num(df, col):

    if col is None:
        return pd.Series([0]*len(df))

    return pd.to_numeric(df[col], errors="coerce").fillna(0)


# =================================================
# MAIN PROCESS
# =================================================

if gstr_file and purchase_file:

    # -----------------------------
    # LOAD GSTR-2B
    # -----------------------------

    xl = pd.ExcelFile(gstr_file)

    if "B2B" not in xl.sheet_names:
        st.error("B2B sheet not found in GSTR-2B")
        st.stop()

    gstr2b = xl.parse("B2B")
    gstr2b.columns = gstr2b.columns.str.strip()


    gstin2b = find_col(gstr2b.columns, ["gstin"])
    party2b = find_col(gstr2b.columns, ["trade"])
    inv2b   = find_col(gstr2b.columns, ["invoice"])

    igst2b  = find_col(gstr2b.columns, ["integrated"])
    cgst2b  = find_col(gstr2b.columns, ["central"])
    sgst2b  = find_col(gstr2b.columns, ["state"])


    # -----------------------------
    # LOAD PURCHASE REGISTER
    # -----------------------------

    purchase = pd.read_excel(purchase_file)
    purchase.columns = purchase.columns.str.strip()


    gstinpr = find_col(purchase.columns, ["gstin"])
    invpr   = find_col(purchase.columns, ["invoice"])
    partypr = find_col(purchase.columns, ["particular"])

    igstpr  = find_col(purchase.columns, ["igst"])
    cgstpr  = find_col(purchase.columns, ["cgst"])
    sgstpr  = find_col(purchase.columns, ["sgst"])


    # -----------------------------
    # CLEAN DATAFRAMES
    # -----------------------------

    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin2b].astype(str).str.upper().str.strip()
    df2b["Invoice"] = gstr2b[inv2b].apply(clean_invoice)
    df2b["Party"] = gstr2b[party2b].astype(str).str.strip()

    df2b["IGST2B"] = safe_num(gstr2b, igst2b)
    df2b["CGST2B"] = safe_num(gstr2b, cgst2b)
    df2b["SGST2B"] = safe_num(gstr2b, sgst2b)


    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstinpr].astype(str).str.upper().str.strip()
    dfpr["Invoice"] = purchase[invpr].apply(clean_invoice)
    dfpr["Party"] = purchase[partypr].astype(str).str.strip()

    dfpr["IGSTPR"] = safe_num(purchase, igstpr)
    dfpr["CGSTPR"] = safe_num(purchase, cgstpr)
    dfpr["SGSTPR"] = safe_num(purchase, sgstpr)


    df2b = df2b.dropna(subset=["GSTIN","Invoice"])
    dfpr = dfpr.dropna(subset=["GSTIN","Invoice"])


    # -----------------------------
    # MERGE
    # -----------------------------

    recon = pd.merge(
        dfpr,
        df2b,
        on=["GSTIN","Invoice"],
        how="outer",
        indicator=True
    )


    # -----------------------------
    # RECONCILIATION LOGIC
    # -----------------------------

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


    # -----------------------------
    # EXPORT
    # -----------------------------

    output = "GST_Reconciliation_Output.xlsx"

    recon.to_excel(output, index=False)

    with open(output,"rb") as f:

        st.download_button(
            "Download Reconciliation Excel",
            data=f,
            file_name=output
        )
