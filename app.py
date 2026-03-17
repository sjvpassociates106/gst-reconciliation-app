import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="GST Reconciliation", layout="wide")
st.title("GST 2B vs Purchase Register Reconciliation")

gstr_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register", type=["xls", "xlsx"])


# ---------------- HELPERS ---------------- #

def clean_text(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    x = re.sub(r"\s+", " ", x)
    return x


def clean_invoice(inv):
    if pd.isna(inv):
        return ""
    inv = str(inv).upper().strip()
    inv = inv.replace(" ", "")
    inv = re.sub(r"[/\\\-_.]", "", inv)
    inv = re.sub(r"[^A-Z0-9]", "", inv)
    return inv


def clean_gstin(x):
    if pd.isna(x):
        return ""
    x = str(x).upper().strip()
    x = re.sub(r"[^A-Z0-9]", "", x)
    if len(x) == 15:
        return x
    return x


def num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def normalize_colname(col):
    c = str(col).lower().strip()
    c = c.replace("₹", "")
    c = c.replace("rs.", "rs")
    c = c.replace("(", " ").replace(")", " ")
    c = c.replace("_", " ").replace("-", " ")
    c = re.sub(r"\s+", " ", c)
    return c.strip()


def detect_header_row_excel(file, sheet_name=0, max_rows=20):
    temp = pd.read_excel(file, sheet_name=sheet_name, header=None)

    best_row = 0
    best_score = -1

    check_words = [
        "gstin", "invoice", "taxable", "integrated", "central", "state",
        "party", "trade", "legal", "supplier", "igst", "cgst", "sgst"
    ]

    max_scan = min(max_rows, len(temp))

    for i in range(max_scan):
        vals = temp.iloc[i].astype(str).tolist()
        row_text = " | ".join(vals).lower()
        score = sum(1 for w in check_words if w in row_text)

        if score > best_score:
            best_score = score
            best_row = i

    return best_row


def detect_column(df, kind):
    cols = list(df.columns)
    normalized = {col: normalize_colname(col) for col in cols}

    patterns = {
        "gstin": [
            "gstin of supplier", "supplier gstin", "gstin", "gst no", "gstin no", "uin"
        ],
        "party": [
            "trade legal name", "trade/legal name", "legal name", "trade name",
            "name of supplier", "supplier name", "party name", "party", "particulars", "vendor"
        ],
        "invoice": [
            "invoice number", "invoice no", "invoice no.", "inv no", "inv number",
            "bill no", "document number", "doc no", "voucher no", "invoice"
        ],
        "taxable": [
            "taxable value", "taxable amount", "taxable", "taxable val"
        ],
        "igst": [
            "integrated tax", "igst amount", "igst"
        ],
        "cgst": [
            "central tax", "cgst amount", "cgst"
        ],
        "sgst": [
            "state/ut tax", "state tax", "sgst amount", "sgst", "state ut tax", "utgst"
        ]
    }

    # exact / strong match
    for col, norm in normalized.items():
        for p in patterns[kind]:
            if p == norm or p in norm:
                return col

    # fallback by tokens
    for col, norm in normalized.items():
        if kind == "gstin" and ("gstin" in norm or "uin" in norm):
            return col
        if kind == "party" and any(x in norm for x in ["party", "supplier", "legal", "trade", "vendor", "particular"]):
            return col
        if kind == "invoice" and any(x in norm for x in ["invoice", "inv", "bill", "doc", "voucher"]):
            return col
        if kind == "taxable" and "taxable" in norm:
            return col
        if kind == "igst" and ("integrated" in norm or "igst" in norm):
            return col
        if kind == "cgst" and ("central" in norm or "cgst" in norm):
            return col
        if kind == "sgst" and ("state" in norm or "sgst" in norm or "utgst" in norm):
            return col

    return None


def detect_invoice_by_data(df):
    best_col = None
    best_score = -1

    for col in df.columns:
        s = df[col].astype(str).fillna("").head(50)
        s = s[s.str.strip() != ""]
        if len(s) == 0:
            continue

        score = 0
        score += s.str.contains(r"\d", regex=True).sum()
        score += s.str.contains(r"[A-Za-z]", regex=True).sum()
        score += s.str.len().between(3, 25).sum()

        if score > best_score:
            best_score = score
            best_col = col

    return best_col


def prepare_2b(gstr_file):
    header_row = detect_header_row_excel(gstr_file, sheet_name="B2B", max_rows=20)
    df = pd.read_excel(gstr_file, sheet_name="B2B", header=header_row)
    df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed", case=False, na=False)]

    gstin_col = detect_column(df, "gstin")
    party_col = detect_column(df, "party")
    invoice_col = detect_column(df, "invoice")
    taxable_col = detect_column(df, "taxable")
    igst_col = detect_column(df, "igst")
    cgst_col = detect_column(df, "cgst")
    sgst_col = detect_column(df, "sgst")

    if invoice_col is None:
        invoice_col = detect_invoice_by_data(df)

    out = pd.DataFrame()

    out["GSTIN"] = df[gstin_col].apply(clean_gstin) if gstin_col else ""
    out["Party2B"] = df[party_col].apply(clean_text) if party_col else ""
    out["Invoice"] = df[invoice_col].apply(clean_invoice) if invoice_col else ""

    out["Taxable2B"] = num(df[taxable_col]) if taxable_col else 0
    out["IGST2B"] = num(df[igst_col]) if igst_col else 0
    out["CGST2B"] = num(df[cgst_col]) if cgst_col else 0
    out["SGST2B"] = num(df[sgst_col]) if sgst_col else 0

    out = out[out["Invoice"] != ""].copy()

    group_cols = ["GSTIN", "Invoice"]
    out = out.groupby(group_cols, as_index=False).agg({
        "Party2B": "first",
        "Taxable2B": "sum",
        "IGST2B": "sum",
        "CGST2B": "sum",
        "SGST2B": "sum"
    })

    return out, {
        "gstin_col": gstin_col,
        "party_col": party_col,
        "invoice_col": invoice_col,
        "taxable_col": taxable_col,
        "igst_col": igst_col,
        "cgst_col": cgst_col,
        "sgst_col": sgst_col,
        "header_row": header_row,
        "columns": list(df.columns)
    }


def prepare_purchase(purchase_file):
    header_row = detect_header_row_excel(purchase_file, sheet_name=0, max_rows=20)
    df = pd.read_excel(purchase_file, header=header_row)
    df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed", case=False, na=False)]

    gstin_col = detect_column(df, "gstin")
    party_col = detect_column(df, "party")
    invoice_col = detect_column(df, "invoice")
    taxable_col = detect_column(df, "taxable")
    igst_col = detect_column(df, "igst")
    cgst_col = detect_column(df, "cgst")
    sgst_col = detect_column(df, "sgst")

    if invoice_col is None:
        invoice_col = detect_invoice_by_data(df)

    out = pd.DataFrame()

    out["GSTIN"] = df[gstin_col].apply(clean_gstin) if gstin_col else ""
    out["PartyPR"] = df[party_col].apply(clean_text) if party_col else ""
    out["Invoice"] = df[invoice_col].apply(clean_invoice) if invoice_col else ""

    out["TaxablePR"] = num(df[taxable_col]) if taxable_col else 0
    out["IGSTPR"] = num(df[igst_col]) if igst_col else 0
    out["CGSTPR"] = num(df[cgst_col]) if cgst_col else 0
    out["SGSTPR"] = num(df[sgst_col]) if sgst_col else 0

    out = out[out["Invoice"] != ""].copy()

    group_cols = ["GSTIN", "Invoice"]
    out = out.groupby(group_cols, as_index=False).agg({
        "PartyPR": "first",
        "TaxablePR": "sum",
        "IGSTPR": "sum",
        "CGSTPR": "sum",
        "SGSTPR": "sum"
    })

    return out, {
        "gstin_col": gstin_col,
        "party_col": party_col,
        "invoice_col": invoice_col,
        "taxable_col": taxable_col,
        "igst_col": igst_col,
        "cgst_col": cgst_col,
        "sgst_col": sgst_col,
        "header_row": header_row,
        "columns": list(df.columns)
    }


def reconcile_data(dfpr, df2b):
    # primary match by GSTIN + Invoice
    recon = pd.merge(
        dfpr,
        df2b,
        on=["GSTIN", "Invoice"],
        how="outer",
        indicator=True
    )

    # fill blanks for display
    text_cols = ["GSTIN", "Invoice", "PartyPR", "Party2B"]
    for c in text_cols:
        if c in recon.columns:
            recon[c] = recon[c].fillna("")

    num_cols = [
        "TaxablePR", "IGSTPR", "CGSTPR", "SGSTPR",
        "Taxable2B", "IGST2B", "CGST2B", "SGST2B"
    ]
    for c in num_cols:
        if c in recon.columns:
            recon[c] = pd.to_numeric(recon[c], errors="coerce").fillna(0)

    def check(r):
        if r["_merge"] == "left_only":
            return pd.Series(["Mismatch", "Missing in 2B"])
        if r["_merge"] == "right_only":
            return pd.Series(["Mismatch", "Missing in Purchase"])

        tol = 1
        reasons = []

        if abs(r["TaxablePR"] - r["Taxable2B"]) > tol:
            reasons.append("Taxable mismatch")
        if abs(r["CGSTPR"] - r["CGST2B"]) > tol:
            reasons.append("CGST mismatch")
        if abs(r["SGSTPR"] - r["SGST2B"]) > tol:
            reasons.append("SGST mismatch")
        if abs(r["IGSTPR"] - r["IGST2B"]) > tol:
            reasons.append("IGST mismatch")

        if reasons:
            return pd.Series(["Mismatch", ", ".join(reasons)])
        return pd.Series(["Matched", ""])

    recon[["Status", "Reason"]] = recon.apply(check, axis=1)
    recon.drop(columns=["_merge"], inplace=True)

    # final display format
    final_cols = [
        "GSTIN", "PartyPR", "Party2B", "Invoice",
        "TaxablePR", "CGSTPR", "SGSTPR", "IGSTPR",
        "Taxable2B", "CGST2B", "SGST2B", "IGST2B",
        "Status", "Reason"
    ]

    for c in final_cols:
        if c not in recon.columns:
            recon[c] = ""

    recon = recon[final_cols].copy()

    recon.rename(columns={
        "PartyPR": "PartyNamePR",
        "Party2B": "PartyName2B"
    }, inplace=True)

    return recon


# ---------------- MAIN ---------------- #

if gstr_file and purchase_file:
    try:
        df2b, info2b = prepare_2b(gstr_file)
        dfpr, infopr = prepare_purchase(purchase_file)

        recon = reconcile_data(dfpr, df2b)

        st.subheader("Reconciliation Result")
        st.dataframe(recon, use_container_width=True)

        st.subheader("Detected Columns")
        col1, col2 = st.columns(2)

        with col1:
            st.write("**GSTR-2B Detection**")
            st.write({
                "Header Row": info2b["header_row"],
                "GSTIN": str(info2b["gstin_col"]),
                "Party": str(info2b["party_col"]),
                "Invoice": str(info2b["invoice_col"]),
                "Taxable": str(info2b["taxable_col"]),
                "IGST": str(info2b["igst_col"]),
                "CGST": str(info2b["cgst_col"]),
                "SGST": str(info2b["sgst_col"]),
            })

        with col2:
            st.write("**Purchase Register Detection**")
            st.write({
                "Header Row": infopr["header_row"],
                "GSTIN": str(infopr["gstin_col"]),
                "Party": str(infopr["party_col"]),
                "Invoice": str(infopr["invoice_col"]),
                "Taxable": str(infopr["taxable_col"]),
                "IGST": str(infopr["igst_col"]),
                "CGST": str(infopr["cgst_col"]),
                "SGST": str(infopr["sgst_col"]),
            })

        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            recon.to_excel(writer, sheet_name="Reconciliation", index=False)
            dfpr.to_excel(writer, sheet_name="Purchase_Cleaned", index=False)
            df2b.to_excel(writer, sheet_name="GSTR2B_Cleaned", index=False)

        st.download_button(
            label="Download Excel Report",
            data=buffer.getvalue(),
            file_name="GST_Reconciliation_Output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"Error: {str(e)}")
