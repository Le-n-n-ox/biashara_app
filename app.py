import streamlit as st

# Set up the page header
st.title("Biashara Bookkeeper 📊")
st.subheader("Paste your daily M-Pesa SMS receipts below:")

# Text area for user input
sms_input = st.text_area("M-Pesa Messages", height=200, placeholder="Paste raw M-Pesa SMS here...")

# Button to trigger processing
if st.button("Analyze Receipts"):
    if sms_input:
        st.success("Messages received! (We will process these in the next step)")
    else:
        st.warning("Please paste some messages first.")