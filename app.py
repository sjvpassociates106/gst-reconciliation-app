import streamlit as st
import pandas as pd
import re

st.title("GST Reconciliation Tool (2B vs Purchase Register)")

# ---------------------------
# FILE UPLOAD
# ---------------------------
file_2b = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
file_pr = st.file_uploader("Upload Purchase Register", type=["xlsx","xls","csv"])

# ---------------------------
# READ FUNCTIONS
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
        return digits[-1][-3:]   # last 3 digits
    
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
# PREPROCESS (AS PER YOUR FILE)
# ---------------------------
def preprocess_2b(df):
    new_df = pd.DataFrame()

    new_df["invoice"] = df["Invoice number"]
    new_df["date"] = df["Invoice Date"]
    new_df["party"] = df["GSTIN of supplier"]
    new_df["taxable"] = df["Taxable Value (₹)"]
    new_df["cgst"] = df["Central Tax(₹)"]
    new_df["sgst"] = df["State/UT Tax(₹)"]
    new_df["igst"] = df["Integrated Tax(₹)"]

    return clean_common(new_df)


def preprocess_pr(df):
    new_df = pd.DataFrame()

    new_df["invoice"] = df["Supplier Invoice No."]
    new_df["date"] = df["Date"]
    new_df["party"] = df["GSTIN/UIN"]
    new_df["taxable"] = df["Taxable Value"]
    new_df["cgst"] = df["CGST"]
    new_df["sgst"] = df["SGST"]
    new_df["igst"] = df["IGST"]

    return clean_common(new_df)


# ---------------------------
# MATCHING LOGIC
# ---------------------------
def match_data(df_pr, df_2b):

    result = []

    for _, row in df_pr.iterrows():
        matched = "Only in Purchase"

        for _, r2 in df_2b.iterrows():

            # GSTIN match (most important)
            if row["party_clean"] != r2["party_clean"]:
                continue

            # Invoice match
            if row["invoice_clean"] != r2["invoice_clean"]:
                continue

            # Amount tolerance
            if abs(row["taxable"] - r2["taxable"]) > 5:
                continue

            # Date tolerance
            if pd.notna(row["date"]) and pd.notna(r2["date"]):
                if abs((row["date"] - r2["date"]).days) > 3:
                    continue

            matched = "Matched"
            break

        result.append(matched)

    df_pr["Status"] = result

    # 2B side
    matched_keys = set(zip(df_pr[df_pr["Status"]=="Matched"]["invoice_clean"],
                           df_pr[df_pr["Status"]=="Matched"]["party_clean"]))

    df_2b["Status"] = df_2b.apply(
        lambda x: "Matched" if (x["invoice_clean"], x["party_clean"]) in matched_keys else "Only in 2B",
        axis=1
    )

    return df_pr, df_2b


# ---------------------------
# MAIN PROCESS
# ---------------------------
if file_2b and file_pr:

    df_2b_raw = read_2b_file(file_2b)
    df_pr_raw = read_file(file_pr)

    # DEBUG (optional remove later)
    st.write("2B RAW", df_2b_raw.head())
    st.write("PR RAW", df_pr_raw.head())

    df_2b = preprocess_2b(df_2b_raw)
    df_pr = preprocess_pr(df_pr_raw)

    # Remove duplicates
    df_2b = df_2b.drop_duplicates(subset=["invoice_clean", "party_clean", "taxable"])
    df_pr = df_pr.drop_duplicates(subset=["invoice_clean", "party_clean", "taxable"])

    df_pr, df_2b = match_data(df_pr, df_2b)

    st.success("Reconciliation Completed ✅")

    # Summary
    st.subheader("Summary")
    st.write(df_pr["Status"].value_counts())

    # Purchase Output
    st.subheader("Purchase Register Result")
    st.dataframe(df_pr)

    # 2B Output
    st.subheader("2B Result")
    st.dataframe(df_2b)

    # Download
    csv = df_pr.to_csv(index=False).encode("utf-8")
    st.download_button("Download Purchase Result", csv, "purchase_result.csv")
