import streamlit as st
import pandas as pd
import re

st.title("GST Reconciliation (2B vs Purchase Register)")

# ---------------------------
# FILE UPLOAD (FIXED KEY ERROR)
# ---------------------------
file_2b = st.file_uploader("Upload GSTR-2B File", type=["xlsx"], key="file_2b")
file_pr = st.file_uploader("Upload Purchase Register", type=["xlsx","xls","csv"], key="file_pr")


# ---------------------------
# PARTY CLEANING (AI MATCH)
# ---------------------------
def clean_party_name(name):
    if pd.isna(name):
        return ""

    name = str(name).upper()

    # remove brackets
    name = re.sub(r'\(.*?\)', '', name)

    # remove common words
    remove_words = ["PVT","PRIVATE","LTD","LIMITED","LLP","CO","COMPANY","INDIA"]
    for word in remove_words:
        name = name.replace(word, "")

    # remove symbols
    name = re.sub(r'[^A-Z0-9]', '', name)

    return name


# ---------------------------
# INVOICE CLEANING (FINAL FIX)
# ---------------------------
def clean_invoice(inv):
    if pd.isna(inv):
        return ""

    inv = str(inv).upper()

    numbers = re.findall(r'\d+', inv)

    if numbers:
        return numbers[0]   # 🔥 IMPORTANT (first number)

    return ""


# ---------------------------
# TOLERANCE CHECK
# ---------------------------
def is_close(a, b, tol=3):
    try:
        return abs(float(a) - float(b)) <= tol
    except:
        return False


# ---------------------------
# READ FILES
# ---------------------------
def read_2b_file(file):
    xls = pd.ExcelFile(file, engine="openpyxl")

    for sheet in xls.sheet_names:
        if "b2b" in sheet.lower():
            for i in range(10):
                df = pd.read_excel(xls, sheet_name=sheet, header=i)
                if any("invoice" in str(c).lower() for c in df.columns):
                    return df

    st.error("❌ B2B not found")
    st.stop()


def read_pr_file(file):
    for i in range(20):
        try:
            df = pd.read_excel(file, header=i)
            if any("invoice" in str(c).lower() for c in df.columns):
                return df
        except:
            continue

    return pd.read_csv(file)


# ---------------------------
# COLUMN FINDER
# ---------------------------
def get_col(df, keys):
    for col in df.columns:
        c = str(col).lower().replace(" ","")
        if any(k in c for k in keys):
            return col
    return None


# ---------------------------
# COMMON CLEANING
# ---------------------------
def clean_common(df):
    df["invoice_clean"] = df["invoice"].apply(clean_invoice)
    df["party_clean"] = df["party"].apply(clean_party_name)

    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)

    for c in ["taxable","cgst","sgst","igst"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    return df


# ---------------------------
# PREPROCESS 2B
# ---------------------------
def preprocess_2b(df):

    inv = get_col(df, ["invoice"])
    date = get_col(df, ["date"])
    party = get_col(df, ["trade","legal","name"])
    gst = get_col(df, ["gstin"])
    tax = get_col(df, ["taxable"])
    cgst = get_col(df, ["central"])
    sgst = get_col(df, ["state"])
    igst = get_col(df, ["integrated"])

    new = pd.DataFrame()
    new["invoice"] = df[inv]
    new["date"] = df[date]
    new["party"] = df[party] if party else df[gst]
    new["taxable"] = df[tax]
    new["cgst"] = df[cgst] if cgst else 0
    new["sgst"] = df[sgst] if sgst else 0
    new["igst"] = df[igst] if igst else 0

    return clean_common(new)


# ---------------------------
# PREPROCESS PR
# ---------------------------
def preprocess_pr(df):

    inv = get_col(df, ["invoice","supplier"])
    date = get_col(df, ["date"])
    party = get_col(df, ["particular"])
    gst = get_col(df, ["gstin"])
    tax = get_col(df, ["taxable"])
    cgst = get_col(df, ["cgst"])
    sgst = get_col(df, ["sgst"])
    igst = get_col(df, ["igst"])

    new = pd.DataFrame()
    new["invoice"] = df[inv]
    new["date"] = df[date]
    new["party"] = df[party] if party else df[gst]
    new["taxable"] = df[tax]
    new["cgst"] = df[cgst]
    new["sgst"] = df[sgst]
    new["igst"] = df[igst]

    return clean_common(new)


# ---------------------------
# RECONCILE
# ---------------------------
def reconcile(pr, b2b):

    b2b = b2b.drop_duplicates(subset=["party_clean","invoice_clean"])

    pr["key"] = pr["party_clean"] + "_" + pr["invoice_clean"]
    b2b["key"] = b2b["party_clean"] + "_" + b2b["invoice_clean"]

    result = []

    for _, r in pr.iterrows():
        m = b2b[b2b["key"] == r["key"]]

        if not m.empty:
            b = m.iloc[0]

            status = "Matched"

            if not is_close(r["taxable"], b["taxable"], 3):
                status = "Taxable Mismatch"
            elif not is_close(r["cgst"], b["cgst"], 2):
                status = "CGST Mismatch"
            elif not is_close(r["sgst"], b["sgst"], 2):
                status = "SGST Mismatch"
            elif not is_close(r["igst"], b["igst"], 2):
                status = "IGST Mismatch"

        else:
            b = {}
            status = "Not in 2B"

        result.append({
            "Party PR": r["party"],
            "Invoice PR": r["invoice"],
            "Taxable PR": r["taxable"],
            "Party 2B": b.get("party",""),
            "Invoice 2B": b.get("invoice",""),
            "Taxable 2B": b.get("taxable",""),
            "Status": status
        })

    return pd.DataFrame(result)


# ---------------------------
# MAIN
# ---------------------------
if file_2b and file_pr:

    df_2b = preprocess_2b(read_2b_file(file_2b))
    df_pr = preprocess_pr(read_pr_file(file_pr))

    result = reconcile(df_pr, df_2b)

    st.success("✅ Done")

    st.write(result["Status"].value_counts())
    st.dataframe(result)

    st.download_button("Download CSV", result.to_csv(index=False), "result.csv")
