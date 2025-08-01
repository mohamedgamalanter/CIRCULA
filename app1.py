import streamlit as st
import pandas as pd
from PIL import Image
import base64
from io import BytesIO
import plotly.express as px
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="CIRCULA Dashboard", layout="wide")

# Load logo
logo = Image.open("logo_circula.png.jpeg")

def logo_to_base64(img):
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()

def render_animation():
    gif_path = "20250719_1311_Dynamic Logo Motion_simple_compose_01k0h2ne94fb0bqqcd2yek36yy.gif"
    gif_bytes = open(gif_path, "rb").read()
    encoded = base64.b64encode(gif_bytes).decode()
    st.markdown("""
        <style>
            [data-testid="stSidebar"] { display: none; }
            .block-container { padding-top: 0rem !important; }
            body { background: #111 !important; }
        </style>
        """, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style='display:flex;justify-content:center;align-items:center;height:100vh;width:100vw;position:fixed;top:0;left:0;z-index:99999;background:#111;'>
            <img src='data:image/gif;base64,{encoded}' style='width:80vw;height:auto;max-width:100vw;object-fit:contain;'>
        </div>
        """,
        unsafe_allow_html=True
    )
    time.sleep(6)
    st.rerun()

def render_header():
    role = st.session_state.get("role", "").capitalize()
    username = st.session_state.get("display_name", "")
    st.markdown(f"""
        <div style='display: flex; align-items: center;'>
            <img src='data:image/png;base64,{logo_to_base64(logo)}' width='60' style='margin-right: 20px;'>
            <h2>Welcome to CIRCULA, {role} - {username}</h2>
        </div>
        <hr style='border-top: 1px solid #bbb;'>
    """, unsafe_allow_html=True)

def authenticate_user():
    df_users = pd.read_excel("logistics_system_sheets.xlsx", sheet_name="Users")
    df_users.columns = df_users.columns.str.strip().str.lower()
    user_match = df_users[(df_users['username'] == st.session_state.username) & (df_users['password'] == st.session_state.password)]
    if not user_match.empty:
        user_info = user_match.iloc[0]
        st.session_state.logged_in = True
        st.session_state.role = user_info['role']
        st.session_state.branch_code = user_info['branch_code']
        st.session_state.display_name = user_info['username']
        st.success("Login successful")
        st.session_state.just_logged_in = True
        st.rerun()
    else:
        st.error("Invalid credentials")

def get_available_tabs(role):
    tab_roles = {
        "driver": ["Transfers"],
        "branch": ["Transfers", "KPIs"],
        "manager": ["Transfers", "KPIs", "Statistics"],
        "supervisor": ["Transfers", "KPIs", "Statistics"],
        "owner": ["Transfers", "KPIs", "Statistics"]
    }
    return tab_roles.get(role.lower(), []) + ["Logout"]

def render_notifications(df):
    role = st.session_state.role.lower()
    if role not in ["supervisor", "manager", "owner"]:
        return

    today = datetime.today()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    alerts = []

    # 1. Transfers older than 7 days not received
    week_old = df[(df['status'].str.lower() != 'received') & (today - df['date'] > timedelta(days=7))]
    if not week_old.empty:
        alerts.append(f"🚨 {len(week_old)} transfer(s) pending for over 7 days!")

    # 2. Branches with > 15 pending transfers
    pending_counts = df[df['status'].str.lower() == 'pending'].groupby('to').size()
    overloaded = pending_counts[pending_counts > 15]
    for branch, count in overloaded.items():
        alerts.append(f"⚠️ Branch {branch} has {count} pending transfers!")

    # 3. Pending at WH
    wh_pending = df[df['status'].str.lower() == 'pending at wh']
    if not wh_pending.empty:
        alerts.append(f"🏬 {len(wh_pending)} transfer(s) pending at Warehouse!")

    for alert in alerts:
        st.error(alert)

def update_transfer_status(transfer_id, new_status, driver=None):
    df = pd.read_excel("logistics_system_sheets.xlsx", sheet_name="Transfers")
    idx = df[df['transfer_id'] == transfer_id].index
    if not idx.empty:
        idx = idx[0]
        df.at[idx, 'status'] = new_status
        if new_status == "Picked Up":
            df.at[idx, 'driver'] = driver
            df.at[idx, 'picked_up_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if new_status == "Received":
            df.at[idx, 'received_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with pd.ExcelWriter("logistics_system_sheets.xlsx", engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            df.to_excel(writer, sheet_name="Transfers", index=False)

def render_transfer_cards(df, role):
    for i, row in df.iterrows():
        with st.container():
            st.markdown(f"**Transfer ID**: {row['transfer_id']} | **From**: {row['from']} ➡️ **To**: {row['to']} | **Status**: {row['status']}")
            st.json(row.to_dict())

            # Pick Up button for drivers
            if role == "driver" and row['status'].lower() in ["pending", "pending at wh"]:
                if st.button("🚚 Pick Up", key=f"pickup_{i}"):
                    update_transfer_status(row['transfer_id'], "Picked Up", driver=st.session_state.username)
                    st.success("تم تغيير الحالة إلى Picked Up")
                    st.rerun()

            # Receive button for branches (only for their incoming transfers)
            if role == "branch" and row['to'] == st.session_state.branch_code and row['status'].lower() in ["pending", "picked up"]:
                if st.button("📥 Receive", key=f"receive_{i}"):
                    update_transfer_status(row['transfer_id'], "Received")
                    st.success("تم تغيير الحالة إلى Received")
                    st.rerun()

def render_transfers():
    st.subheader("📦 Internal Transfers")
    role = st.session_state.get("role", "").lower()
    branch = st.session_state.get("branch_code", "")
    username = st.session_state.get("username", "")

    if role == "branch":
        st.markdown("### ➕ Create New Transfer")
        with st.form("new_transfer_form", clear_on_submit=True):
            transfer_id = st.text_input("Transfer ID")
            to_branch = st.text_input("To Branch")
            value = st.number_input("Transfer Value (SAR)", min_value=0.0, format="%.2f")
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Submit Transfer")
            if submitted:
                existing_df = pd.read_excel("logistics_system_sheets.xlsx", sheet_name="Transfers")
                template_cols = existing_df.columns.tolist()
                new_transfer = {
                    "transfer_id": transfer_id,
                    "from": branch,
                    "to": to_branch,
                    "value": value,
                    "notes": notes,
                    "status": "Pending",
                    "date": datetime.today().strftime('%Y-%m-%d'),
                    "driver": "",
                }
                for col in template_cols:
                    if col not in new_transfer:
                     new_transfer[col] = ""
                     new_transfer = {k: new_transfer.get(k, "") for k in template_cols}


                     df = pd.concat([pd.DataFrame([new_transfer]), existing_df], ignore_index=True)

                     with pd.ExcelWriter("logistics_system_sheets.xlsx", engine="openpyxl", mode="a",if_sheet_exists="replace") as writer:
                        df.to_excel(writer, sheet_name="Transfers", index=False)
                st.success("✅ Transfer created successfully.")

    df = pd.read_excel("logistics_system_sheets.xlsx", sheet_name="Transfers")
    role = st.session_state.role.lower()
    branch = st.session_state.branch_code
    username = st.session_state.username

    # ------------------------- فلترة التحويلات ---------------------------
    if role == "driver":
        df = df[
            ((df['status'].str.lower().isin(["pending", "pending at wh"]))) |
            ((df['status'].str.lower() == "picked up") & (df['driver'] == username))
        ]
    elif role == "branch":
        df = df[
            ((df['status'].str.lower().isin(["pending", "picked up"])) & (df['to'] == branch))
        ]
    elif role == "supervisor":
        df = df[df['from'].astype(str).str[:2] == str(branch)[:2]]
    elif role in ["manager", "owner"]:
        all_regions = sorted(df['from'].astype(str).str[:2].unique())
        selected_region = st.selectbox("📍 Filter by Region", ["All"] + all_regions)
        if selected_region != "All":
            df = df[df['from'].astype(str).str[:2] == selected_region]

        branches = sorted(df['from'].astype(str).unique())
        selected_branch = st.selectbox("🏪 Filter by Branch", ["All"] + branches)
        if selected_branch != "All":
            df = df[df['from'].astype(str) == selected_branch]

    status_options = df['status'].dropna().unique().tolist()
    selected_status = st.selectbox("📌 Filter by Status", ["All"] + status_options)
    if selected_status != "All":
        df = df[df['status'] == selected_status]

    search_term = st.text_input("🔍 Search by Transfer ID")
    if search_term:
        df = df[df['transfer_id'].astype(str).str.contains(search_term)]

    render_notifications(df)
    render_transfer_cards(df, role)

def render_kpis():
    st.subheader("📊 Performance KPIs")
    df = pd.read_excel("logistics_system_sheets.xlsx", sheet_name="Transfers")
    sent = df[df['status'].str.lower() == 'sent']
    received = df[df['status'].str.lower() == 'received']
    pending = df[df['status'].str.lower() == 'pending']
    picked_up = df[df['status'].str.lower() == 'picked up']

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Transfers", len(df))
    col2.metric("Sent", len(sent))
    col3.metric("Picked Up", len(picked_up))
    col4.metric("Received", len(received))
    col5.metric("Pending", len(pending))

    st.divider()

    top_sender = df.groupby('from')['value'].sum().reset_index().sort_values(by='value', ascending=False).head(1)
    top_receiver = df.groupby('to')['value'].sum().reset_index().sort_values(by='value', ascending=False).head(1)
    total_sent_value = df[df['status'].str.lower().isin(['sent', 'picked up'])]['value'].sum()
    total_received_value = df[df['status'].str.lower() == 'received']['value'].sum()

    col6, col7 = st.columns(2)
    with col6:
        st.metric("🏆 Top Sender", f"{top_sender['from'].values[0]}: {top_sender['value'].values[0]:,.2f}")
        st.metric("💰 Total Value Sent", f"{total_sent_value:,.2f} SAR")
    with col7:
        st.metric("📥 Top Receiver", f"{top_receiver['to'].values[0]}: {top_receiver['value'].values[0]:,.2f}")
        st.metric("💰 Total Value Received", f"{total_received_value:,.2f} SAR")

def render_statistics():
    st.subheader("📈 Transfer Statistics")
    df = pd.read_excel("logistics_system_sheets.xlsx", sheet_name="Transfers")
    top_senders = df['from'].value_counts().reset_index()
    top_senders.columns = ['Branch', 'Transfers Made']
    fig = px.bar(top_senders, x='Branch', y='Transfers Made', title='Transfers Made per Branch')
    st.plotly_chart(fig, use_container_width=True)

# Session Initialization
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.password = ""
    st.session_state.role = ""
    st.session_state.branch_code = ""
    st.session_state.display_name = ""
    st.session_state.selected_tab = "Transfers"
    st.session_state.just_logged_in = False

# Sidebar Login
with st.sidebar:
    st.image(logo, width=150)
    if not st.session_state.logged_in:
        st.markdown("# Login")
        st.session_state.username = st.text_input("Username", value=st.session_state.username)
        st.session_state.password = st.text_input("Password", type="password", value=st.session_state.password)
        if st.button("Login"):
            authenticate_user()
    else:
        tabs = get_available_tabs(st.session_state.role)
        st.session_state.selected_tab = st.selectbox("Select Tab", tabs)

# Authentication Gate
if not st.session_state.logged_in:
    st.warning("🚫 Please login first.")
    st.stop()

# Splash Animation after Login
if st.session_state.get("just_logged_in", False):
    st.session_state.just_logged_in = False
    render_animation()
if st.session_state.get("role", "").lower() == "owner":
    st.subheader("🔒 Download Data (Owner Only)")
    with open("logistics_system_sheets.xlsx", "rb") as f:
        bytes_data = f.read()
    st.download_button(
        label="Download Full Excel File",
        data=bytes_data,
        file_name="logistics_system_sheets.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
# Header Rendering
render_header()

# Tab Control
if st.session_state.selected_tab == "Transfers":
    render_transfers()
elif st.session_state.selected_tab == "KPIs":
    render_kpis()
elif st.session_state.selected_tab == "Statistics":
    render_statistics()
elif st.session_state.selected_tab == "Logout":
    st.session_state.logged_in = False
    st.success("You have been logged out.")
    st.rerun()
