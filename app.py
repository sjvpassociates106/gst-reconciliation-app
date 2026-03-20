import streamlit as st
import pandas as pd
import re

st.title("GST Reconciliation (2B vs Purchase Register)")

# ---------------------------
# FILE UPLOAD
# ---------------------------
file_2b = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
file_pr = st.file_uploader("Upload Purchase Register", type=["xlsx","xls","csv"])

# ---------------------------
# READ FILES
# ---------------------------
def read_2b_file(file):
    xls = pd.ExcelFile(file, engine="openpyxl")
    for sheet in xls.sheet_names:
        if "b2b" in sheet.lower():
            return pd.read_excel(xls, sheet_name=sheet)
    st.error("B2B sheet not found")
    return None

def read_file(file):
    try:
        return pd.read_excel(file, engine="openpyxl")
    except:
        try:
            return pd.read_csv(file, encoding="utf-8")
        except:
            return pd.read_csv(file, encoding="latin1")

# ---------------------------
# SAFE COLUMN FINDER
# ---------------------------
def get_col(df, keyword):
    for col in df.columns:
        if keyword.lower() in col.lower():
            return col
    return None

# ---------------------------
# CLEANING
# ---------------------------
def clean_invoice(inv):
    if pd.isna(inv):
        return ""
    inv = str(inv).upper()
    inv = re.sub(r'[^A-Z0-9]', '', inv)
    inv = re.sub(r'20\d{2}', '', inv)
    digits = re.findall(r'\d+', inv)
    if digits:
        return digits[-1][-3:]
    return inv

def clean_common(df):
    df["invoice"] = df["invoice"].astype(str)
    df["invoice_clean"] = df["invoice"].apply(clean_invoice)

    df["party"] = df["party"].astype(str)
    df["party_clean"] = df["party"].str.replace(" ", "").str.upper()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for col in ["taxable", "cgst", "sgst", "igst"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df = df.dropna(how="all")

    return df

# ---------------------------
# PREPROCESS
# ---------------------------
def preprocess_2b(df):
    new_df = pd.DataFrame()

    new_df["invoice"] = df[get_col(df, "invoice")]
    new_df["date"] = df[get_col(df, "date")]
    new_df["party"] = df[get_col(df, "gstin")]
    new_df["taxable"] = df[get_col(df, "taxable")]
    new_df["cgst"] = df[get_col(df, "central")]
    new_df["sgst"] = df[get_col(df, "state")]
    new_df["igst"] = df[get_col(df, "integrated")]

    return clean_common(new_df)

def preprocess_pr(df):
    new_df = pd.DataFrame()

    new_df["invoice"] = df[get_col(df, "invoice")]
    new_df["date"] = df[get_col(df, "date")]
    new_df["party"] = df[get_col(df, "gstin")]
    new_df["taxable"] = df[get_col(df, "taxable")]
    new_df["cgst"] = df[get_col(df, "cgst")]
    new_df["sgst"] = df[get_col(df, "sgst")]
    new_df["igst"] = df[get_col(df, "igst")]

    return clean_common(new_df)

# ---------------------------
# RECONCILIATION LOGIC
# ---------------------------
def reconcile(df_pr, df_2b):

    df_pr["key"] = df_pr["party_clean"] + "_" + df_pr["invoice_clean"]
    df_2b["key"] = df_2b["party_clean"] + "_" + df_2b["invoice_clean"]

    result_rows = []
    used_2b = set()

    for _, pr in df_pr.iterrows():

        match = df_2b[df_2b["key"] == pr["key"]]

        if not match.empty:
            r2 = match.iloc[0]
            used_2b.add(r2["key"])

            status = "Matched"

            if abs(pr["taxable"] - r2["taxable"]) > 1:
                status = "Taxable Mismatch"
            if abs(pr["cgst"] - r2["cgst"]) > 1:
                status = "CGST Mismatch"
            if abs(pr["sgst"] - r2["sgst"]) > 1:
                status = "SGST Mismatch"
            if abs(pr["igst"] - r2["igst"]) > 1:
                status = "IGST Mismatch"

            result_rows.append({
                "Date PR": pr["date"],
                "Party PR": pr["party"],
                "Invoice PR": pr["invoice"],
                "Taxable PR": pr["taxable"],
                "CGST PR": pr["cgst"],
                "SGST PR": pr["sgst"],
                "IGST PR": pr["igst"],

                "Date 2B": r2["date"],
                "Party 2B": r2["party"],
                "Invoice 2B": r2["invoice"],
                "Taxable 2B": r2["taxable"],
                "CGST 2B": r2["cgst"],
                "SGST 2B": r2["sgst"],
                "IGST 2B": r2["igst"],

                "Status": status
            })

        else:
            result_rows.append({
                "Date PR": pr["date"],
                "Party PR": pr["party"],
                "Invoice PR": pr["invoice"],
                "Taxable PR": pr["taxable"],
                "CGST PR": pr["cgst"],
                "SGST PR": pr["sgst"],
                "IGST PR": pr["igst"],

                "Date 2B": "",
                "Party 2B": "",
                "Invoice 2B": "",
                "Taxable 2B": "",
                "CGST 2B": "",
                "SGST 2B": "",
                "IGST 2B": "",

                "Status": "Not in 2B"
            })

    for _, r2 in df_2b.iterrows():
        if r2["key"] not in used_2b:
            result_rows.append({
                "Date PR": "",
                "Party PR": "",
                "Invoice PR": "",
                "Taxable PR": "",
                "CGST PR": "",
                "SGST PR": "",
                "IGST PR": "",

                "Date 2B": r2["date"],
                "Party 2B": r2["party"],
                "Invoice 2B": r2["invoice"],
                "Taxable 2B": r2["taxable"],
                "CGST 2B": r2["cgst"],
                "SGST 2B": r2["sgst"],
                "IGST 2B": r2["igst"],

                "Status": "Not in Purchase"
            })

    return pd.DataFrame(result_rows)

# ---------------------------
# MAIN
# ---------------------------
if file_2b and file_pr:

    df_2b_raw = read_2b_file(file_2b)
    df_pr_raw = read_file(file_pr)

    df_2b = preprocess_2b(df_2b_raw)
    df_pr = preprocess_pr(df_pr_raw)

    df_pr = df_pr.drop_duplicates(subset=["invoice_clean", "party_clean"])
    df_2b = df_2b.drop_duplicates(subset=["invoice_clean", "party_clean"])

    result_df = reconcile(df_pr, df_2b)

    st.success("Reconciliation Completed ✅")

    # ---------------------------
    # SUMMARY
    # ---------------------------
    st.subheader("📊 Summary")

    st.write("Total Records:", len(result_df))
    st.write("Matched:", len(result_df[result_df["Status"] == "Matched"]))
    st.write("Not in 2B:", len(result_df[result_df["Status"] == "Not in 2B"]))
    st.write("Not in Purchase:", len(result_df[result_df["Status"] == "Not in Purchase"]))

    # ---------------------------
    # OUTPUT
    # ---------------------------
    st.subheader("📋 Reconciliation Output")
    st.dataframe(result_df)

    # Download
    csv = result_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download Result", csv, "gst_reconciliation.csv")
