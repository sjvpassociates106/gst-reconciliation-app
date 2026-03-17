import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls", "xlsx"])


# ---------------- FUNCTIONS ---------------- #

def clean_invoice(inv):
    if pd.isna(inv):
        return ""
    inv = str(inv).upper()
    inv = inv.replace(" ", "")
    inv = re.sub(r"[^A-Z0-9]", "", inv)
    numbers = re.findall(r"\d+", inv)
    return numbers[-1] if numbers else inv


def num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def detect_header(file, sheet):
    temp = pd.read_excel(file, sheet_name=sheet, header=None)
    for i in range(20):
        row = " ".join(temp.iloc[i].astype(str).str.lower())
        if "invoice" in row and "gstin" in row:
            return i
    return 0


def detect_invoice_column(df):
    patterns = ["invoice", "inv", "bill", "doc", "voucher"]
    for col in df.columns:
        c = str(col).lower()
        for p in patterns:
            if p in c:
                return col

    # fallback AI pattern
    for col in df.columns:
        sample = df[col].astype(str).head(20)
        if sample.str.contains(r"\d", regex=True).sum() > 10:
            return col

    return None


def detect_gst_columns(df):

    igst = cgst = sgst = taxable = None

    for col in df.columns:
        c = str(col).lower()

        if "integrated" in c or "igst" in c:
            igst = col

        elif "central" in c or "cgst" in c:
            cgst = col

        elif "state" in c or "sgst" in c:
            sgst = col

        elif "taxable" in c:
            taxable = col

    return taxable, igst, cgst, sgst


# ---------------- MAIN PROCESS ---------------- #

if gstr_file and purchase_file:

    # -------- GSTR2B -------- #

    header2b = detect_header(gstr_file, "B2B")
    gstr2b = pd.read_excel(gstr_file, sheet_name="B2B", header=header2b)

    invoice_col_2b = detect_invoice_column(gstr2b)

    if invoice_col_2b is None:
        st.error("Invoice column not found in GSTR2B")
        st.write(list(gstr2b.columns))
        st.stop()

    taxable_2b, igst_2b, cgst_2b, sgst_2b = detect_gst_columns(gstr2b)

    df2b = pd.DataFrame()
    df2b["Invoice"] = gstr2b[invoice_col_2b].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[taxable_2b]) if taxable_2b else 0
    df2b["IGST2B"] = num(gstr2b[igst_2b]) if igst_2b else 0
    df2b["CGST2B"] = num(gstr2b[cgst_2b]) if cgst_2b else 0
    df2b["SGST2B"] = num(gstr2b[sgst_2b]) if sgst_2b else 0

    df2b = df2b.groupby("Invoice", as_index=False).sum()

    # -------- PURCHASE -------- #

    purchase = pd.read_excel(purchase_file)

    invoice_col_pr = detect_invoice_column(purchase)

    if invoice_col_pr is None:
        st.error("Invoice column not found in Purchase Register")
        st.write(list(purchase.columns))
        st.stop()

    taxable_pr, igst_pr, cgst_pr, sgst_pr = detect_gst_columns(purchase)

    dfpr = pd.DataFrame()
    dfpr["Invoice"] = purchase[invoice_col_pr].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable_pr]) if taxable_pr else 0
    dfpr["IGSTPR"] = num(purchase[igst_pr]) if igst_pr else 0
    dfpr["CGSTPR"] = num(purchase[cgst_pr]) if cgst_pr else 0
    dfpr["SGSTPR"] = num(purchase[sgst_pr]) if sgst_pr else 0

    dfpr = dfpr.groupby("Invoice", as_index=False).sum()

    # -------- MERGE -------- #

    recon = pd.merge(dfpr, df2b, on="Invoice", how="outer", indicator=True)

    # -------- CHECK -------- #

    def check(r):

        if r["_merge"] == "left_only":
            return pd.Series(["Mismatch", "Missing in 2B"])

        if r["_merge"] == "right_only":
            return pd.Series(["Mismatch", "Missing in Purchase"])

        tol = 1
        reasons = []

        if abs(r["TaxablePR"] - r["Taxable2B"]) > tol:
            reasons.append("Taxable mismatch")

        if abs(r["IGSTPR"] - r["IGST2B"]) > tol:
            reasons.append("IGST mismatch")

        if abs(r["CGSTPR"] - r["CGST2B"]) > tol:
            reasons.append("CGST mismatch")

        if abs(r["SGSTPR"] - r["SGST2B"]) > tol:
            reasons.append("SGST mismatch")

        if not reasons:
            return pd.Series(["Matched", ""])

        return pd.Series(["Mismatch", ",".join(reasons)])


    recon[["Status", "Reason"]] = recon.apply(check, axis=1)
    recon = recon.drop(columns=["_merge"])

    # -------- OUTPUT -------- #

    st.subheader("Reconciliation Result")
    st.dataframe(recon, use_container_width=True)

    # -------- DOWNLOAD -------- #

    buffer = BytesIO()
    recon.to_excel(buffer, index=False)

    st.download_button(
        label="Download Excel Report",
        data=buffer.getvalue(),
        file_name="GST_Reconciliation_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
