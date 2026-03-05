import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="GST Reconciliation", layout="wide")
st.title("GST 2B vs Purchase Register Reconciliation")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx","xls"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx","xls"])


# ----------------------------
# CLEAN COLUMN FUNCTION
# ----------------------------

def clean(text):
    text=str(text).lower()
    text=text.replace("₹","")
    text=re.sub(r'[^a-z0-9]','',text)
    return text


# ----------------------------
# FIND COLUMN BY KEYWORDS
# ----------------------------

def find_col(columns,keys):

    for col in columns:
        c=clean(col)

        for k in keys:
            if k in c:
                return col

    return None


# ----------------------------
# LOAD GSTR2B B2B SHEET
# ----------------------------

def load_gstr2b(file):

    excel=pd.ExcelFile(file)

    if "B2B" not in excel.sheet_names:
        st.error("B2B sheet not found in GSTR-2B")
        st.stop()

    raw=excel.parse("B2B",header=None)

    header_row=None

    for i in range(len(raw)):
        if raw.iloc[i].astype(str).str.contains("gstin",case=False).any():
            header_row=i
            break

    if header_row is None:
        st.error("Could not detect header row in B2B sheet")
        st.stop()

    df=excel.parse("B2B",header=header_row)
    df.columns=df.columns.str.strip()

    return df


# ----------------------------
# LOAD PURCHASE REGISTER
# ----------------------------

def load_purchase(file):

    raw=pd.read_excel(file,header=None)

    header_row=None

    for i in range(len(raw)):
        row=raw.iloc[i].astype(str).str.lower()

        if any("gstin" in x for x in row) and any("invoice" in x for x in row):
            header_row=i
            break

    if header_row is None:
        st.error("Purchase Register header not detected")
        st.stop()

    df=pd.read_excel(file,header=header_row)
    df.columns=df.columns.str.strip()

    return df


# ----------------------------
# MAIN PROCESS
# ----------------------------

if gstr2b_file and purchase_file:

    gstr2b=load_gstr2b(gstr2b_file)
    purchase=load_purchase(purchase_file)

    # Detect Columns

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


    # Build Standard Tables

    df2b=pd.DataFrame({

        "GSTIN":gstr2b[gstin2b].astype(str).str.strip().str.upper(),
        "Invoice":gstr2b[inv2b].astype(str).str.strip().str.upper(),
        "Taxable2B":pd.to_numeric(gstr2b[tax2b],errors="coerce").fillna(0),
        "IGST2B":pd.to_numeric(gstr2b[igst2b],errors="coerce").fillna(0),
        "CGST2B":pd.to_numeric(gstr2b[cgst2b],errors="coerce").fillna(0),
        "SGST2B":pd.to_numeric(gstr2b[sgst2b],errors="coerce").fillna(0)

    })


    dfpr=pd.DataFrame({

        "GSTIN":purchase[gstinpr].astype(str).str.strip().str.upper(),
        "Invoice":purchase[invpr].astype(str).str.strip().str.upper(),
        "TaxablePR":pd.to_numeric(purchase[taxpr],errors="coerce").fillna(0),
        "IGSTPR":pd.to_numeric(purchase[igstpr],errors="coerce").fillna(0),
        "CGSTPR":pd.to_numeric(purchase[cgstpr],errors="coerce").fillna(0),
        "SGSTPR":pd.to_numeric(purchase[sgstpr],errors="coerce").fillna(0)

    })


    # Merge

    recon=pd.merge(dfpr,df2b,on=["GSTIN","Invoice"],how="outer",indicator=True)


    # Status + Reason

    def status(row):

        if row["_merge"]=="left_only":
            return pd.Series(["Mismatch","Missing in 2B"])

        if row["_merge"]=="right_only":
            return pd.Series(["Mismatch","Missing in Purchase Register"])

        reasons=[]

        if round(row["TaxablePR"],2)!=round(row["Taxable2B"],2):
            reasons.append("Taxable Value Mismatch")

        if round(row["IGSTPR"],2)!=round(row["IGST2B"],2):
            reasons.append("IGST Mismatch")

        if round(row["CGSTPR"],2)!=round(row["CGST2B"],2):
            reasons.append("CGST Mismatch")

        if round(row["SGSTPR"],2)!=round(row["SGST2B"],2):
            reasons.append("SGST Mismatch")

        if len(reasons)==0:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])


    recon[["Status","Reason"]]=recon.apply(status,axis=1)

    recon=recon.drop(columns=["_merge"])


    # Display

    st.subheader("Summary")

    st.write(recon["Status"].value_counts())

    st.subheader("Reconciliation Result")

    st.dataframe(recon,use_container_width=True)


    # Export Excel

    file="GST_Reconciliation_Output.xlsx"

    recon.to_excel(file,index=False)

    with open(file,"rb") as f:

        st.download_button(
            "Download Excel",
            data=f,
            file_name=file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
