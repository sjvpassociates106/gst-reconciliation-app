import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Enterprise GST Reconciliation", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File (Raw Data Only)", type=["xlsx"])


# -------------------------------------------------------------
# FIND REAL HEADER ROW IN GSTR2B
# -------------------------------------------------------------

def load_real_gstr2b(file):
    raw = pd.read_excel(file, header=None)

    header_row = None

    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).str.lower()

        if row.str.contains("gstin of supplier").any():
            header_row = i
            break

    if header_row is None:
        st.error("Could not locate B2B table inside GSTR-2B file.")
        st.stop()

    df = pd.read_excel(file, header=header_row)
    df.columns = df.columns.str.strip()
    return df


# -------------------------------------------------------------
# FIND PURCHASE HEADER ROW
# -------------------------------------------------------------

def load_real_purchase(file):
    raw = pd.read_excel(file, header=None)

    header_row = None

    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).str.lower()

        if row.str.contains("supplier invoice").any() and row.str.contains("gstin").any():
            header_row = i
            break

    if header_row is None:
        st.error("Upload RAW Purchase Register sheet (not Pivot).")
        st.stop()

    df = pd.read_excel(file, header=header_row)
    df.columns = df.columns.str.strip()
    return df


# -------------------------------------------------------------
# CLEAN COLUMN NAME
# -------------------------------------------------------------

def clean(col):
    col = str(col)
    col = col.lower()
    col = col.replace("₹", "")
    col = col.replace("(", "").replace(")", "")
    col = re.sub(r'[^a-z0-9]', '', col)
    return col


# -------------------------------------------------------------
# MAIN LOGIC
# -------------------------------------------------------------

if gstr2b_file and purchase_file:

    gstr2b = load_real_gstr2b(gstr2b_file)
    purchase = load_real_purchase(purchase_file)

    g2b_map = {col: clean(col) for col in gstr2b.columns}
    pr_map = {col: clean(col) for col in purchase.columns}

    # Required from GSTR2B
    gstin_2b = next((c for c, v in g2b_map.items() if "gstinofsupplier" in v), None)
    invoice_2b = next((c for c, v in g2b_map.items() if "invoicenumber" in v), None)
    date_2b = next((c for c, v in g2b_map.items() if "invoicedate" in v), None)
    taxable_2b = next((c for c, v in g2b_map.items() if "taxablevalue" in v), None)
    igst_2b = next((c for c, v in g2b_map.items() if "integratedtax" in v), None)
    cgst_2b = next((c for c, v in g2b_map.items() if "centraltax" in v), None)
    sgst_2b = next((c for c, v in g2b_map.items() if "stateuttax" in v), None)

    # Required from Purchase
    gstin_pr = next((c for c, v in pr_map.items() if "gstinuin" in v or "gstin" in v), None)
    invoice_pr = next((c for c, v in pr_map.items() if "supplierinvoiceno" in v), None)
    date_pr = next((c for c, v in pr_map.items() if v == "date"), None)
    taxable_pr = next((c for c, v in pr_map.items() if "taxableamount" in v), None)
    igst_pr = next((c for c, v in pr_map.items() if v == "igst"), None)
    cgst_pr = next((c for c, v in pr_map.items() if v == "cgst"), None)
    sgst_pr = next((c for c, v in pr_map.items() if v == "sgst"), None)

    if not gstin_2b or not invoice_2b:
        st.error("Required columns missing in GSTR-2B.")
        st.write(gstr2b.columns)
        st.stop()

    if not gstin_pr or not invoice_pr:
        st.error("Required columns missing in Purchase Register.")
        st.write(purchase.columns)
        st.stop()

    # Build clean tables
    df_2b = pd.DataFrame({
        "GSTIN": gstr2b[gstin_2b],
        "Invoice": gstr2b[invoice_2b],
        "Taxable_2B": pd.to_numeric(gstr2b[taxable_2b], errors="coerce").fillna(0),
        "IGST_2B": pd.to_numeric(gstr2b[igst_2b], errors="coerce").fillna(0),
        "CGST_2B": pd.to_numeric(gstr2b[cgst_2b], errors="coerce").fillna(0),
        "SGST_2B": pd.to_numeric(gstr2b[sgst_2b], errors="coerce").fillna(0)
    })

    df_pr = pd.DataFrame({
        "GSTIN": purchase[gstin_pr],
        "Invoice": purchase[invoice_pr],
        "Taxable_PR": pd.to_numeric(purchase[taxable_pr], errors="coerce").fillna(0),
        "IGST_PR": pd.to_numeric(purchase[igst_pr], errors="coerce").fillna(0),
        "CGST_PR": pd.to_numeric(purchase[cgst_pr], errors="coerce").fillna(0),
        "SGST_PR": pd.to_numeric(purchase[sgst_pr], errors="coerce").fillna(0)
    })

    df_2b["Invoice"] = df_2b["Invoice"].astype(str).str.strip().str.upper()
    df_pr["Invoice"] = df_pr["Invoice"].astype(str).str.strip().str.upper()

    df_2b["GSTIN"] = df_2b["GSTIN"].astype(str).str.strip()
    df_pr["GSTIN"] = df_pr["GSTIN"].astype(str).str.strip()

    recon = pd.merge(df_pr, df_2b, on=["GSTIN", "Invoice"], how="outer", indicator=True)

    recon["Taxable_Diff"] = recon["Taxable_PR"] - recon["Taxable_2B"]
    recon["IGST_Diff"] = recon["IGST_PR"] - recon["IGST_2B"]
    recon["CGST_Diff"] = recon["CGST_PR"] - recon["CGST_2B"]
    recon["SGST_Diff"] = recon["SGST_PR"] - recon["SGST_2B"]

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

    st.subheader("Detailed Reconciliation")
    st.dataframe(recon, use_container_width=True)

    st.download_button(
        "Download Reconciliation",
        data=recon.to_csv(index=False),
        file_name="GST_Reconciliation.csv",
        mime="text/csv"
    )
