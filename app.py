import streamlit as st
import pandas as pd
import re

st.title("GST Reconciliation Tool (2B vs Purchase Register)")

# ---------------------------
# FILE UPLOAD
# ---------------------------
file_2b = st.file_uploader("Upload GSTR-2B File", type=["xlsx", "csv"])
file_pr = st.file_uploader("Upload Purchase Register File", type=["xlsx", "csv"])

# ---------------------------
# HELPER FUNCTIONS
# ---------------------------

def detect_column(df, keywords):
    for col in df.columns:
        col_lower = col.lower()
        for key in keywords:
            if key in col_lower:
                return col
    return None

def clean_invoice(inv):
    if pd.isna(inv):
        return ""
    inv = str(inv).upper()
    
    # remove symbols
    inv = re.sub(r'[^A-Z0-9]', '', inv)
    
    # extract last 2-4 digits
    digits = re.findall(r'\d+', inv)
    if digits:
        core = digits[-1]
        return core[-4:]
    
    return inv

def preprocess(df):
    df.columns = df.columns.str.strip()

    col_map = {
        "invoice": detect_column(df, ["invoice", "bill", "inv"]),
        "date": detect_column(df, ["date"]),
        "party": detect_column(df, ["party", "supplier", "name"]),
        "taxable": detect_column(df, ["taxable", "value"]),
        "cgst": detect_column(df, ["cgst"]),
        "sgst": detect_column(df, ["sgst"]),
        "igst": detect_column(df, ["igst"]),
    }

    df_clean = pd.DataFrame()

    for key, col in col_map.items():
        if col:
            df_clean[key] = df[col]
        else:
            df_clean[key] = ""

    # Clean invoice number
    df_clean["invoice_clean"] = df_clean["invoice"].apply(clean_invoice)

    # Convert numeric
    for col in ["taxable", "cgst", "sgst", "igst"]:
        df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce").fillna(0)

    # Normalize party
    df_clean["party"] = df_clean["party"].astype(str).str.upper().str.strip()

    return df_clean

# ---------------------------
# MAIN LOGIC
# ---------------------------

if file_2b and file_pr:

    df_2b = pd.read_excel(file_2b) if file_2b.name.endswith("xlsx") else pd.read_csv(file_2b)
    df_pr = pd.read_excel(file_pr) if file_pr.name.endswith("xlsx") else pd.read_csv(file_pr)

    df_2b = preprocess(df_2b)
    df_pr = preprocess(df_pr)

    # Remove duplicates
    df_2b = df_2b.drop_duplicates(subset=["invoice_clean", "party", "taxable"])
    df_pr = df_pr.drop_duplicates(subset=["invoice_clean", "party", "taxable"])

    # Merge
    merged = pd.merge(
        df_pr,
        df_2b,
        on=["invoice_clean", "party"],
        how="outer",
        suffixes=("_pr", "_2b"),
        indicator=True
    )

    # Status
    merged["Status"] = merged["_merge"].map({
        "both": "Matched",
        "left_only": "Only in Purchase",
        "right_only": "Only in 2B"
    })

    st.success("Reconciliation Completed")

    # Summary
    st.subheader("Summary")
    st.write(merged["Status"].value_counts())

    # Detailed Output
    st.subheader("Detailed Reconciliation")
    st.dataframe(merged)

    # Download
    csv = merged.to_csv(index=False).encode('utf-8')
    st.download_button("Download Result", csv, "gst_reconciliation.csv", "text/csv")
