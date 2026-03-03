import streamlit as st
import pandas as pd

st.set_page_config(page_title="Enterprise GST Reconciliation", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])


# -----------------------------
# AUTO HEADER DETECTION
# -----------------------------

def load_with_auto_header(file):
    temp = pd.read_excel(file, header=None)

    for i in range(15):
        row = temp.iloc[i].astype(str).str.lower()
        if row.str.contains("gstin").any() and row.str.contains("invoice").any():
            return pd.read_excel(file, header=i)

    return pd.read_excel(file)


# -----------------------------
# AUTO COLUMN DETECTION
# -----------------------------

def detect_column(columns, keywords):
    for col in columns:
        clean = col.lower().replace(" ", "").replace("₹", "").replace(".", "")
        for key in keywords:
            if key in clean:
                return col
    return None


# -----------------------------
# LOAD FILES
# -----------------------------

if gstr2b_file and purchase_file:

    gstr2b = load_with_auto_header(gstr2b_file)
    purchase = load_with_auto_header(purchase_file)

    gstr2b.columns = gstr2b.columns.astype(str).str.strip()
    purchase.columns = purchase.columns.astype(str).str.strip()

    # Detect 2B columns
    gstin_2b = detect_column(gstr2b.columns, ["gstin"])
    party_2b = detect_column(gstr2b.columns, ["legal", "trade"])
    invoice_2b = detect_column(gstr2b.columns, ["invoicenumber", "invoice"])
    date_2b = detect_column(gstr2b.columns, ["date"])
    taxable_2b = detect_column(gstr2b.columns, ["taxable"])
    igst_2b = detect_column(gstr2b.columns, ["integrated", "igst"])
    cgst_2b = detect_column(gstr2b.columns, ["central", "cgst"])
    sgst_2b = detect_column(gstr2b.columns, ["state", "sgst"])

    # Detect Purchase columns
    gstin_pr = detect_column(purchase.columns, ["gstin"])
    party_pr = detect_column(purchase.columns, ["particular"])
    invoice_pr = detect_column(purchase.columns, ["supplierinvoiceno", "invoiceno", "invoice"])
    date_pr = detect_column(purchase.columns, ["date"])
    taxable_pr = detect_column(purchase.columns, ["taxable"])
    igst_pr = detect_column(purchase.columns, ["igst"])
    cgst_pr = detect_column(purchase.columns, ["cgst"])
    sgst_pr = detect_column(purchase.columns, ["sgst"])

    required = [gstin_2b, invoice_2b, gstin_pr, invoice_pr]

    if any(x is None for x in required):
        st.error("Required columns not detected automatically.")
        st.write("2B Columns:", list(gstr2b.columns))
        st.write("Purchase Columns:", list(purchase.columns))
        st.stop()

    # Create clean working dataframe
    df_2b = pd.DataFrame({
        "GSTIN": gstr2b[gstin_2b],
        "Party": gstr2b[party_2b] if party_2b else "",
        "Invoice": gstr2b[invoice_2b],
        "Date": gstr2b[date_2b] if date_2b else "",
        "Taxable_2B": pd.to_numeric(gstr2b[taxable_2b], errors="coerce").fillna(0) if taxable_2b else 0,
        "IGST_2B": pd.to_numeric(gstr2b[igst_2b], errors="coerce").fillna(0) if igst_2b else 0,
        "CGST_2B": pd.to_numeric(gstr2b[cgst_2b], errors="coerce").fillna(0) if cgst_2b else 0,
        "SGST_2B": pd.to_numeric(gstr2b[sgst_2b], errors="coerce").fillna(0) if sgst_2b else 0
    })

    df_pr = pd.DataFrame({
        "GSTIN": purchase[gstin_pr],
        "Party": purchase[party_pr] if party_pr else "",
        "Invoice": purchase[invoice_pr],
        "Date": purchase[date_pr] if date_pr else "",
        "Taxable_PR": pd.to_numeric(purchase[taxable_pr], errors="coerce").fillna(0) if taxable_pr else 0,
        "IGST_PR": pd.to_numeric(purchase[igst_pr], errors="coerce").fillna(0) if igst_pr else 0,
        "CGST_PR": pd.to_numeric(purchase[cgst_pr], errors="coerce").fillna(0) if cgst_pr else 0,
        "SGST_PR": pd.to_numeric(purchase[sgst_pr], errors="coerce").fillna(0) if sgst_pr else 0
    })

    # Clean key fields
    df_2b["Invoice"] = df_2b["Invoice"].astype(str).str.strip().str.upper()
    df_pr["Invoice"] = df_pr["Invoice"].astype(str).str.strip().str.upper()
    df_2b["GSTIN"] = df_2b["GSTIN"].astype(str).str.strip()
    df_pr["GSTIN"] = df_pr["GSTIN"].astype(str).str.strip()

    # Merge
    recon = pd.merge(df_pr, df_2b, on=["GSTIN", "Invoice"], how="outer", indicator=True)

    # Differences
    recon["Taxable_Diff"] = recon["Taxable_PR"] - recon["Taxable_2B"]
    recon["IGST_Diff"] = recon["IGST_PR"] - recon["IGST_2B"]
    recon["CGST_Diff"] = recon["CGST_PR"] - recon["CGST_2B"]
    recon["SGST_Diff"] = recon["SGST_PR"] - recon["SGST_2B"]

    # Status
    def classify(row):
        if row["_merge"] == "both":
            if row["Taxable_Diff"] != 0 or row["IGST_Diff"] != 0 or \
               row["CGST_Diff"] != 0 or row["SGST_Diff"] != 0:
                return "Tax Mismatch"
            return "Matched"
        elif row["_merge"] == "left_only":
            return "Missing in 2B"
        else:
            return "Missing in Purchase"

    recon["Status"] = recon.apply(classify, axis=1)

    # Summary
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
