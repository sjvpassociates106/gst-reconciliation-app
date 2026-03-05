import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="GST Reconciliation", layout="wide")
st.title("GST 2B vs Purchase Register Reconciliation")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx","xls"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx","xls"])


# ---------- CLEAN COLUMN ----------
def clean(text):
    text=str(text).lower()
    text=text.replace("₹","")
    text=re.sub(r'[^a-z0-9]','',text)
    return text


# ---------- FIND COLUMN ----------
def find_col(columns,keywords):

    for col in columns:
        c=clean(col)

        for k in keywords:
            if k in c:
                return col

    return None


# ---------- SAFE COLUMN ----------
def safe_numeric(df,col):
    if col and col in df.columns:
        return pd.to_numeric(df[col],errors="coerce").fillna(0)
    return 0


# ---------- LOAD GSTR2B ----------
def load_gstr2b(file):

    excel=pd.ExcelFile(file)

    if "B2B" not in excel.sheet_names:
        st.error("B2B sheet not found in GSTR-2B")
        st.stop()

    raw=excel.parse("B2B",header=None)

    header=None

    for i in range(len(raw)):
        if raw.iloc[i].astype(str).str.contains("gstin",case=False).any():
            header=i
            break

    if header is None:
        header=0

    df=excel.parse("B2B",header=header)
    df.columns=df.columns.str.strip()

    return df


# ---------- LOAD PURCHASE ----------
def load_purchase(file):

    raw=pd.read_excel(file,header=None)

    header=None

    for i in range(len(raw)):
        row=raw.iloc[i].astype(str).str.lower()

        if any("gstin" in x for x in row) or any("invoice" in x for x in row):
            header=i
            break

    if header is None:
        header=0

    df=pd.read_excel(file,header=header)
    df.columns=df.columns.str.strip()

    return df


# ---------- MAIN ----------
if gstr2b_file and purchase_file:

    gstr2b=load_gstr2b(gstr2b_file)
    purchase=load_purchase(purchase_file)

    # Detect columns
    gstin2b=find_col(gstr2b.columns,["gstin"])
    inv2b=find_col(gstr2b.columns,["invoice"])
    tax2b=find_col(gstr2b.columns,["taxable"])
    igst2b=find_col(gstr2b.columns,["integrated","igst"])
    cgst2b=find_col(gstr2b.columns,["central","cgst"])
    sgst2b=find_col(gstr2b.columns,["state","sgst"])

    gstinpr=find_col(purchase.columns,["gstin"])
    invpr=find_col(purchase.columns,["supplierinvoice","invoice"])
    taxpr=find_col(purchase.columns,["taxable","value"])
    igstpr=find_col(purchase.columns,["igst"])
    cgstpr=find_col(purchase.columns,["cgst"])
    sgstpr=find_col(purchase.columns,["sgst"])


    # ---------- STANDARD TABLES ----------
    df2b=pd.DataFrame({

        "GSTIN":gstr2b[gstin2b].astype(str).str.strip().str.upper(),
        "Invoice":gstr2b[inv2b].astype(str).str.strip().str.upper(),
        "Taxable2B":safe_numeric(gstr2b,tax2b),
        "IGST2B":safe_numeric(gstr2b,igst2b),
        "CGST2B":safe_numeric(gstr2b,cgst2b),
        "SGST2B":safe_numeric(gstr2b,sgst2b)

    })


    dfpr=pd.DataFrame({

        "GSTIN":purchase[gstinpr].astype(str).str.strip().str.upper(),
        "Invoice":purchase[invpr].astype(str).str.strip().str.upper(),
        "TaxablePR":safe_numeric(purchase,taxpr),
        "IGSTPR":safe_numeric(purchase,igstpr),
        "CGSTPR":safe_numeric(purchase,cgstpr),
        "SGSTPR":safe_numeric(purchase,sgstpr)

    })


    # ---------- MERGE ----------
    recon=pd.merge(dfpr,df2b,on=["GSTIN","Invoice"],how="outer",indicator=True)


    # ---------- STATUS ----------
    def status(row):

        if row["_merge"]=="left_only":
            return pd.Series(["Mismatch","Missing in 2B"])

        if row["_merge"]=="right_only":
            return pd.Series(["Mismatch","Missing in Purchase"])

        reasons=[]

        if round(row["TaxablePR"],2)!=round(row["Taxable2B"],2):
            reasons.append("Taxable mismatch")

        if round(row["IGSTPR"],2)!=round(row["IGST2B"],2):
            reasons.append("IGST mismatch")

        if round(row["CGSTPR"],2)!=round(row["CGST2B"],2):
            reasons.append("CGST mismatch")

        if round(row["SGSTPR"],2)!=round(row["SGST2B"],2):
            reasons.append("SGST mismatch")

        if len(reasons)==0:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]]=recon.apply(status,axis=1)

    recon=recon.drop(columns=["_merge"])


    # ---------- DISPLAY ----------
    st.subheader("Summary")
    st.write(recon["Status"].value_counts())

    st.subheader("Reconciliation Result")
    st.dataframe(recon,use_container_width=True)


    # ---------- EXPORT ----------
    file="GST_Reconciliation_Output.xlsx"
    recon.to_excel(file,index=False)

    with open(file,"rb") as f:

        st.download_button(
            "Download Excel",
            data=f,
            file_name=file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
