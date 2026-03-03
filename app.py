import streamlit as st
import pandas as pd

st.set_page_config(page_title="Enterprise GST Reconciliation", layout="wide")
st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx","xls"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx","xls"])


# -------------------------
# AUTO LOAD B2B SHEET
# -------------------------
def load_2b_b2b_sheet(file):
    xls = pd.ExcelFile(file)
    for sheet in xls.sheet_names:
        if "b2b" in sheet.lower():
            return pd.read_excel(file, sheet_name=sheet)
    return pd.read_excel(file, sheet_name=xls.sheet_names[0])


# -------------------------
# AUTO HEADER DETECTION
# -------------------------
def detect_header(df):
    for i in range(10):
        row = df.iloc[i].astype(str).str.lower()
        if row.str.contains("gstin").any() and row.str.contains("invoice").any():
            return i
    return 0


if gstr2b_file and purchase_file:

    # ---------- LOAD 2B ----------
    raw_2b = load_2b_b2b_sheet(gstr2b_file)
    header_row_2b = detect_header(raw_2b)
    gstr2b = pd.read_excel(gstr2b_file, header=header_row_2b)

    # ---------- LOAD PURCHASE ----------
    raw_pr = pd.read_excel(purchase_file, header=None)
    header_row_pr = detect_header(raw_pr)
    purchase = pd.read_excel(purchase_file, header=header_row_pr)

    gstr2b.columns = gstr2b.columns.astype(str).str.strip()
    purchase.columns = purchase.columns.astype(str).str.strip()

    # -------------------------
    # COLUMN MAPPING
    # -------------------------

    def find_col(columns, keywords):
        for col in columns:
            clean = col.lower().replace(" ", "").replace(".", "")
            for key in keywords:
                if key in clean:
                    return col
        return None

    # 2B Columns
    gstin_2b = find_col(gstr2b.columns, ["gstin"])
    invoice_2b = find_col(gstr2b.columns, ["invoicenumber"])
    taxable_2b = find_col(gstr2b.columns, ["taxablevalue"])
    igst_2b = find_col(gstr2b.columns, ["integratedtax","igst"])
    cgst_2b = find_col(gstr2b.columns, ["centraltax","cgst"])
    sgst_2b = find_col(gstr2b.columns, ["statetax","sgst"])

    # Purchase Columns
    gstin_pr = find_col(purchase.columns, ["gstinuin","gstin"])
    invoice_pr = find_col(purchase.columns, ["supplierinvoiceno"])
    taxable_pr = find_col(purchase.columns, ["taxableamount","taxablevalue"])
    igst_pr = find_col(purchase.columns, ["igst"])
    cgst_pr = find_col(purchase.columns, ["cgst"])
    sgst_pr = find_col(purchase.columns, ["sgst"])

    required = [gstin_2b, invoice_2b, gstin_pr, invoice_pr]

    if any(x is None for x in required):
        st.error("Required columns not detected.")
        st.write("2B Columns:", list(gstr2b.columns))
        st.write("Purchase Columns:", list(purchase.columns))
        st.stop()

    # -------------------------
    # CLEAN DATA
    # -------------------------

    gstr2b[invoice_2b] = gstr2b[invoice_2b].astype(str).str.strip().str.upper()
    purchase[invoice_pr] = purchase[invoice_pr].astype(str).str.strip().str.upper()

    gstr2b[gstin_2b] = gstr2b[gstin_2b].astype(str).str.strip()
    purchase[gstin_pr] = purchase[gstin_pr].astype(str).str.strip()

    for col in [taxable_2b, igst_2b, cgst_2b, sgst_2b]:
        if col:
            gstr2b[col] = pd.to_numeric(gstr2b[col], errors="coerce").fillna(0)

    for col in [taxable_pr, igst_pr, cgst_pr, sgst_pr]:
        if col:
            purchase[col] = pd.to_numeric(purchase[col], errors="coerce").fillna(0)

    # -------------------------
    # MERGE
    # -------------------------

    recon = pd.merge(
        purchase,
        gstr2b,
        left_on=[gstin_pr, invoice_pr],
        right_on=[gstin_2b, invoice_2b],
        how="outer",
        indicator=True,
        suffixes=("_PR","_2B")
    )

    # -------------------------
    # DIFFERENCE CALCULATION
    # -------------------------

    def calc_diff(pr, b2b):
        if pr and b2b:
            return recon[pr+"_PR"] - recon[b2b+"_2B"]
        return 0

    if taxable_pr and taxable_2b:
        recon["Taxable_Diff"] = calc_diff(taxable_pr, taxable_2b)

    if igst_pr and igst_2b:
        recon["IGST_Diff"] = calc_diff(igst_pr, igst_2b)

    if cgst_pr and cgst_2b:
        recon["CGST_Diff"] = calc_diff(cgst_pr, cgst_2b)

    if sgst_pr and sgst_2b:
        recon["SGST_Diff"] = calc_diff(sgst_pr, sgst_2b)

    # -------------------------
    # STATUS + REASON
    # -------------------------

    def classify(row):
        if row["_merge"] == "left_only":
            return "Missing in 2B"
        if row["_merge"] == "right_only":
            return "Missing in Purchase"

        diffs = []
        for col in ["Taxable_Diff","IGST_Diff","CGST_Diff","SGST_Diff"]:
            if col in row and row[col] != 0:
                diffs.append(col.replace("_Diff",""))

        if diffs:
            return "Mismatch: " + ", ".join(diffs)

        return "Matched"

    recon["Status"] = recon.apply(classify, axis=1)

    # -------------------------
    # SUMMARY
    # -------------------------

    st.subheader("Summary")

    col1,col2,col3 = st.columns(3)
    col1.metric("Matched", (recon["Status"]=="Matched").sum())
    col2.metric("Missing in 2B", recon["Status"].str.contains("Missing").sum())
    col3.metric("Tax Mismatch", recon["Status"].str.contains("Mismatch").sum())

    st.subheader("Detailed Reconciliation")

    def highlight(row):
        if "Mismatch" in row:
            return "background-color:#ffcccc"
        if "Missing in 2B" in row:
            return "background-color:#fff3cd"
        if "Missing in Purchase" in row:
            return "background-color:#cce5ff"
        return ""

    st.dataframe(
        recon.style.applymap(highlight, subset=["Status"]),
        use_container_width=True
    )

    st.download_button(
        "Download Enterprise Reconciliation Report",
        data=recon.to_csv(index=False),
        file_name="Enterprise_GST_Reconciliation_Report.csv",
        mime="text/csv"
    )
