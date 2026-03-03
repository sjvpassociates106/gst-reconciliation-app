import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="GST Reconciliation", layout="wide")
st.title("GST Reconciliation - Enterprise Version")


gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])


# ------------------------------------------------------
# CLEAN FUNCTION
# ------------------------------------------------------

def clean_col(col):
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


# ------------------------------------------------------
# LOAD B2B SHEET SAFELY
# ------------------------------------------------------

def load_b2b(file):
    excel = pd.ExcelFile(file)

    if "B2B" not in excel.sheet_names:
        st.error("B2B sheet not found.")
        st.stop()

    raw = excel.parse("B2B", header=None)

    header_row = None
    for i in range(len(raw)):
        if raw.iloc[i].astype(str).str.contains("gstin", case=False).any():
            header_row = i
            break

    if header_row is None:
        st.error("Header not detected in B2B sheet.")
        st.stop()

    df = excel.parse("B2B", header=header_row)
    df.columns = df.columns.str.strip()
    return df


# ------------------------------------------------------
# MAIN PROCESS
# ------------------------------------------------------

if gstr2b_file and purchase_file:

    gstr2b = load_b2b(gstr2b_file)
    purchase = pd.read_excel(purchase_file)
    purchase.columns = purchase.columns.str.strip()

    g2b_map = {col: clean_col(col) for col in gstr2b.columns}
    pr_map = {col: clean_col(col) for col in purchase.columns}

    # Flexible matching
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
    taxable_pr = find_column(pr_map, ["taxable", "value", "gross"])
    igst_pr = find_column(pr_map, ["igst"])
    cgst_pr = find_column(pr_map, ["cgst"])
    sgst_pr = find_column(pr_map, ["sgst"])

    if not gstin_2b or not invoice_2b:
        st.error("Invoice or GSTIN column not found in GSTR-2B.")
        st.write("Available columns:", gstr2b.columns)
        st.stop()

    if not gstin_pr or not invoice_pr:
        st.error("Invoice or GSTIN column not found in Purchase Register.")
        st.write("Available columns:", purchase.columns)
        st.stop()

    # Build DataFrames safely
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

    # Differences
    recon["Taxable_Diff"] = recon["Taxable_PR"] - recon["Taxable_2B"]
    recon["IGST_Diff"] = recon["IGST_PR"] - recon["IGST_2B"]
    recon["CGST_Diff"] = recon["CGST_PR"] - recon["CGST_2B"]
    recon["SGST_Diff"] = recon["SGST_PR"] - recon["SGST_2B"]

    # Reason Logic
    def reason(row):
        if row["_merge"] == "left_only":
            return "Missing in 2B"
        if row["_merge"] == "right_only":
            return "Missing in Purchase"

        issues = []

        if row["Taxable_Diff"] != 0:
            issues.append("Taxable Mismatch")
        if row["IGST_Diff"] != 0:
            issues.append("IGST Mismatch")
        if row["CGST_Diff"] != 0:
            issues.append("CGST Mismatch")
        if row["SGST_Diff"] != 0:
            issues.append("SGST Mismatch")

        if not issues:
            return "Matched"

        return ", ".join(issues)

    recon["Status"] = recon.apply(reason, axis=1)

    st.subheader("Summary")
    st.write(recon["Status"].value_counts())

    st.subheader("Detailed Output")
    st.dataframe(recon, use_container_width=True)

    recon.to_excel("GST_Reconciliation_Output.xlsx", index=False)

    with open("GST_Reconciliation_Output.xlsx", "rb") as f:
        st.download_button(
            "Download Excel Report",
            data=f,
            file_name="GST_Reconciliation_Output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
