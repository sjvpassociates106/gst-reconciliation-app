import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST 2B vs Purchase Register Reconciliation")


gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls", "xlsx"])


# ---------- FUNCTIONS ---------- #

def clean_invoice(x):
    if pd.isna(x):
        return ""
    x = str(x).upper().replace(" ", "")
    x = re.sub(r"[^A-Z0-9]", "", x)
    nums = re.findall(r"\d+", x)
    return nums[-1] if nums else x


def num(x):
    return pd.to_numeric(x, errors="coerce").fillna(0)


def detect_header(file, sheet):
    temp = pd.read_excel(file, sheet_name=sheet, header=None)

    for i in range(20):
        row = " ".join(temp.iloc[i].astype(str).str.lower())

        if "invoice" in row and "gstin" in row:
            return i

    return 0


def detect_columns(df):

    gstin = party = invoice = taxable = igst = cgst = sgst = None

    for col in df.columns:

        c = str(col).lower()

        if "gstin" in c:
            gstin = col

        elif "trade" in c or "party" in c:
            party = col

        elif "invoice" in c:
            invoice = col

        elif "taxable" in c:
            taxable = col

        elif "integrated" in c or "igst" in c:
            igst = col

        elif "central" in c or "cgst" in c:
            cgst = col

        elif "state" in c or "sgst" in c:
            sgst = col

    return gstin, party, invoice, taxable, igst, cgst, sgst


# ---------- MAIN ---------- #

if gstr_file and purchase_file:

    # ---------- GSTR 2B ---------- #

    header2b = detect_header(gstr_file, "B2B")
    gstr2b = pd.read_excel(gstr_file, sheet_name="B2B", header=header2b)

    gstin, party, invoice, taxable, igst, cgst, sgst = detect_columns(gstr2b)

    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin].astype(str).str.strip() if gstin else ""
    df2b["Party"] = gstr2b[party] if party else ""
    df2b["Invoice"] = gstr2b[invoice].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[taxable]) if taxable else 0
    df2b["IGST2B"] = num(gstr2b[igst]) if igst else 0
    df2b["CGST2B"] = num(gstr2b[cgst]) if cgst else 0
    df2b["SGST2B"] = num(gstr2b[sgst]) if sgst else 0

    df2b = df2b.groupby(["GSTIN", "Invoice"], as_index=False).sum()


    # ---------- PURCHASE ---------- #

    purchase = pd.read_excel(purchase_file)

    gstin_p, party_p, invoice_p, taxable_p, igst_p, cgst_p, sgst_p = detect_columns(purchase)

    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[gstin_p].astype(str).str.strip() if gstin_p else ""
    dfpr["Party"] = purchase[party_p] if party_p else ""
    dfpr["Invoice"] = purchase[invoice_p].apply(clean_invoice)

    dfpr["TaxablePR"] = num(purchase[taxable_p]) if taxable_p else 0
    dfpr["IGSTPR"] = num(purchase[igst_p]) if igst_p else 0
    dfpr["CGSTPR"] = num(purchase[cgst_p]) if cgst_p else 0
    dfpr["SGSTPR"] = num(purchase[sgst_p]) if sgst_p else 0

    dfpr = dfpr.groupby(["GSTIN", "Invoice"], as_index=False).sum()


    # ---------- MERGE ---------- #

    recon = pd.merge(
        dfpr,
        df2b,
        on=["GSTIN", "Invoice"],
        how="outer",
        indicator=True
    )


    recon = recon.fillna(0)


    # ---------- STATUS ---------- #

    def check(r):

        if r["_merge"] == "left_only":
            return pd.Series(["Mismatch", "Missing in 2B"])

        if r["_merge"] == "right_only":
            return pd.Series(["Mismatch", "Missing in Purchase"])

        tol = 1
        reasons = []

        if abs(r["TaxablePR"] - r["Taxable2B"]) > tol:
            reasons.append("Taxable")

        if abs(r["IGSTPR"] - r["IGST2B"]) > tol:
            reasons.append("IGST")

        if abs(r["CGSTPR"] - r["CGST2B"]) > tol:
            reasons.append("CGST")

        if abs(r["SGSTPR"] - r["SGST2B"]) > tol:
            reasons.append("SGST")

        if not reasons:
            return pd.Series(["Matched", ""])

        return pd.Series(["Mismatch", ",".join(reasons)])


    recon[["Status", "Reason"]] = recon.apply(check, axis=1)
    recon = recon.drop(columns=["_merge"])


    # ---------- OUTPUT FORMAT ---------- #

    final_cols = [
        "GSTIN", "Party", "Invoice",
        "TaxablePR", "Taxable2B",
        "CGSTPR", "CGST2B",
        "SGSTPR", "SGST2B",
        "IGSTPR", "IGST2B",
        "Status", "Reason"
    ]

    recon = recon[final_cols]

    st.subheader("Reconciliation Result")
    st.dataframe(recon, use_container_width=True)


    # ---------- DOWNLOAD ---------- #

    buffer = BytesIO()
    recon.to_excel(buffer, index=False)

    st.download_button(
        "Download Excel Report",
        buffer.getvalue(),
        "GST_Reconciliation.xlsx"
    )
