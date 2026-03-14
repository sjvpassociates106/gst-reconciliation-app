import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])

def detect_invoice_column(df):

    # Step 1: Try by column name
    patterns = ["invoice", "inv", "bill", "doc", "voucher"]

    for col in df.columns:
        c = str(col).lower()
        for p in patterns:
            if p in c:
                return col

    # Step 2: Try by data pattern (AI-like detection)
    for col in df.columns:

        sample = df[col].astype(str).head(20)

        match_count = sample.str.contains(r"[A-Za-z]*\d+", regex=True).sum()

        if match_count > 10:  # many values look like invoice numbers
            return col

    return None

# -------- Functions --------

def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    inv = str(inv).upper()
    inv = inv.replace(" ", "")
    inv = re.sub(r"[^A-Z0-9]", "", inv)

    numbers = re.findall(r"\d+", inv)

    if numbers:
        return numbers[-1]

    return inv


def num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


# -------- Process --------

if gstr_file and purchase_file:

    # -------- GSTR2B --------

   import pandas as pd

def load_gstr2b(file):

    temp = pd.read_excel(file, sheet_name="B2B", header=None)

    header_row = None

    for i in range(20):

        row = " ".join(temp.iloc[i].astype(str).str.lower())

        if "invoice" in row and "gstin" in row:
            header_row = i
            break

    if header_row is None:
        raise Exception("Cannot detect header row in GSTR2B")

    df = pd.read_excel(file, sheet_name="B2B", header=header_row)

    return df


gstr2b = load_gstr2b(gstr_file)
invoice_col = None

for col in gstr2b.columns:

    c = str(col).lower()

    if "invoice" in c:
        invoice_col = col
        break


if invoice_col is None:
    st.write("Available columns in GSTR2B:")
    st.write(list(gstr2b.columns))
    st.error("Invoice column not found in GSTR2B")
    st.stop()
    taxable_col = None
    igst_col = None
    cgst_col = None
    sgst_col = None

    for col in gstr2b.columns:

        c = str(col).lower()

        if "invoice" in c and invoice_col is None:
            invoice_col = col

        if "taxable" in c:
            taxable_col = col

        if "integrated" in c:
            igst_col = col

        if "central" in c:
            cgst_col = col

        if "state" in c:
            sgst_col = col


    if invoice_col is None:
        st.error("Invoice column not found in GSTR2B")
        st.stop()


    df2b = pd.DataFrame()

    df2b["Invoice"] = gstr2b[invoice_col].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[taxable_col]) if taxable_col else 0
    df2b["IGST2B"] = num(gstr2b[igst_col]) if igst_col else 0
    df2b["CGST2B"] = num(gstr2b[cgst_col]) if cgst_col else 0
    df2b["SGST2B"] = num(gstr2b[sgst_col]) if sgst_col else 0


    df2b = df2b.groupby("Invoice", as_index=False).sum()


    # -------- Purchase Register --------

    purchase = pd.read_excel(purchase_file)

    invoice_pr = None
    taxable_pr = None
    igst_pr = None
    cgst_pr = None
    sgst_pr = None

    for col in purchase.columns:

        c = str(col).lower()

        if "invoice" in c and invoice_pr is None:
            invoice_pr = col

        if "taxable" in c:
            taxable_pr = col

        if "igst" in c:
            igst_pr = col

        if "cgst" in c:
            cgst_pr = col

        if "sgst" in c:
            sgst_pr = col


    if invoice_pr is None:
        st.error("Invoice column not found in Purchase Register")
        st.stop()


    dfpr = pd.DataFrame()

    dfpr["Invoice"] = purchase[invoice_pr].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable_pr]) if taxable_pr else 0
    dfpr["IGSTPR"] = num(purchase[igst_pr]) if igst_pr else 0
    dfpr["CGSTPR"] = num(purchase[cgst_pr]) if cgst_pr else 0
    dfpr["SGSTPR"] = num(purchase[sgst_pr]) if sgst_pr else 0


    dfpr = dfpr.groupby("Invoice", as_index=False).sum()


    # -------- Merge --------

    recon = pd.merge(
        dfpr,
        df2b,
        on="Invoice",
        how="outer",
        indicator=True
    )


    # -------- Reconciliation --------

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

        if len(reasons) == 0:
            return pd.Series(["Matched", ""])

        return pd.Series(["Mismatch", ",".join(reasons)])


    recon[["Status","Reason"]] = recon.apply(check, axis=1)

    recon = recon.drop(columns=["_merge"])


    st.subheader("Reconciliation Result")

    st.dataframe(recon, use_container_width=True)


    # -------- Download Excel --------

    buffer = BytesIO()
    recon.to_excel(buffer, index=False)

    st.download_button(
        label="Download Excel Report",
        data=buffer.getvalue(),
        file_name="GST_Reconciliation_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
