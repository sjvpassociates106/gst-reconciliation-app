import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="GST Reconciliation", layout="wide")
st.title("GST 2B vs Purchase Register Reconciliation")


gstr2b_file = st.file_uploader("Upload GSTR-2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx","xls"])


# ---------------------------
# CLEAN INVOICE NUMBER
# ---------------------------

def clean_invoice(inv):

    if pd.isna(inv):
        return ""

    inv=str(inv)

    parts=re.split(r'[/-]',inv)

    for p in parts:

        num=re.sub(r'\D','',p)

        if len(num)>=3:
            return num

    return re.sub(r'\D','',inv)



# ---------------------------
# CLEAN COLUMN NAME
# ---------------------------

def clean(col):

    col=str(col).lower()
    col=col.replace("₹","")
    col=re.sub(r'[^a-z0-9]','',col)

    return col



# ---------------------------
# FIND COLUMN
# ---------------------------

def find_column(cols,keys):

    for c in cols:

        cc=clean(c)

        for k in keys:

            if k in cc:
                return c

    return None



# ---------------------------
# LOAD GSTR2B B2B
# ---------------------------

def load_2b(file):

    xl=pd.ExcelFile(file)

    if "B2B" not in xl.sheet_names:

        st.error("B2B sheet not found in GSTR-2B")
        st.stop()

    raw=xl.parse("B2B",header=None)

    header=0

    for i in range(len(raw)):

        if raw.iloc[i].astype(str).str.contains("gstin",case=False).any():

            header=i
            break

    df=xl.parse("B2B",header=header)

    df.columns=df.columns.str.strip()

    return df



# ---------------------------
# LOAD PURCHASE
# ---------------------------

def load_purchase(file):

    raw=pd.read_excel(file,header=None)

    header=0

    for i in range(len(raw)):

        row=raw.iloc[i].astype(str).str.lower()

        if any("gstin" in x for x in row):

            header=i
            break

    df=pd.read_excel(file,header=header)

    df.columns=df.columns.str.strip()

    return df



# ---------------------------
# MAIN
# ---------------------------

if gstr2b_file and purchase_file:

    gstr2b=load_2b(gstr2b_file)

    purchase=load_purchase(purchase_file)


    # detect columns

    gstin2b=find_column(gstr2b.columns,["gstin"])
    name2b=find_column(gstr2b.columns,["tradename","legalname","tradelegalname"])
    inv2b=find_column(gstr2b.columns,["invoice"])
    date2b=find_column(gstr2b.columns,["date"])
    igst2b=find_column(gstr2b.columns,["integrated"])
    cgst2b=find_column(gstr2b.columns,["central"])
    sgst2b=find_column(gstr2b.columns,["state"])


    gstinpr=find_column(purchase.columns,["gstin"])
    namepr=find_column(purchase.columns,["particular"])
    invpr=find_column(purchase.columns,["invoice"])
    datepr=find_column(purchase.columns,["date"])
    igstpr=find_column(purchase.columns,["igst"])
    cgstpr=find_column(purchase.columns,["cgst"])
    sgstpr=find_column(purchase.columns,["sgst"])



    df2b=pd.DataFrame({

        "GSTIN":gstr2b[gstin2b].astype(str).str.strip().str.upper(),

        "Party":gstr2b[name2b],

        "Invoice":gstr2b[inv2b].apply(clean_invoice),

        "Date2B":pd.to_datetime(gstr2b[date2b],errors="coerce"),

        "IGST2B":pd.to_numeric(gstr2b[igst2b],errors="coerce").fillna(0),

        "CGST2B":pd.to_numeric(gstr2b[cgst2b],errors="coerce").fillna(0),

        "SGST2B":pd.to_numeric(gstr2b[sgst2b],errors="coerce").fillna(0)

    })


    dfpr=pd.DataFrame({

        "GSTIN":purchase[gstinpr].astype(str).str.strip().str.upper(),

        "Party":purchase[namepr],

        "Invoice":purchase[invpr].apply(clean_invoice),

        "DatePR":pd.to_datetime(purchase[datepr],errors="coerce"),

        "IGSTPR":pd.to_numeric(purchase[igstpr],errors="coerce").fillna(0),

        "CGSTPR":pd.to_numeric(purchase[cgstpr],errors="coerce").fillna(0),

        "SGSTPR":pd.to_numeric(purchase[sgstpr],errors="coerce").fillna(0)

    })



    recon=pd.merge(dfpr,df2b,on=["GSTIN","Invoice"],how="outer",indicator=True)



    def status(r):

        if r["_merge"]=="left_only":

            return pd.Series(["Mismatch","Missing in 2B"])

        if r["_merge"]=="right_only":

            return pd.Series(["Mismatch","Missing in Purchase"])

        reasons=[]

        if round(r["IGSTPR"],2)!=round(r["IGST2B"],2):
            reasons.append("IGST mismatch")

        if round(r["CGSTPR"],2)!=round(r["CGST2B"],2):
            reasons.append("CGST mismatch")

        if round(r["SGSTPR"],2)!=round(r["SGST2B"],2):
            reasons.append("SGST mismatch")

        if len(reasons)==0:
            return pd.Series(["Matched",""])

        return pd.Series(["Mismatch",",".join(reasons)])



    recon[["Status","Reason"]]=recon.apply(status,axis=1)

    recon=recon.drop(columns=["_merge"])



    st.subheader("Summary")

    st.write(recon["Status"].value_counts())


    st.subheader("Reconciliation Result")

    st.dataframe(recon,use_container_width=True)



    file="GST_Reconciliation_Output.xlsx"

    recon.to_excel(file,index=False)


    with open(file,"rb") as f:

        st.download_button(
            "Download Excel Report",
            data=f,
            file_name=file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
