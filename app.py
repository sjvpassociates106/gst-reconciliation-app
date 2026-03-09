import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST 2B Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# -----------------------------
# Clean Invoice
# -----------------------------
def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    nums = re.findall(r'\d+', str(inv))

    if nums:
        return nums[0]

    return ""


# -----------------------------
# Convert number safely
# -----------------------------
def num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


# -----------------------------
# Detect header row automatically
# -----------------------------
def load_gstr2b(file):

    xl = pd.ExcelFile(file)

    sheet = xl.parse("B2B", header=None)

    header_row = None

    for i in range(10):

        row = sheet.iloc[i].astype(str).str.lower()

        if "gstin" in " ".join(row.values) and "invoice" in " ".join(row.values):
            header_row = i
            break

    if header_row is None:
        st.error("Could not detect header row in B2B sheet")
        st.stop()

    df = xl.parse("B2B", header=header_row)

    df.columns = df.columns.astype(str).str.strip()

    return df


# =============================
# PROCESS
# =============================
if gstr_file and purchase_file:

    # -----------------------------
    # Load GSTR2B
    # -----------------------------
    gstr2b = load_gstr2b(gstr_file)

    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b["GSTIN of supplier"].astype(str).str.upper().str.strip()
    df2b["Party"] = gstr2b["Trade/Legal name"]
    df2b["Invoice"] = gstr2b["Invoice number"].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b["Taxable Value"])
    df2b["IGST2B"] = num(gstr2b["Integrated Tax(₹)"])
    df2b["CGST2B"] = num(gstr2b["Central Tax(₹)"])
    df2b["SGST2B"] = num(gstr2b["State/UT Tax(₹)"])


    # -----------------------------
    # Load Purchase Register
    # -----------------------------
    purchase = pd.read_excel(purchase_file)

    purchase.columns = purchase.columns.astype(str).str.strip()

    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase["GSTiN/UIN"].astype(str).str.upper().str.strip()
    dfpr["Party"] = purchase["Particular"]
    dfpr["Invoice"] = purchase["Supplier Invoice Number"].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase["Taxable Value"])
    dfpr["IGSTPR"] = num(purchase["IGST"])
    dfpr["CGSTPR"] = num(purchase["CGST"])
    dfpr["SGSTPR"] = num(purchase["SGST"])


    # Remove blank invoice
    df2b = df2b[df2b["Invoice"] != ""]
    dfpr = dfpr[dfpr["Invoice"] != ""]


    # -----------------------------
    # Merge
    # -----------------------------
    recon = pd.merge(
        dfpr,
        df2b,
        on=["GSTIN","Invoice"],
        how="outer",
        indicator=True
    )


    # -----------------------------
    # Reconciliation Logic
    # -----------------------------
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


    # -----------------------------
    # Dashboard
    # -----------------------------
    st.subheader("Summary")

    c1,c2,c3 = st.columns(3)

    c1.metric("Total Records",len(recon))
    c2.metric("Matched",(recon["Status"]=="Matched").sum())
    c3.metric("Mismatch",(recon["Status"]=="Mismatch").sum())


    # -----------------------------
    # Result Table
    # -----------------------------
    st.subheader("Reconciliation Result")

    st.dataframe(recon,use_container_width=True)


    # -----------------------------
    # Excel Download
    # -----------------------------
    buffer = BytesIO()

    recon.to_excel(buffer,index=False)

    st.download_button(
        "Download Excel Report",
        buffer.getvalue(),
        "GST_Reconciliation_Output.xlsx"
    )
