import streamlit as st
import pandas as pd
import re
from rapidfuzz import fuzz

st.title("GST Reconciliation (2B vs Purchase Register) - PRO VERSION")

# ---------------------------
# FILE UPLOAD
# ---------------------------
file_2b = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
file_pr = st.file_uploader("Upload Purchase Register", type=["xlsx","xls","csv"])

# ---------------------------
# READ FILE FUNCTIONS
# ---------------------------
def read_file(file):
    try:
        return pd.read_excel(file, engine="openpyxl")
    except:
        try:
            return pd.read_csv(file, encoding="utf-8")
        except:
            return pd.read_csv(file, encoding="latin1")

def read_2b_file(file):
    xls = pd.ExcelFile(file, engine="openpyxl")
    
    for sheet in xls.sheet_names:
        if "b2b" in sheet.lower():
            return pd.read_excel(xls, sheet_name=sheet)
    
    st.error("B2B sheet not found")
    return None

# ---------------------------
# COLUMN DETECTION
# ---------------------------
def detect_column(df, keywords):
    for col in df.columns:
        for key in keywords:
            if key in col.lower():
                return col
    return None

# ---------------------------
# CLEANING FUNCTIONS
# ---------------------------
def clean_invoice(inv):
    if pd.isna(inv):
        return ""
    
    inv = str(inv).upper()
    
    # remove symbols
    inv = re.sub(r'[^A-Z0-9]', '', inv)
    
    # remove year
    inv = re.sub(r'20\d{2}', '', inv)
    
    digits = re.findall(r'\d+', inv)
    
    if digits:
        return digits[-1][-3:]  # last 3 digits
    
    return inv

def clean_party(p):
    return str(p).upper().replace(" ", "").strip()

# ---------------------------
# PREPROCESS
# ---------------------------
def preprocess(df):
    df.columns = df.columns.str.strip()
    
    col_map = {
        "invoice": detect_column(df, ["invoice", "bill"]),
        "date": detect_column(df, ["date"]),
        "party": detect_column(df, ["party", "supplier", "gstin"]),
        "taxable": detect_column(df, ["taxable"]),
        "cgst": detect_column(df, ["cgst"]),
        "sgst": detect_column(df, ["sgst"]),
        "igst": detect_column(df, ["igst"]),
    }

    new_df = pd.DataFrame()
    
    for key, col in col_map.items():
        new_df[key] = df[col] if col else ""
    
    new_df["invoice_clean"] = new_df["invoice"].apply(clean_invoice)
    new_df["party_clean"] = new_df["party"].apply(clean_party)

    # numeric
    for col in ["taxable", "cgst", "sgst", "igst"]:
        new_df[col] = pd.to_numeric(new_df[col], errors="coerce").fillna(0)

    # date
    new_df["date"] = pd.to_datetime(new_df["date"], errors="coerce")

    return new_df

# ---------------------------
# MATCHING LOGIC
# ---------------------------
def match_row(row, df_2b):
    for _, r2 in df_2b.iterrows():
        
        # Invoice match
        if row["invoice_clean"] != r2["invoice_clean"]:
            continue
        
        # Party fuzzy match
        if fuzz.ratio(row["party_clean"], r2["party_clean"]) < 80:
            continue
        
        # Amount tolerance
        if abs(row["taxable"] - r2["taxable"]) > 5:
            continue
        
        # Date tolerance
        if pd.notna(row["date"]) and pd.notna(r2["date"]):
            if abs((row["date"] - r2["date"]).days) > 3:
                continue
        
        return "Matched"
    
    return "Not Matched"

# ---------------------------
# MAIN PROCESS
# ---------------------------
if file_2b and file_pr:
    
    df_2b = read_2b_file(file_2b)
    df_pr = read_file(file_pr)

    df_2b = preprocess(df_2b)
    df_pr = preprocess(df_pr)

    # remove duplicates
    df_2b = df_2b.drop_duplicates(subset=["invoice_clean", "party_clean", "taxable"])
    df_pr = df_pr.drop_duplicates(subset=["invoice_clean", "party_clean", "taxable"])

    # Matching
    df_pr["Status"] = df_pr.apply(lambda row: match_row(row, df_2b), axis=1)

    # Identify missing in 2B
    matched_invoices = df_pr[df_pr["Status"] == "Matched"]["invoice_clean"]
    df_2b["Status"] = df_2b["invoice_clean"].apply(
        lambda x: "Matched" if x in matched_invoices.values else "Only in 2B"
    )

    st.success("Reconciliation Completed ✅")

    # Summary
    st.subheader("Summary")
    st.write(df_pr["Status"].value_counts())

    # Output
    st.subheader("Purchase Register Result")
    st.dataframe(df_pr)

    st.subheader("2B Result")
    st.dataframe(df_2b)

    # Download
    csv = df_pr.to_csv(index=False).encode('utf-8')
    st.download_button("Download Purchase Result", csv, "purchase_result.csv")
