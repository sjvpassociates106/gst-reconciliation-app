import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Enterprise GST Reconciliation", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File (Raw Data Only)", type=["xlsx"])


# ----------------------------------------------------------
# CLEAN COLUMN NAMES
# ----------------------------------------------------------

def clean_column(col):
    col = str(col)
    col = col.lower()
    col = col.replace("₹", "")
    col = col.replace("(", "").replace(")", "")
    col = re.sub(r'[^a-z0-9]', '', col)
    return col


def map_columns(df):
    mapping = {}
    for col in df.columns:
        mapping[col] = clean_column(col)
    return mapping


# ----------------------------------------------------------
# LOAD GSTR2B - ONLY B2B SHEET
# ----------------------------------------------------------

def load_gstr2b(file):
    excel = pd.ExcelFile(file)

    if "B2B" not in excel.sheet_names:
        st.error("B2B sheet not found in GSTR-2B file.")
        st.write("Available sheets:", excel.sheet_names)
        st.stop()

    df = excel.parse("B2B")
    df.columns = df.columns.str.strip()
    return df


# ----------------------------------------------------------
# MAIN LOGIC
# ----------------------------------------------------------

if gstr2b_file and purchase_file:

    gstr2b = load_gstr2b(gstr2b_file)
    purchase = pd.read_excel(purchase_file)

    gstr2b.columns = gstr2b.columns.str.strip()
    purchase.columns = purchase.columns.str.strip()

    g2b_map = map_columns(gstr2b)
    pr_map = map_columns(purchase)

    # Required from GSTR-2B
    required_2b = {
        "gstinofsupplier": None,
        "tradellegalname": None,
        "invoicenumber": None,
        "invoicedate": None,
        "taxablevalue": None,
        "integratedtax": None,
        "centraltax": None,
        "stateuttax": None
    }

    # Required from Purchase
    required_pr = {
        "gstinuin": None,
        "particulars": None,
        "supplierinvoiceno": None,
        "date": None,
        "taxableamount": None,
        "igst": None,
        "cgst": None,
        "sgst": None
    }

    # Match columns dynamically
    for col, clean in g2b_map.items():
        for key in required_2b:
            if key in clean:
                required_2b[key] = col

    for col, clean in pr_map.items():
        for key in required_pr:
            if key in clean:
                required_pr[key] = col

    # Validate essential fields
    if not required_2b["gstinofsupplier"] or not required_2b["invoicenumber"]:
        st.error("Required columns missing in GSTR-2B.")
        st.write(gstr2b.columns)
        st.stop()

    if not required_pr["gstinuin"] or not required_pr["supplierinvoiceno"]:
        st.error("Required columns missing in Purchase Register. Please upload RAW data sheet (not pivot).")
        st.write(purchase.columns)
        st.stop()

    # Build clean datasets
    df_2b = pd.DataFrame({
        "GSTIN": gstr2b[required_2b["gstinofsupplier"]],
        "Invoice": gstr2b[required_2b["invoicenumber"]],
        "Date": gstr2b[required_2b["invoicedate"]],
        "Taxable_2B": pd.to_numeric(gstr2b[required_2b["taxablevalue"]], errors="coerce").fillna(0),
        "IGST_2B": pd.to_numeric(gstr2b[required_2b["integratedtax"]], errors="coerce").fillna(0),
        "CGST_2B": pd.to_numeric(gstr2b[required_2b["centraltax"]], errors="coerce").fillna(0),
        "SGST_2B": pd.to_numeric(gstr2b[required_2b["stateuttax"]], errors="coerce").fillna(0)
    })

    df_pr = pd.DataFrame({
        "GSTIN": purchase[required_pr["gstinuin"]],
        "Invoice": purchase[required_pr["supplierinvoiceno"]],
        "Date": purchase[required_pr["date"]],
        "Taxable_PR": pd.to_numeric(purchase[required_pr["taxableamount"]], errors="coerce").fillna(0),
        "IGST_PR": pd.to_numeric(purchase[required_pr["igst"]], errors="coerce").fillna(0),
        "CGST_PR": pd.to_numeric(purchase[required_pr["cgst"]], errors="coerce").fillna(0),
        "SGST_PR": pd.to_numeric(purchase[required_pr["sgst"]], errors="coerce").fillna(0)
    })

    # Clean matching keys
    df_2b["Invoice"] = df_2b["Invoice"].astype(str).str.strip().str.upper()
    df_pr["Invoice"] = df_pr["Invoice"].astype(str).str.strip().str.upper()

    df_2b["GSTIN"] = df_2b["GSTIN"].astype(str).str.strip()
    df_pr["GSTIN"] = df_pr["GSTIN"].astype(str).str.strip()

    # Merge
    recon = pd.merge(df_pr, df_2b, on=["GSTIN", "Invoice"], how="outer", indicator=True)

    # Difference
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

    st.subheader("Reconciliation Summary")

    col1, col2, col3 = st.columns(3)
    col1.metric("Matched", (recon["Status"] == "Matched").sum())
    col2.metric("Tax Mismatch", (recon["Status"] == "Tax Mismatch").sum())
    col3.metric("Missing in 2B", (recon["Status"] == "Missing in 2B").sum())

    st.subheader("Detailed Reconciliation")
    st.dataframe(recon, use_container_width=True)

    st.download_button(
        "Download Reconciliation Report",
        data=recon.to_csv(index=False),
        file_name="GST_Reconciliation_Report.csv",
        mime="text/csv"
    )
