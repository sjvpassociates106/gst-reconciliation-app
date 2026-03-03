import streamlit as st
import pandas as pd

st.set_page_config(page_title="Enterprise GST Reconciliation", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])


# -------------------------------------------------------
# AUTO DETECT HEADER ROW FUNCTION
# -------------------------------------------------------

def detect_header_row(file, required_keywords):
    raw = pd.read_excel(file, header=None)

    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).str.lower()

        match_count = 0
        for keyword in required_keywords:
            if row.str.contains(keyword).any():
                match_count += 1

        if match_count >= 2:  # at least 2 required words found
            return i

    return None


# -------------------------------------------------------
# FIND COLUMN BY KEYWORDS
# -------------------------------------------------------

def find_column(columns, keywords):
    for col in columns:
        clean = col.lower().replace(" ", "").replace("₹", "").replace(".", "")
        for key in keywords:
            if key in clean:
                return col
    return None


# -------------------------------------------------------
# MAIN PROCESS
# -------------------------------------------------------

if gstr2b_file and purchase_file:

    # Detect header rows
    gstr2b_header = detect_header_row(
        gstr2b_file,
        ["gstin", "invoice", "taxable"]
    )

    purchase_header = detect_header_row(
        purchase_file,
        ["date", "invoice", "gstin"]
    )

    if gstr2b_header is None:
        st.error("Could not detect GSTR-2B header row automatically.")
        st.stop()

    if purchase_header is None:
        st.error("Could not detect Purchase Register header row automatically.")
        st.stop()

    # Load with correct headers
    gstr2b = pd.read_excel(gstr2b_file, header=gstr2b_header)
    purchase = pd.read_excel(purchase_file, header=purchase_header)

    gstr2b.columns = gstr2b.columns.astype(str).str.strip()
    purchase.columns = purchase.columns.astype(str).str.strip()

    # -------------------------------------------------------
    # DETECT REQUIRED COLUMNS FROM 2B
    # -------------------------------------------------------

    gstin_2b = find_column(gstr2b.columns, ["gstin"])
    invoice_2b = find_column(gstr2b.columns, ["invoice"])
    date_2b = find_column(gstr2b.columns, ["date"])
    taxable_2b = find_column(gstr2b.columns, ["taxable"])
    igst_2b = find_column(gstr2b.columns, ["integrated", "igst"])
    cgst_2b = find_column(gstr2b.columns, ["central", "cgst"])
    sgst_2b = find_column(gstr2b.columns, ["state", "sgst"])

    # -------------------------------------------------------
    # DETECT REQUIRED COLUMNS FROM PURCHASE
    # -------------------------------------------------------

    gstin_pr = find_column(purchase.columns, ["gstin"])
    invoice_pr = find_column(purchase.columns, ["supplierinvoiceno", "invoice"])
    date_pr = find_column(purchase.columns, ["date"])
    igst_pr = find_column(purchase.columns, ["igst"])
    cgst_pr = find_column(purchase.columns, ["cgst"])
    sgst_pr = find_column(purchase.columns, ["sgst"])
    taxable_pr = find_column(purchase.columns, ["taxable", "value", "gross"])

    # Basic required validation
    if not gstin_2b or not invoice_2b:
        st.error("Required columns missing in GSTR-2B.")
        st.write(gstr2b.columns)
        st.stop()

    if not gstin_pr or not invoice_pr:
        st.error("Required columns missing in Purchase Register.")
        st.write(purchase.columns)
        st.stop()

    # -------------------------------------------------------
    # BUILD CLEAN DATAFRAMES (IGNORE OTHER COLUMNS)
    # -------------------------------------------------------

    df_2b = pd.DataFrame({
        "GSTIN": gstr2b[gstin_2b],
        "Invoice": gstr2b[invoice_2b],
        "Date": gstr2b[date_2b] if date_2b else "",
        "Taxable_2B": pd.to_numeric(gstr2b[taxable_2b], errors="coerce").fillna(0) if taxable_2b else 0,
        "IGST_2B": pd.to_numeric(gstr2b[igst_2b], errors="coerce").fillna(0) if igst_2b else 0,
        "CGST_2B": pd.to_numeric(gstr2b[cgst_2b], errors="coerce").fillna(0) if cgst_2b else 0,
        "SGST_2B": pd.to_numeric(gstr2b[sgst_2b], errors="coerce").fillna(0) if sgst_2b else 0
    })

    df_pr = pd.DataFrame({
        "GSTIN": purchase[gstin_pr],
        "Invoice": purchase[invoice_pr],
        "Date": purchase[date_pr] if date_pr else "",
        "Taxable_PR": pd.to_numeric(purchase[taxable_pr], errors="coerce").fillna(0) if taxable_pr else 0,
        "IGST_PR": pd.to_numeric(purchase[igst_pr], errors="coerce").fillna(0) if igst_pr else 0,
        "CGST_PR": pd.to_numeric(purchase[cgst_pr], errors="coerce").fillna(0) if cgst_pr else 0,
        "SGST_PR": pd.to_numeric(purchase[sgst_pr], errors="coerce").fillna(0) if sgst_pr else 0
    })

    # Clean keys
    df_2b["Invoice"] = df_2b["Invoice"].astype(str).str.strip().str.upper()
    df_pr["Invoice"] = df_pr["Invoice"].astype(str).str.strip().str.upper()

    df_2b["GSTIN"] = df_2b["GSTIN"].astype(str).str.strip()
    df_pr["GSTIN"] = df_pr["GSTIN"].astype(str).str.strip()

    # -------------------------------------------------------
    # MERGE
    # -------------------------------------------------------

    recon = pd.merge(df_pr, df_2b, on=["GSTIN", "Invoice"], how="outer", indicator=True)

    recon["Taxable_Diff"] = recon["Taxable_PR"] - recon["Taxable_2B"]
    recon["IGST_Diff"] = recon["IGST_PR"] - recon["IGST_2B"]
    recon["CGST_Diff"] = recon["CGST_PR"] - recon["CGST_2B"]
    recon["SGST_Diff"] = recon["SGST_PR"] - recon["SGST_2B"]

    # Status
    def classify(row):
        if row["_merge"] == "both":
            if row["Taxable_Diff"] != 0 or row["IGST_Diff"] != 0 \
               or row["CGST_Diff"] != 0 or row["SGST_Diff"] != 0:
                return "Tax Mismatch"
            return "Matched"
        elif row["_merge"] == "left_only":
            return "Missing in 2B"
        else:
            return "Missing in Purchase"

    recon["Status"] = recon.apply(classify, axis=1)

    # -------------------------------------------------------
    # OUTPUT
    # -------------------------------------------------------

    st.subheader("Reconciliation Summary")

    col1, col2, col3 = st.columns(3)
    col1.metric("Matched", (recon["Status"] == "Matched").sum())
    col2.metric("Tax Mismatch", (recon["Status"] == "Tax Mismatch").sum())
    col3.metric("Missing in 2B", (recon["Status"] == "Missing in 2B").sum())

    st.subheader("Detailed Reconciliation")
    st.dataframe(recon, use_container_width=True)

    st.download_button(
        "Download Reconciliation Report",
        data=recon.to_csv(index=False),
        file_name="GST_Reconciliation_Report.csv",
        mime="text/csv"
    )
