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
# 🔥 PARTY CLEANING
# ---------------------------
def clean_party_name(name):
    if pd.isna(name):
        return ""

    name = str(name).upper()

    remove_words = [
        "PVT", "PRIVATE", "LTD", "LIMITED",
        "LLP", "CO", "COMPANY", "INDIA"
    ]

    for word in remove_words:
        name = name.replace(word, "")

    name = re.sub(r'[^A-Z0-9]', '', name)

    return name


# ---------------------------
# 🔥 AMOUNT TOLERANCE FUNCTION
# ---------------------------
def is_close(a, b, tol=3):
    try:
        return abs(float(a) - float(b)) <= tol
    except:
        return False


# ---------------------------
# READ 2B FILE
# ---------------------------
def read_2b_file(file):
    xls = pd.ExcelFile(file, engine="openpyxl")

    for sheet in xls.sheet_names:
        if "b2b" in sheet.lower():
            for i in range(10):
                df = pd.read_excel(xls, sheet_name=sheet, header=i)
                cols = [str(c).lower() for c in df.columns]

                if any("invoice" in c for c in cols):
                    return df

    st.error("❌ B2B sheet/header not detected")
    st.stop()


# ---------------------------
# READ PURCHASE FILE
# ---------------------------
def read_pr_file(file):
    try:
        for i in range(20):
            df = pd.read_excel(file, header=i)
            cols = [str(c).lower() for c in df.columns]

            if any(("invoice" in c or "supplier" in c or "gstin" in c) for c in cols):
                return df

        st.error("❌ Purchase header not detected")
        st.stop()

    except:
        try:
            return pd.read_csv(file, encoding="utf-8")
        except:
            return pd.read_csv(file, encoding="latin1")


# ---------------------------
# COLUMN FINDER
# ---------------------------
def get_col(df, keywords):
    for col in df.columns:
        col_clean = str(col).lower().replace(" ", "").replace("\n", "").replace(".", "")
        for key in keywords:
            if key in col_clean:
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
    df["party_clean"] = df["party"].apply(clean_party_name)

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
        dayfirst=True,
        infer_datetime_format=True
    )

    for col in ["taxable", "cgst", "sgst", "igst"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


# ---------------------------
# PREPROCESS 2B
# ---------------------------
def preprocess_2b(df):
    new_df = pd.DataFrame()

    inv_col = get_col(df, ["invoice"])
    date_col = get_col(df, ["date"])
    gst_col = get_col(df, ["gstin"])
    tax_col = get_col(df, ["taxable"])
    cgst_col = get_col(df, ["central"])
    sgst_col = get_col(df, ["state"])
    igst_col = get_col(df, ["integrated"])
    party_name_col = get_col(df, ["trade", "legal", "name"])

    if inv_col is None:
        st.error("❌ Invoice column not found in 2B")
        st.stop()

    new_df["invoice"] = df[inv_col]
    new_df["date"] = df[date_col] if date_col else ""

    if party_name_col:
        new_df["party"] = df[party_name_col]
    else:
        new_df["party"] = df[gst_col] if gst_col else ""

    new_df["taxable"] = df[tax_col] if tax_col else 0
    new_df["cgst"] = df[cgst_col] if cgst_col else 0
    new_df["sgst"] = df[sgst_col] if sgst_col else 0
    new_df["igst"] = df[igst_col] if igst_col else 0

    return clean_common(new_df)


# ---------------------------
# PREPROCESS PURCHASE
# ---------------------------
def preprocess_pr(df):
    new_df = pd.DataFrame()

    inv_col = get_col(df, ["supplierinvoice", "invoice"])
    date_col = get_col(df, ["date"])
    gst_col = get_col(df, ["gstin"])
    tax_col = get_col(df, ["taxable"])
    cgst_col = get_col(df, ["cgst"])
    sgst_col = get_col(df, ["sgst"])
    igst_col = get_col(df, ["igst"])
    party_name_col = get_col(df, ["particular"])

    if inv_col is None:
        st.error("❌ Invoice column not found in Purchase Register")
        st.stop()

    new_df["invoice"] = df[inv_col]
    new_df["date"] = df[date_col] if date_col else ""

    if party_name_col:
        new_df["party"] = df[party_name_col]
    else:
        new_df["party"] = df[gst_col] if gst_col else ""

    new_df["taxable"] = df[tax_col] if tax_col else 0
    new_df["cgst"] = df[cgst_col] if cgst_col else 0
    new_df["sgst"] = df[sgst_col] if sgst_col else 0
    new_df["igst"] = df[igst_col] if igst_col else 0

    return clean_common(new_df)


# ---------------------------
# RECONCILIATION (WITH TOLERANCE)
# ---------------------------
def reconcile(df_pr, df_2b):

    df_pr["key"] = df_pr["party_clean"] + "_" + df_pr["invoice_clean"]
    df_2b["key"] = df_2b["party_clean"] + "_" + df_2b["invoice_clean"]

    result = []

    for _, pr in df_pr.iterrows():
        match = df_2b[df_2b["key"] == pr["key"]]

        if not match.empty:
            r2 = match.iloc[0]

            status = "Matched"

            # 🔥 TOLERANCE LOGIC
            if not is_close(pr["taxable"], r2["taxable"], 3):
                status = "Taxable Mismatch"
            elif not is_close(pr["cgst"], r2["cgst"], 2):
                status = "CGST Mismatch"
            elif not is_close(pr["sgst"], r2["sgst"], 2):
                status = "SGST Mismatch"
            elif not is_close(pr["igst"], r2["igst"], 2):
                status = "IGST Mismatch"

        else:
            r2 = {}

            status = "Not in 2B"

        result.append({
            "Party PR": pr["party"],
            "Invoice PR": pr["invoice"],
            "Taxable PR": pr["taxable"],

            "Party 2B": r2.get("party", ""),
            "Invoice 2B": r2.get("invoice", ""),
            "Taxable 2B": r2.get("taxable", ""),

            "Status": status
        })

    return pd.DataFrame(result)


# ---------------------------
# MAIN
# ---------------------------
if file_2b and file_pr:

    df_2b = preprocess_2b(read_2b_file(file_2b))
    df_pr = preprocess_pr(read_pr_file(file_pr))

    result_df = reconcile(df_pr, df_2b)

    st.success("✅ Reconciliation Completed")

    st.write(result_df["Status"].value_counts())
    st.dataframe(result_df)

    st.download_button(
        "Download Result",
        result_df.to_csv(index=False).encode("utf-8"),
        "gst_reconciliation.csv"
    )
