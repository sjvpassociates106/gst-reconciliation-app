import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="GST Reconciliation", layout="wide")
st.title("GST 2B vs Purchase Register Reconciliation")

gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx","xls"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx","xls"])


# ----------------------------
# CLEAN COLUMN NAME
# ----------------------------

def clean(text):
    text=str(text).lower()
    text=text.replace("₹","")
    text=re.sub(r'[^a-z0-9]','',text)
    return text


# ----------------------------
# FIND COLUMN
# ----------------------------

def find_column(columns, keywords):

    for col in columns:
        c=clean(col)

        for key in keywords:
            if key in c:
                return col

    return None


# ----------------------------
# SAFE NUMBER
# ----------------------------

def safe_number(df,col):

    if col and col in df.columns:
        return pd.to_numeric(df[col],errors="coerce").fillna(0)

    return 0


# ----------------------------
# LOAD GSTR-2B
# ----------------------------

def load_gstr2b(file):

    excel=pd.ExcelFile(file)

    if "B2B" not in excel.sheet_names:
        st.error("B2B sheet not found in GSTR-2B")
        st.stop()

    raw=excel.parse("B2B",header=None)

    header_row=0

    for i in range(len(raw)):

        if raw.iloc[i].astype(str).str.contains("gstin",case=False).any():
            header_row=i
            break

    df=excel.parse("B2B",header=header_row)
    df.columns=df.columns.str.strip()

    return df


# ----------------------------
# LOAD PURCHASE REGISTER
# ----------------------------

def load_purchase(file):

    raw=pd.read_excel(file,header=None)

    header_row=0

    for i in range(len(raw)):

        row=raw.iloc[i].astype(str).str.lower()

        if any("gstin" in x for x in row):
            header_row=i
            break

    df=pd.read_excel(file,header=header_row)
    df.columns=df.columns.str.strip()

    return df


# ----------------------------
# MAIN PROCESS
# ----------------------------

if gstr2b_file and purchase_file:

    gstr2b=load_gstr2b(gstr2b_file)
    purchase=load_purchase(purchase_file)

    # detect columns automatically

    gstin2b=find_column(gstr2b.columns,["gstin"])
    invoice2b=find_column(gstr2b.columns,["invoice"])
    taxable2b=find_column(gstr2b.columns,["taxable"])
    igst2b=find_column(gstr2b.columns,["igst","integrated"])
    cgst2b=find_column(gstr2b.columns,["cgst","central"])
    sgst2b=find_column(gstr2b.columns,["sgst","state"])

    gstinpr=find_column(purchase.columns,["gstin"])
    invoicepr=find_column(purchase.columns,["invoice"])
    taxablepr=find_column(purchase.columns,["taxable","value"])
    igstpr=find_column(purchase.columns,["igst"])
    cgstpr=find_column(purchase.columns,["cgst"])
    sgstpr=find_column(purchase.columns,["sgst"])


    # create standard tables

    df2b=pd.DataFrame({

        "GSTIN":gstr2b[gstin2b].astype(str).str.strip().str.upper(),
        "Invoice":gstr2b[invoice2b].astype(str).str.strip().str.upper(),
        "Taxable2B":safe_number(gstr2b,taxable2b),
        "IGST2B":safe_number(gstr2b,igst2b),
        "CGST2B":safe_number(gstr2b,cgst2b),
        "SGST2B":safe_number(gstr2b,sgst2b)

    })


    dfpr=pd.DataFrame({

        "GSTIN":purchase[gstinpr].astype(str).str.strip().str.upper(),
        "Invoice":purchase[invoicepr].astype(str).str.strip().str.upper(),
        "TaxablePR":safe_number(purchase,taxablepr),
        "IGSTPR":safe_number(purchase,igstpr),
        "CGSTPR":safe_number(purchase,cgstpr),
        "SGSTPR":safe_number(purchase,sgstpr)

    })


    # merge

    recon=pd.merge(dfpr,df2b,on=["GSTIN","Invoice"],how="outer",indicator=True)


    # status logic

    def check(row):

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


    recon[["Status","Reason"]]=recon.apply(check,axis=1)

    recon=recon.drop(columns=["_merge"])


    st.subheader("Summary")

    st.write(recon["Status"].value_counts())


    st.subheader("Reconciliation Result")

    st.dataframe(recon,use_container_width=True)


    # export

    file="GST_Reconciliation_Output.xlsx"

    recon.to_excel(file,index=False)

    with open(file,"rb") as f:

        st.download_button(
            "Download Excel",
            data=f,
            file_name=file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
