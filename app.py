# -------------------------
# SMART COLUMN DETECTION
# -------------------------

def find_column(columns, possible_names):
    for col in columns:
        if col.strip().lower() in possible_names:
            return col
    return None

gstr2b_columns = [c.strip().lower() for c in gstr2b.columns]
purchase_columns = [c.strip().lower() for c in purchase.columns]

invoice_col_2b = find_column(gstr2b.columns, ["invoice no", "invoice number", "inv no", "document no"])
invoice_col_pr = find_column(purchase.columns, ["bill no", "invoice no", "invoice number"])

gstin_col_2b = find_column(gstr2b.columns, ["gstin"])
gstin_col_pr = find_column(purchase.columns, ["supplier gstin", "gstin"])

if not invoice_col_2b or not invoice_col_pr or not gstin_col_2b or not gstin_col_pr:
    st.error("Required columns not found. Please check column names.")
    st.stop()

# Clean data
gstr2b[invoice_col_2b] = gstr2b[invoice_col_2b].astype(str).str.strip().str.upper()
purchase[invoice_col_pr] = purchase[invoice_col_pr].astype(str).str.strip().str.upper()

gstr2b[gstin_col_2b] = gstr2b[gstin_col_2b].astype(str).str.strip()
purchase[gstin_col_pr] = purchase[gstin_col_pr].astype(str).str.strip()

# Merge
recon = pd.merge(
    purchase,
    gstr2b,
    left_on=[gstin_col_pr, invoice_col_pr],
    right_on=[gstin_col_2b, invoice_col_2b],
    how="outer",
    indicator=True
)
