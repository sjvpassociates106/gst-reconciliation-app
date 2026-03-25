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
# 🔥 AI PARTY CLEANING
# ---------------------------
def clean_party_name(name):
    if pd.isna(name):
        return ""

    name = str(name).upper()

    # 🔥 REMOVE BRACKETS CONTENT (VERY IMPORTANT)
    name = re.sub(r'\(.*?\)', '', name)

    # remove common words
    remove_words = [
        "PVT", "PRIVATE", "LTD", "LIMITED",
        "LLP", "CO", "COMPANY", "INDIA"
    ]

    for word in remove_words:
        name = name.replace(word, "")

    # remove special characters
    name = re.sub(r'[^A-Z0-9]', '', name)

    return name


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
                st.write(f"✅ Purchase Header Found at Row: {i}")
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
        col_clean = str(col).lower()
        col_clean = col_clean.replace(" ", "").replace("\n", "").replace(".", "")

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

    # remove special chars
    inv = re.sub(r'[^A-Z0-9]', '', inv)

    # remove year patterns
    inv = re.sub(r'20\d{2}', '', inv)

    # 🔥 KEEP FULL NUMBER (NOT LAST 3 DIGITS)
    return inv


def clean_common(df):
    df["invoice"] = df["invoice"].astype(str)
    df["invoice_clean"] = df["invoice"].apply(clean_invoice)

    df["party"] = df["party"].astype(str)

    # 🔥 AI PARTY MATCHING
    df["party_clean"] = df["party"].apply(clean_party_name)

    # 🔥 SMART DATE HANDLING
    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
        dayfirst=True,
        infer_datetime_format=True
    )

    for col in ["taxable", "cgst", "sgst", "igst"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df = df.dropna(how="all")

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

    st.write("Detected 2B Columns:", {
        "invoice": inv_col,
        "date": date_col,
        "gstin": gst_col,
        "taxable": tax_col,
        "party_name": party_name_col
    })

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

    inv_col = get_col(df, ["supplierinvoice", "invoiceno", "invoice"])
    date_col = get_col(df, ["date"])
    gst_col = get_col(df, ["gstin"])
    tax_col = get_col(df, ["taxable"])
    cgst_col = get_col(df, ["cgst"])
    sgst_col = get_col(df, ["sgst"])
    igst_col = get_col(df, ["igst"])

    party_name_col = get_col(df, ["particular"])

    st.write("Detected PR Columns:", {
        "invoice": inv_col,
        "date": date_col,
        "gstin": gst_col,
        "taxable": tax_col,
        "party_name": party_name_col
    })

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
# RECONCILIATION
# ---------------------------
def is_close(a, b, tol=3):
    try:
        return abs(float(a) - float(b)) <= tol
    except:
        return False


def reconcile(df_pr, df_2b):

    df_pr["key"] = df_pr["party_clean"] + "_" + df_pr["invoice_clean"]
    df_2b["key"] = df_2b["party_clean"] + "_" + df_2b["invoice_clean"]

    result = []
    used_2b = set()

    for _, pr in df_pr.iterrows():
        match = df_2b[df_2b["key"] == pr["key"]]

        if not match.empty:
            r2 = match.iloc[0]
            used_2b.add(r2["key"])

            # ✅ DEFAULT
            status = "Matched"

            # 🔥 TOLERANCE LOGIC (FINAL FIX)
            if not is_close(pr["taxable"], r2["taxable"], 3):
                status = "Taxable Mismatch"

            elif not is_close(pr["cgst"], r2["cgst"], 2):
                status = "CGST Mismatch"

            elif not is_close(pr["sgst"], r2["sgst"], 2):
                status = "SGST Mismatch"

            elif not is_close(pr["igst"], r2["igst"], 2):
                status = "IGST Mismatch"

            result.append({
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
            result.append({
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

    # Remaining 2B
    for _, r2 in df_2b.iterrows():
        if r2["key"] not in used_2b:
            result.append({
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

    return pd.DataFrame(result)


# ---------------------------
# MAIN
# ---------------------------
if file_2b and file_pr:

    df_2b_raw = read_2b_file(file_2b)
    df_pr_raw = read_pr_file(file_pr)

    df_2b = preprocess_2b(df_2b_raw)
    df_pr = preprocess_pr(df_pr_raw)
    
    df_2b = df_2b.drop_duplicates(subset=["party_clean", "invoice_clean"])

    result_df = reconcile(df_pr, df_2b)

    st.success("✅ Reconciliation Completed")

    st.subheader("📊 Summary")
    st.write(result_df["Status"].value_counts())

    st.subheader("📋 Reconciliation Output")
    st.dataframe(result_df)

    csv = result_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download Result", csv, "gst_reconciliation.csv")
