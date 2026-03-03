import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="GST Reconciliation", layout="wide")
st.title("GST Reconciliation - B2B Only")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])


# --------------------------------------------------------
# FIND HEADER ROW INSIDE B2B SHEET
# --------------------------------------------------------

def load_b2b_sheet(file):
    excel = pd.ExcelFile(file)

    if "B2B" not in excel.sheet_names:
        st.error("B2B sheet not found.")
        st.write("Available sheets:", excel.sheet_names)
        st.stop()

    raw = excel.parse("B2B", header=None)

    header_row = None

    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).str.lower()

        if row.str.contains("gstin of supplier").any():
            header_row = i
            break

    if header_row is None:
        st.error("Could not detect header row in B2B sheet.")
        st.stop()

    df = excel.parse("B2B", header=header_row)
    df.columns = df.columns.astype(str).str.strip()
    return df


# --------------------------------------------------------
# CLEAN COLUMN NAME
# --------------------------------------------------------

def clean(col):
    col = str(col).lower()
    col = col.replace("₹", "")
    col = re.sub(r'[^a-z0-9]', '', col)
    return col


# --------------------------------------------------------
# MAIN
# --------------------------------------------------------

if gstr2b_file and purchase_file:

    # Load B2B correctly
    gstr2b = load_b2b_sheet(gstr2b_file)
    purchase = pd.read_excel(purchase_file)

    purchase.columns = purchase.columns.str.strip()

    # Map columns
    g2b_cols = {col: clean(col) for col in gstr2b.columns}
    pr_cols = {col: clean(col) for col in purchase.columns}

    # Detect needed columns safely
    gstin_2b = next((c for c, v in g2b_cols.items() if "gstinofsupplier" in v), None)
    invoice_2b = next((c for c, v in g2b_cols.items() if "invoicenumber" in v), None)
    taxable_2b = next((c for c, v in g2b_cols.items() if "taxablevalue" in v), None)
    igst_2b = next((c for c, v in g2b_cols.items() if "integratedtax" in v), None)
    cgst_2b = next((c for c, v in g2b_cols.items() if "centraltax" in v), None)
    sgst_2b = next((c for c, v in g2b_cols.items() if "stateuttax" in v), None)

    gstin_pr = next((c for c, v in pr_cols.items() if "gstin" in v), None)
    invoice_pr = next((c for c, v in pr_cols.items() if "supplierinvoiceno" in v), None)
    taxable_pr = next((c for c, v in pr_cols.items() if "taxableamount" in v), None)
    igst_pr = next((c for c, v in pr_cols.items() if v == "igst"), None)
    cgst_pr = next((c for c, v in pr_cols.items() if v == "cgst"), None)
    sgst_pr = next((c for c, v in pr_cols.items() if v == "sgst"), None)

    # Build safe dataframe (no crash if missing)
    df_2b = pd.DataFrame({
        "GSTIN": gstr2b[gstin_2b] if gstin_2b else "",
        "Invoice": gstr2b[invoice_2b] if invoice_2b else "",
        "Taxable_2B": pd.to_numeric(gstr2b[taxable_2b], errors="coerce").fillna(0) if taxable_2b else 0,
        "IGST_2B": pd.to_numeric(gstr2b[igst_2b], errors="coerce").fillna(0) if igst_2b else 0,
        "CGST_2B": pd.to_numeric(gstr2b[cgst_2b], errors="coerce").fillna(0) if cgst_2b else 0,
        "SGST_2B": pd.to_numeric(gstr2b[sgst_2b], errors="coerce").fillna(0) if sgst_2b else 0
    })

    df_pr = pd.DataFrame({
        "GSTIN": purchase[gstin_pr] if gstin_pr else "",
        "Invoice": purchase[invoice_pr] if invoice_pr else "",
        "Taxable_PR": pd.to_numeric(purchase[taxable_pr], errors="coerce").fillna(0) if taxable_pr else 0,
        "IGST_PR": pd.to_numeric(purchase[igst_pr], errors="coerce").fillna(0) if igst_pr else 0,
        "CGST_PR": pd.to_numeric(purchase[cgst_pr], errors="coerce").fillna(0) if cgst_pr else 0,
        "SGST_PR": pd.to_numeric(purchase[sgst_pr], errors="coerce").fillna(0) if sgst_pr else 0
    })

    # Clean keys
    df_2b["Invoice"] = df_2b["Invoice"].astype(str).str.strip().str.upper()
    df_pr["Invoice"] = df_pr["Invoice"].astype(str).str.strip().str.upper()
    df_2b["GSTIN"] = df_2b["GSTIN"].astype(str).str.strip()
    df_pr["GSTIN"] = df_pr["GSTIN"].astype(str).str.strip()

    # Merge
    recon = pd.merge(df_pr, df_2b, on=["GSTIN", "Invoice"], how="outer", indicator=True)

    # Differences
    recon["Taxable_Diff"] = recon["Taxable_PR"] - recon["Taxable_2B"]
    recon["IGST_Diff"] = recon["IGST_PR"] - recon["IGST_2B"]
    recon["CGST_Diff"] = recon["CGST_PR"] - recon["CGST_2B"]
    recon["SGST_Diff"] = recon["SGST_PR"] - recon["SGST_2B"]

    # Status
    def classify(row):
        if row["_merge"] == "both":
            if row["Taxable_Diff"] != 0 or row["IGST_Diff"] != 0 or \
               row["CGST_Diff"] != 0 or row["SGST_Diff"] != 0:
                return "Tax Mismatch"
            return "Matched"
        elif row["_merge"] == "left_only":
            return "Missing in 2B"
        else:
            return "Missing in Purchase"

    recon["Status"] = recon.apply(classify, axis=1)

    st.subheader("Summary")
    st.write(recon["Status"].value_counts())

    st.subheader("Reconciliation Details")
    st.dataframe(recon, use_container_width=True)

    st.download_button(
        "Download CSV",
        data=recon.to_csv(index=False),
        file_name="GST_Reconciliation.csv",
        mime="text/csv"
    )
