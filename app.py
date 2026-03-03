import streamlit as st
import pandas as pd

st.set_page_config(page_title="Enterprise GST Reconciliation", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])


# -------------------------------------------------
# STEP 1: AUTO FIND CORRECT HEADER ROW
# -------------------------------------------------

def read_with_correct_header(file):
    raw = pd.read_excel(file, header=None)

    header_row = None

    for i in range(min(20, len(raw))):
        row_text = raw.iloc[i].astype(str).str.lower()

        if row_text.str.contains("gstin").any() and \
           row_text.str.contains("invoice").any():
            header_row = i
            break

    if header_row is None:
        st.error("Header row not detected automatically.")
        st.write(raw.head(15))
        st.stop()

    return pd.read_excel(file, header=header_row)


# -------------------------------------------------
# STEP 2: DETECT REQUIRED COLUMNS ONLY
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

    gstr2b = read_with_correct_header(gstr2b_file)
    purchase = read_with_correct_header(purchase_file)

    gstr2b.columns = gstr2b.columns.astype(str).str.strip()
    purchase.columns = purchase.columns.astype(str).str.strip()

    # ---- Detect only required fields ----

    gstin_2b = find_column(gstr2b.columns, ["gstin"])
    invoice_2b = find_column(gstr2b.columns, ["invoice"])
    date_2b = find_column(gstr2b.columns, ["date"])
    taxable_2b = find_column(gstr2b.columns, ["taxable"])
    igst_2b = find_column(gstr2b.columns, ["integrated", "igst"])
    cgst_2b = find_column(gstr2b.columns, ["central", "cgst"])
    sgst_2b = find_column(gstr2b.columns, ["state", "sgst"])

    gstin_pr = find_column(purchase.columns, ["gstin"])
    invoice_pr = find_column(purchase.columns, ["supplierinvoiceno", "invoiceno", "invoice"])
    date_pr = find_column(purchase.columns, ["date"])
    taxable_pr = find_column(purchase.columns, ["taxable"])
    igst_pr = find_column(purchase.columns, ["igst"])
    cgst_pr = find_column(purchase.columns, ["cgst"])
    sgst_pr = find_column(purchase.columns, ["sgst"])

    required = [gstin_2b, invoice_2b, gstin_pr, invoice_pr]

    if any(x is None for x in required):
        st.error("Required columns not detected automatically.")
        st.write("2B Columns:", list(gstr2b.columns))
        st.write("Purchase Columns:", list(purchase.columns))
        st.stop()

    # -------------------------------------------------
    # CREATE CLEAN WORKING DATA (IGNORE OTHER COLUMNS)
    # -------------------------------------------------

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

    # Clean matching fields
    df_2b["Invoice"] = df_2b["Invoice"].astype(str).str.strip().str.upper()
    df_pr["Invoice"] = df_pr["Invoice"].astype(str).str.strip().str.upper()
    df_2b["GSTIN"] = df_2b["GSTIN"].astype(str).str.strip()
    df_pr["GSTIN"] = df_pr["GSTIN"].astype(str).str.strip()

    # -------------------------------------------------
    # MERGE
    # -------------------------------------------------

    recon = pd.merge(df_pr, df_2b, on=["GSTIN", "Invoice"], how="outer", indicator=True)

    # -------------------------------------------------
    # DIFFERENCE CALCULATION
    # -------------------------------------------------

    recon["Taxable_Diff"] = recon["Taxable_PR"] - recon["Taxable_2B"]
    recon["IGST_Diff"] = recon["IGST_PR"] - recon["IGST_2B"]
    recon["CGST_Diff"] = recon["CGST_PR"] - recon["CGST_2B"]
    recon["SGST_Diff"] = recon["SGST_PR"] - recon["SGST_2B"]

    # -------------------------------------------------
    # STATUS LOGIC
    # -------------------------------------------------

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

    # -------------------------------------------------
    # OUTPUT
    # -------------------------------------------------

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
