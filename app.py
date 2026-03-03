import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="GST Reconciliation System", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])


# ----------------------------------------------------------
# CLEAN FUNCTIONS
# ----------------------------------------------------------

def clean_column(col):
    col = str(col).lower()
    col = col.replace("₹", "")
    col = re.sub(r'[^a-z0-9]', '', col)
    return col


def find_column(mapping, keywords):
    for col, cleaned in mapping.items():
        for key in keywords:
            if key in cleaned:
                return col
    return None


# ----------------------------------------------------------
# LOAD B2B SHEET (AUTO HEADER DETECT)
# ----------------------------------------------------------

def load_b2b(file):
    excel = pd.ExcelFile(file)

    if "B2B" not in excel.sheet_names:
        st.error("B2B sheet not found in GSTR-2B file.")
        st.stop()

    raw = excel.parse("B2B", header=None)

    header_row = None
    for i in range(len(raw)):
        if raw.iloc[i].astype(str).str.contains("gstin", case=False).any():
            header_row = i
            break

    if header_row is None:
        st.error("Could not detect header row in B2B sheet.")
        st.stop()

    df = excel.parse("B2B", header=header_row)
    df.columns = df.columns.str.strip()
    return df


# ----------------------------------------------------------
# MAIN PROCESS
# ----------------------------------------------------------

if gstr2b_file and purchase_file:

    # Load files
    gstr2b = load_b2b(gstr2b_file)
    purchase = pd.read_excel(purchase_file)
    purchase.columns = purchase.columns.str.strip()

    # Create column maps
    g2b_map = {col: clean_column(col) for col in gstr2b.columns}
    pr_map = {col: clean_column(col) for col in purchase.columns}

    # Detect required columns dynamically
    gstin_2b = find_column(g2b_map, ["gstin"])
    invoice_2b = find_column(g2b_map, ["invoice", "doc"])
    date_2b = find_column(g2b_map, ["date"])
    taxable_2b = find_column(g2b_map, ["taxable"])
    igst_2b = find_column(g2b_map, ["integrated", "igst"])
    cgst_2b = find_column(g2b_map, ["central", "cgst"])
    sgst_2b = find_column(g2b_map, ["state", "sgst"])

    gstin_pr = find_column(pr_map, ["gstin"])
    invoice_pr = find_column(pr_map, ["supplierinvoice", "invoice"])
    date_pr = find_column(pr_map, ["date"])
    taxable_pr = find_column(pr_map, ["taxable", "gross", "value"])
    igst_pr = find_column(pr_map, ["igst"])
    cgst_pr = find_column(pr_map, ["cgst"])
    sgst_pr = find_column(pr_map, ["sgst"])

    # Validation
    if not gstin_2b or not invoice_2b:
        st.error("Required columns not found in GSTR-2B.")
        st.write("Available columns:", gstr2b.columns)
        st.stop()

    if not gstin_pr or not invoice_pr:
        st.error("Required columns not found in Purchase Register.")
        st.write("Available columns:", purchase.columns)
        st.stop()

    # Build clean DataFrames
    df_2b = pd.DataFrame({
        "GSTIN": gstr2b[gstin_2b],
        "Invoice": gstr2b[invoice_2b],
        "Date_2B": pd.to_datetime(gstr2b[date_2b], errors="coerce") if date_2b else None,
        "Taxable_2B": pd.to_numeric(gstr2b[taxable_2b], errors="coerce").fillna(0) if taxable_2b else 0,
        "IGST_2B": pd.to_numeric(gstr2b[igst_2b], errors="coerce").fillna(0) if igst_2b else 0,
        "CGST_2B": pd.to_numeric(gstr2b[cgst_2b], errors="coerce").fillna(0) if cgst_2b else 0,
        "SGST_2B": pd.to_numeric(gstr2b[sgst_2b], errors="coerce").fillna(0) if sgst_2b else 0
    })

    df_pr = pd.DataFrame({
        "GSTIN": purchase[gstin_pr],
        "Invoice": purchase[invoice_pr],
        "Date_PR": pd.to_datetime(purchase[date_pr], errors="coerce") if date_pr else None,
        "Taxable_PR": pd.to_numeric(purchase[taxable_pr], errors="coerce").fillna(0) if taxable_pr else 0,
        "IGST_PR": pd.to_numeric(purchase[igst_pr], errors="coerce").fillna(0) if igst_pr else 0,
        "CGST_PR": pd.to_numeric(purchase[cgst_pr], errors="coerce").fillna(0) if cgst_pr else 0,
        "SGST_PR": pd.to_numeric(purchase[sgst_pr], errors="coerce").fillna(0) if sgst_pr else 0
    })

    # Clean keys
    df_2b["GSTIN"] = df_2b["GSTIN"].astype(str).str.strip().str.upper()
    df_pr["GSTIN"] = df_pr["GSTIN"].astype(str).str.strip().str.upper()
    df_2b["Invoice"] = df_2b["Invoice"].astype(str).str.strip().str.upper()
    df_pr["Invoice"] = df_pr["Invoice"].astype(str).str.strip().str.upper()

    # Merge
    recon = pd.merge(df_pr, df_2b, on=["GSTIN", "Invoice"], how="outer", indicator=True)

    # Status + Reason Logic
    def generate_status_reason(row):

        if row["_merge"] == "left_only":
            return pd.Series(["Mismatch", "Missing in 2B"])

        if row["_merge"] == "right_only":
            return pd.Series(["Mismatch", "Missing in Purchase Register"])

        reasons = []

        if pd.notna(row["Date_PR"]) and pd.notna(row["Date_2B"]):
            if row["Date_PR"] != row["Date_2B"]:
                reasons.append("Invoice Date Mismatch")

        if round(row["Taxable_PR"],2) != round(row["Taxable_2B"],2):
            reasons.append("Taxable Value Mismatch")

        if round(row["IGST_PR"],2) != round(row["IGST_2B"],2):
            reasons.append("IGST Mismatch")

        if round(row["CGST_PR"],2) != round(row["CGST_2B"],2):
            reasons.append("CGST Mismatch")

        if round(row["SGST_PR"],2) != round(row["SGST_2B"],2):
            reasons.append("SGST Mismatch")

        if len(reasons) == 0:
            return pd.Series(["Matched", ""])

        return pd.Series(["Mismatch", ", ".join(reasons)])

    recon[["Status", "Reason"]] = recon.apply(generate_status_reason, axis=1)

    recon = recon.drop(columns=["_merge"])

    # Summary
    st.subheader("Reconciliation Summary")
    st.write(recon["Status"].value_counts())

    st.subheader("Detailed Reconciliation")
    st.dataframe(recon, use_container_width=True)

    # Export
    output_file = "GST_Reconciliation_Output.xlsx"
    recon.to_excel(output_file, index=False)

    with open(output_file, "rb") as f:
        st.download_button(
            "Download Excel Report",
            data=f,
            file_name="GST_Reconciliation_Output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
