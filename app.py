import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation", layout="wide")
st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls","xlsx"])


# -------- FUNCTIONS --------

def clean_invoice(inv):
    if pd.isna(inv):
        return ""
    inv = str(inv).upper()
    inv = re.sub(r"[^A-Z0-9]", "", inv)
    return inv[-6:] if len(inv) > 6 else inv


def num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def detect_header(file, sheet):
    temp = pd.read_excel(file, sheet_name=sheet, header=None)

    max_rows = min(20, len(temp))
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


# -------- PROCESS --------

if gstr_file and purchase_file:

    # ----- LOAD GSTR2B (MULTI HEADER FIX) -----
    gstr2b = pd.read_excel(gstr_file, sheet_name="B2B", header=[0,1])
    gstr2b.columns = [' '.join([str(i) for i in col]).strip().lower() for col in gstr2b.columns]

    gstin_col = party_col = invoice_col = None
taxable_col = igst_col = cgst_col = sgst_col = None

for col in gstr2b.columns:

    c = str(col).lower()

    # clean properly
    c = c.replace("₹","")
    c = c.replace("(", "").replace(")", "")
    c = c.replace("/", " ")
    c = c.replace("-", " ")
    c = c.replace("_", " ")
    c = " ".join(c.split())

    # DEBUG (run once)
    # st.write(c)

    if "gstin" in c:
        gstin_col = col

    if "trade" in c or "legal" in c:
        party_col = col

    if "invoice number" in c:
        invoice_col = col

    if "taxable" in c:
        taxable_col = col

    # 🔥 VERY STRONG GST DETECTION
    if "integrated" in c or "igst" in c:
        igst_col = col

    if "central" in c or "cgst" in c:
        cgst_col = col

    if "state" in c or "sgst" in c or "ut" in c:
        sgst_col = col
   
    st.write("Detected Columns:",
         "CGST =", cgst_col,
         "SGST =", sgst_col,
         "IGST =", igst_col)

    df2b = pd.DataFrame()

    df2b["GSTIN"] = gstr2b[gstin_col].astype(str).str.upper().str.strip() if gstin_col else ""
    df2b["Party"] = gstr2b[party_col].astype(str).str.upper().str.strip() if party_col else ""
    df2b["Invoice"] = gstr2b[invoice_col].apply(clean_invoice) if invoice_col else ""

    df2b["Taxable2B"] = num(gstr2b[taxable_col]) if taxable_col else 0
    df2b["IGST2B"] = num(gstr2b[igst_col]) if igst_col else 0
    df2b["CGST2B"] = num(gstr2b[cgst_col]) if cgst_col else 0
    df2b["SGST2B"] = num(gstr2b[sgst_col]) if sgst_col else 0

    df2b = df2b.groupby(["GSTIN","Invoice"], as_index=False).sum()


    # ----- LOAD PURCHASE -----
    headerpr = detect_header(purchase_file, 0)
    purchase = pd.read_excel(purchase_file, header=headerpr)

    gstin_pr = party_pr = invoice_pr = None
    taxable_pr = igst_pr = cgst_pr = sgst_pr = None

    for col in purchase.columns:

        c = str(col).lower()

        if "gstin" in c or "uin" in c:
            gstin_pr = col

        if "party" in c or "particular" in c:
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

    dfpr["GSTIN"] = purchase[gstin_pr].astype(str).str.upper().str.strip() if gstin_pr else ""
    dfpr["Party"] = purchase[party_pr].astype(str) if party_pr else ""
    dfpr["Invoice"] = purchase[invoice_pr].apply(clean_invoice) if invoice_pr else ""

    dfpr["TaxablePR"] = num(purchase[taxable_pr]) if taxable_pr else 0
    dfpr["IGSTPR"] = num(purchase[igst_pr]) if igst_pr else 0
    dfpr["CGSTPR"] = num(purchase[cgst_pr]) if cgst_pr else 0
    dfpr["SGSTPR"] = num(purchase[sgst_pr]) if sgst_pr else 0

    dfpr = dfpr.groupby(["GSTIN","Invoice"], as_index=False).sum()


    # ----- MERGE -----
    recon = pd.merge(dfpr, df2b, on=["GSTIN","Invoice"], how="outer", indicator=True)


    # ----- CLEAN OUTPUT -----
    recon = recon.fillna({
        "GSTIN": "",
        "Party_x": "",
        "Party_y": "",
        "Invoice": "",
        "TaxablePR": 0,
        "IGSTPR": 0,
        "CGSTPR": 0,
        "SGSTPR": 0,
        "Taxable2B": 0,
        "IGST2B": 0,
        "CGST2B": 0,
        "SGST2B": 0
    })

    # Merge party name
    recon["Party"] = recon["Party_x"].replace("", None)
    recon["Party"] = recon["Party"].fillna(recon["Party_y"])
    recon = recon.drop(columns=["Party_x","Party_y"])


    # ----- CHECK -----
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
    recon = recon.drop(columns=["_merge"])


    # ----- FINAL FORMAT -----
    cols = [
        "GSTIN","Party","Invoice",
        "TaxablePR","CGSTPR","SGSTPR","IGSTPR",
        "Taxable2B","CGST2B","SGST2B","IGST2B",
        "Status","Reason"
    ]

    recon = recon[cols]
    recon = recon.sort_values(by=["GSTIN","Invoice"])


    st.subheader("Reconciliation Result")
    st.dataframe(recon, use_container_width=True)


    # ----- DOWNLOAD -----
    buffer = BytesIO()
    recon.to_excel(buffer, index=False)

    st.download_button(
        label="Download Excel Report",
        data=buffer.getvalue(),
        file_name="GST_Reconciliation_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
