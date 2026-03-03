import streamlit as st
import pandas as pd

st.set_page_config(page_title="Enterprise GST Reconciliation", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])


# -------------------------------------------------
# AUTO DETECT B2B HEADER ROW INSIDE SHEET
# -------------------------------------------------

def load_gstr2b_correct(file):
    raw = pd.read_excel(file, header=None)

    header_row = None

    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).str.lower()

        if row.str.contains("gstin of supplier").any() or \
           (row.str.contains("gstin").any() and row.str.contains("invoice").any()):
            header_row = i
            break

    if header_row is None:
        st.error("Could not find B2B header row automatically.")
        st.stop()

    df = pd.read_excel(file, header=header_row)
    df.columns = df.columns.astype(str).str.strip()
    return df


def load_purchase_correct(file):
    raw = pd.read_excel(file, header=None)

    header_row = None

    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).str.lower()

        if row.str.contains("gstin").any() and row.str.contains("invoice").any():
            header_row = i
            break

    if header_row is None:
        st.error("Could not find Purchase header row automatically.")
        st.stop()

    df = pd.read_excel(file, header=header_row)
    df.columns = df.columns.astype(str).str.strip()
    return df


# -------------------------------------------------
# FIND COLUMN BY KEYWORD
# -------------------------------------------------

def find_column(columns, keywords):
    for col in columns:
        clean = col.lower().replace(" ", "").replace("₹", "").replace(".", "")
        for key in keywords:
            if key in clean:
                return col
    return None


# -------------------------------------------------
# MAIN PROCESS
# -------------------------------------------------

if gstr2b_file and purchase_file:

    gstr2b = load_gstr2b_correct(gstr2b_file)
    purchase = load_purchase_correct(purchase_file)

    # Detect required fields automatically

    gstin_2b = find_column(gstr2b.columns, ["gstin"])
    invoice_2b = find_column(gstr2b.columns, ["invoice"])
    date_2b = find_column(gstr2b.columns, ["date"])
    taxable_2b = find_column(gstr2b.columns, ["taxable"])
    igst_2b = find_column(gstr2b.columns, ["integrated", "igst"])
    cgst_2b = find_column(gstr2b.columns, ["central", "cgst"])
    sgst_2b = find_column(gstr2b.columns, ["state", "sgst"])

    gstin_pr = find_column(purchase.columns, ["gstin"])
    invoice_pr = find_column(purchase.columns, ["supplierinvoiceno", "invoice"])
    date_pr = find_column(purchase.columns, ["date"])
    taxable_pr = find_column(purchase.columns, ["taxable"])
    igst_pr = find_column(purchase.columns, ["igst"])
    cgst_pr = find_column(purchase.columns, ["cgst"])
    sgst_pr = find_column(purchase.columns, ["sgst"])

    if not gstin_2b or not invoice_2b or not gstin_pr or not invoice_pr:
        st.error("Required reconciliation columns not detected.")
        st.write("2B Columns:", gstr2b.columns)
        st.write("Purchase Columns:", purchase.columns)
        st.stop()

    # Create clean working dataframes

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

    # Output
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
