import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Enterprise GST Reconciliation", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])


# ----------------------------------------------------------
# HELPER FUNCTIONS
# ----------------------------------------------------------

def clean_text(val):
    return str(val).strip().upper()

def clean_column(col):
    col = str(col).lower()
    col = col.replace("₹", "")
    col = re.sub(r'[^a-z0-9]', '', col)
    return col


def load_b2b_sheet(file):
    excel = pd.ExcelFile(file)

    if "B2B" not in excel.sheet_names:
        st.error("B2B sheet not found in GSTR-2B file.")
        st.stop()

    raw = excel.parse("B2B", header=None)

    header_row = None
    for i in range(len(raw)):
        if raw.iloc[i].astype(str).str.contains("GSTIN of Supplier", case=False).any():
            header_row = i
            break

    if header_row is None:
        st.error("Could not detect header in B2B sheet.")
        st.stop()

    df = excel.parse("B2B", header=header_row)
    df.columns = df.columns.str.strip()
    return df


# ----------------------------------------------------------
# MAIN LOGIC
# ----------------------------------------------------------

if gstr2b_file and purchase_file:

    gstr2b = load_b2b_sheet(gstr2b_file)
    purchase = pd.read_excel(purchase_file)
    purchase.columns = purchase.columns.str.strip()

    # Clean column mapping
    g2b_map = {col: clean_column(col) for col in gstr2b.columns}
    pr_map = {col: clean_column(col) for col in purchase.columns}

    # Map required columns dynamically
    def find_col(mapping, keyword):
        for col, clean in mapping.items():
            if keyword in clean:
                return col
        return None

    gstin_2b = find_col(g2b_map, "gstinofsupplier")
    party_2b = find_col(g2b_map, "tradelegalname")
    invoice_2b = find_col(g2b_map, "invoicenumber")
    date_2b = find_col(g2b_map, "invoicedate")
    taxable_2b = find_col(g2b_map, "taxablevalue")
    igst_2b = find_col(g2b_map, "integratedtax")
    cgst_2b = find_col(g2b_map, "centraltax")
    sgst_2b = find_col(g2b_map, "stateuttax")

    gstin_pr = find_col(pr_map, "gstinuin")
    party_pr = find_col(pr_map, "particulars")
    invoice_pr = find_col(pr_map, "supplierinvoiceno")
    date_pr = find_col(pr_map, "date")
    taxable_pr = find_col(pr_map, "taxableamount")
    igst_pr = find_col(pr_map, "igst")
    cgst_pr = find_col(pr_map, "cgst")
    sgst_pr = find_col(pr_map, "sgst")

    # Build DataFrames
    df_2b = pd.DataFrame({
        "GSTIN": gstr2b[gstin_2b],
        "Party_2B": gstr2b[party_2b],
        "Invoice": gstr2b[invoice_2b],
        "Date_2B": pd.to_datetime(gstr2b[date_2b], errors="coerce"),
        "Taxable_2B": pd.to_numeric(gstr2b[taxable_2b], errors="coerce").fillna(0),
        "IGST_2B": pd.to_numeric(gstr2b[igst_2b], errors="coerce").fillna(0),
        "CGST_2B": pd.to_numeric(gstr2b[cgst_2b], errors="coerce").fillna(0),
        "SGST_2B": pd.to_numeric(gstr2b[sgst_2b], errors="coerce").fillna(0)
    })

    df_pr = pd.DataFrame({
        "GSTIN": purchase[gstin_pr],
        "Party_PR": purchase[party_pr],
        "Invoice": purchase[invoice_pr],
        "Date_PR": pd.to_datetime(purchase[date_pr], errors="coerce"),
        "Taxable_PR": pd.to_numeric(purchase[taxable_pr], errors="coerce").fillna(0),
        "IGST_PR": pd.to_numeric(purchase[igst_pr], errors="coerce").fillna(0),
        "CGST_PR": pd.to_numeric(purchase[cgst_pr], errors="coerce").fillna(0),
        "SGST_PR": pd.to_numeric(purchase[sgst_pr], errors="coerce").fillna(0)
    })

    # Clean keys
    df_2b["Invoice"] = df_2b["Invoice"].apply(clean_text)
    df_pr["Invoice"] = df_pr["Invoice"].apply(clean_text)
    df_2b["GSTIN"] = df_2b["GSTIN"].apply(clean_text)
    df_pr["GSTIN"] = df_pr["GSTIN"].apply(clean_text)

    # Merge
    recon = pd.merge(df_pr, df_2b, on=["GSTIN", "Invoice"], how="outer", indicator=True)

    # Differences
    recon["Taxable_Diff"] = recon["Taxable_PR"] - recon["Taxable_2B"]
    recon["IGST_Diff"] = recon["IGST_PR"] - recon["IGST_2B"]
    recon["CGST_Diff"] = recon["CGST_PR"] - recon["CGST_2B"]
    recon["SGST_Diff"] = recon["SGST_PR"] - recon["SGST_2B"]

    # Reason Logic
    def generate_reason(row):
        reasons = []

        if row["_merge"] == "left_only":
            return "Missing in 2B"

        if row["_merge"] == "right_only":
            return "Missing in Purchase"

        if row["Party_PR"] != row["Party_2B"]:
            reasons.append("Party Name Mismatch")

        if row["Date_PR"] != row["Date_2B"]:
            reasons.append("Invoice Date Mismatch")

        if row["Taxable_Diff"] != 0:
            reasons.append("Taxable Value Mismatch")

        if row["IGST_Diff"] != 0:
            reasons.append("IGST Mismatch")

        if row["CGST_Diff"] != 0:
            reasons.append("CGST Mismatch")

        if row["SGST_Diff"] != 0:
            reasons.append("SGST Mismatch")

        if not reasons:
            return "Matched"

        return ", ".join(reasons)

    recon["Status"] = recon.apply(generate_reason, axis=1)

    # Summary
    st.subheader("Reconciliation Summary")
    st.write(recon["Status"].value_counts())

    st.subheader("Detailed Reconciliation")
    st.dataframe(recon, use_container_width=True)

    # Excel download
    excel_file = "GST_Reconciliation_Output.xlsx"
    recon.to_excel(excel_file, index=False)

    with open(excel_file, "rb") as f:
        st.download_button(
            "Download Excel Report",
            data=f,
            file_name="GST_Reconciliation_Output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
