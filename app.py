import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST AI Reconciliation", layout="wide")
st.title("GST 2B vs Purchase Register (AI Reconciliation Tool)")


gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# ---------------- AI FUNCTIONS ---------------- #

def clean_invoice(x):
    if pd.isna(x):
        return ""
    x = str(x).upper()
    x = re.sub(r"[^A-Z0-9]", "", x)
    return x[-6:]


def num(x):
    return pd.to_numeric(x, errors="coerce").fillna(0)


# -------- HEADER DETECTION -------- #

def detect_header(file, sheet):

    temp = pd.read_excel(file, sheet_name=sheet, header=None)

    max_rows = min(20, len(temp))  # 🔥 FIX

    best_row = 0
    best_score = 0

    keywords = ["gstin", "invoice", "taxable", "tax"]

    for i in range(max_rows):

        row = " ".join(temp.iloc[i].astype(str).str.lower())

        score = sum([1 for k in keywords if k in row])

        if score > best_score:
            best_score = score
            best_row = i

    return best_row


# -------- COLUMN DETECTION (AI) -------- #

def detect_columns(df):

    cols = df.columns
    result = {}

    for col in cols:
        c = str(col).lower()

        if "gstin" in c:
            result["gstin"] = col

        elif "invoice" in c:
            result["invoice"] = col

        elif "trade" in c or "party" in c or "legal" in c:
            result["party"] = col

        elif "taxable" in c:
            result["taxable"] = col

        elif "integrated" in c or "igst" in c:
            result["igst"] = col

        elif "central" in c or "cgst" in c:
            result["cgst"] = col

        elif "state" in c or "sgst" in c:
            result["sgst"] = col

    return result


# -------- GST DETECTION BY VALUE -------- #

def detect_gst_by_value(df):

    numeric_cols = df.select_dtypes(include=["float64","int64"]).columns

    taxable = igst = cgst = sgst = None

    for col in numeric_cols:

        data = df[col].dropna()
        if len(data) == 0:
            continue

        avg = data.mean()

        if avg > 10000:
            taxable = col

        elif avg < 5000:
            if cgst is None:
                cgst = col
            elif sgst is None:
                sgst = col
            elif igst is None:
                igst = col

    return taxable, igst, cgst, sgst


# ---------------- MAIN ---------------- #

if gstr_file and purchase_file:

    # -------- GSTR2B -------- #

    header = detect_header(gstr_file, "B2B")
    gstr2b = pd.read_excel(gstr_file, sheet_name="B2B", header=header)

    cols = detect_columns(gstr2b)

    if "taxable" not in cols:
        t, i, c, s = detect_gst_by_value(gstr2b)
        cols["taxable"], cols["igst"], cols["cgst"], cols["sgst"] = t, i, c, s

    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[cols.get("gstin","")].astype(str).str.upper().str.strip()
    df2b["Party"] = gstr2b[cols.get("party","")].astype(str)
    df2b["Invoice"] = gstr2b[cols.get("invoice","")].apply(clean_invoice)

    df2b["Taxable2B"] = num(gstr2b[cols["taxable"]]) if "taxable" in cols else 0
    df2b["IGST2B"] = num(gstr2b[cols["igst"]]) if "igst" in cols else 0
    df2b["CGST2B"] = num(gstr2b[cols["cgst"]]) if "cgst" in cols else 0
    df2b["SGST2B"] = num(gstr2b[cols["sgst"]]) if "sgst" in cols else 0

    df2b = df2b.groupby(["GSTIN","Invoice"], as_index=False).sum()


    # -------- PURCHASE -------- #

    headerp = detect_header(purchase_file, 0)
    purchase = pd.read_excel(purchase_file, header=headerp)

    colsp = detect_columns(purchase)

    if "taxable" not in colsp:
        t, i, c, s = detect_gst_by_value(purchase)
        colsp["taxable"], colsp["igst"], colsp["cgst"], colsp["sgst"] = t, i, c, s

    dfpr = pd.DataFrame()

    dfpr["GSTIN"] = purchase[colsp["gstin"]].astype(str).str.upper().str.strip() if "gstin" in colsp else ""
    dfpr["Party"] = purchase[colsp["party"]].astype(str) if "party" in colsp else ""
    dfpr["Invoice"] = purchase[colsp["invoice"]].apply(clean_invoice) if "invoice" in colsp else ""

    dfpr["TaxablePR"] = num(purchase[colsp["taxable"]]) if "taxable" in colsp else 0
    dfpr["IGSTPR"] = num(purchase[colsp["igst"]]) if "igst" in colsp else 0
    dfpr["CGSTPR"] = num(purchase[colsp["cgst"]]) if "cgst" in colsp else 0
    dfpr["SGSTPR"] = num(purchase[colsp["sgst"]]) if "sgst" in colsp else 0
    dfpr = dfpr.groupby(["GSTIN","Invoice"], as_index=False).sum()


    # -------- MERGE -------- #

    recon = pd.merge(dfpr, df2b, on=["GSTIN","Invoice"], how="outer", indicator=True)


    def check(r):

        if r["_merge"] == "left_only":
            return pd.Series(["Mismatch","Missing in 2B"])

        if r["_merge"] == "right_only":
            return pd.Series(["Mismatch","Missing in Purchase"])

        tol = 1
        reasons = []

        if abs(r["TaxablePR"] - r["Taxable2B"]) > tol:
            reasons.append("Taxable mismatch")

        if abs(r["CGSTPR"] - r["CGST2B"]) > tol:
            reasons.append("CGST mismatch")

        if abs(r["SGSTPR"] - r["SGST2B"]) > tol:
            reasons.append("SGST mismatch")

        if abs(r["IGSTPR"] - r["IGST2B"]) > tol:
            reasons.append("IGST mismatch")

        if not reasons:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]] = recon.apply(check, axis=1)
    recon.drop(columns=["_merge"], inplace=True)


    st.subheader("Reconciliation Result")
    st.dataframe(recon, use_container_width=True)


    buffer = BytesIO()
    recon.to_excel(buffer, index=False)

    st.download_button(
        "Download Report",
        buffer.getvalue(),
        "GST_AI_Reconciliation.xlsx"
    )
