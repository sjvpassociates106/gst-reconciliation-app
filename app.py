import streamlit as st
import pandas as pd

# -------------------------
# SIMPLE LOGIN SYSTEM
# -------------------------

USER_CREDENTIALS = {
    "admin": "admin123",
    "staff1": "gst2026"
}

def login():
    st.title("GST Reconciliation Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
            st.session_state.logged_in = True
        else:
            st.error("Invalid Username or Password")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login()
    st.stop()

# -------------------------
# MAIN GST APPLICATION
# -------------------------

st.title("Enterprise GST Reconciliation System")

gstr2b_file = st.file_uploader("Upload GSTR 2B File", type=["xlsx"])
purchase_file = st.file_uploader("Upload Purchase Register File", type=["xlsx"])

if gstr2b_file and purchase_file:

    gstr2b = pd.read_excel(gstr2b_file)
    purchase = pd.read_excel(purchase_file)

    gstr2b.columns = gstr2b.columns.str.strip()
    purchase.columns = purchase.columns.str.strip()

    gstr2b["Invoice No"] = gstr2b["Invoice No"].astype(str).str.strip().str.upper()
    purchase["Bill No"] = purchase["Bill No"].astype(str).str.strip().str.upper()

    gstr2b["GSTIN"] = gstr2b["GSTIN"].astype(str).str.strip()
    purchase["Supplier GSTIN"] = purchase["Supplier GSTIN"].astype(str).str.strip()

    recon = pd.merge(
        purchase,
        gstr2b,
        left_on=["Supplier GSTIN", "Bill No"],
        right_on=["GSTIN", "Invoice No"],
        how="outer",
        indicator=True
    )

    def classify(row):
        if row["_merge"] == "both":
            return "Matched"
        elif row["_merge"] == "left_only":
            return "In Purchase Not in 2B"
        else:
            return "In 2B Not in Purchase"

    recon["Status"] = recon.apply(classify, axis=1)

    st.success("Reconciliation Completed")
    st.dataframe(recon, use_container_width=True)

    st.download_button(
        label="Download Reconciliation Report",
        data=recon.to_csv(index=False),
        file_name="GST_Reconciliation_Report.csv",
        mime="text/csv"
    )

if st.button("Logout"):
    st.session_state.logged_in = False
