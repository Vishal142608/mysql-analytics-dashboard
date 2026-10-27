import datetime
from decimal import Decimal
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pymysql
import streamlit as st

# ==============================================================================
# SECURE CONFIGURATION (Streamlit Secrets / Environment Variables)
# No real passwords stored in source code. Configured via .streamlit/secrets.toml
# or Streamlit Community Cloud Settings -> Secrets.
# ==============================================================================
def get_config_val(key: str, default: Any = None) -> Any:
    """Fetch configuration from Streamlit secrets, then environment variable, then fallback default."""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)

MYSQL_HOST = str(get_config_val("MYSQL_HOST", "localhost"))
MYSQL_PORT = int(get_config_val("MYSQL_PORT", 3306))
MYSQL_USER = str(get_config_val("MYSQL_USER", "root"))
MYSQL_PASSWORD = str(get_config_val("MYSQL_PASSWORD", ""))

_raw_dbs = get_config_val("DATABASES", ["row_data", "student_1_to_12"])
if isinstance(_raw_dbs, str):
    DATABASES = [d.strip() for d in _raw_dbs.split(",") if d.strip()]
else:
    DATABASES = list(_raw_dbs)

DASHBOARD_PASSWORD = str(get_config_val("DASHBOARD_PASSWORD", ""))
MASK_PII = bool(get_config_val("MASK_PII", False))

# ==============================================================================
# STREAMLIT PAGE CONFIGURATION & CUSTOM STYLING
# ==============================================================================
st.set_page_config(
    page_title="MySQL Data Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

CUSTOM_CSS = """
<style>
    /* Global Styles */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    
    /* Modern KPI Cards */
    .kpi-container {
        background: linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .kpi-container:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px -1px rgba(0, 0, 0, 0.15);
    }
    .kpi-title {
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #888888;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 1.75rem;
        font-weight: 700;
        color: #1E88E5;
        line-height: 1.2;
    }
    .kpi-subtitle {
        font-size: 0.78rem;
        color: #9E9E9E;
        margin-top: 6px;
    }

    /* Badges */
    .badge {
        display: inline-block;
        padding: 3px 8px;
        font-size: 0.75rem;
        font-weight: 600;
        border-radius: 6px;
        margin-right: 5px;
    }
    .badge-primary { background-color: #E3F2FD; color: #1565C0; }
    .badge-success { background-color: #E8F5E9; color: #2E7D32; }
    .badge-warning { background-color: #FFF3E0; color: #E65100; }
    .badge-info { background-color: #EDE7F6; color: #4527A0; }
    
    /* Section Headers */
    .section-header {
        font-size: 1.25rem;
        font-weight: 700;
        margin-top: 1rem;
        margin-bottom: 0.75rem;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid rgba(128,128,128,0.2);
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ==============================================================================
# CONFIDENTIAL ACCESS GATEWAY (Optional Authentication)
# ==============================================================================
if DASHBOARD_PASSWORD:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.markdown("### 🔐 Restricted Access Analytics Dashboard")
        st.info("This application contains confidential analytics and student/school records. Please enter the passcode to access the dashboard.")
        
        login_col1, login_col2 = st.columns([2, 1])
        with login_col1:
            entered_pin = st.text_input("Enter Passcode:", type="password", key="login_passcode_input")
            if st.button("Unlock Dashboard", type="primary"):
                if entered_pin == DASHBOARD_PASSWORD:
                    st.session_state.authenticated = True
                    st.success("Access authorized.")
                    st.rerun()
                else:
                    st.error("Incorrect passcode. Access denied.")
        st.stop()

# ==============================================================================
# SECURITY, SANITIZATION & CONNECTION HELPERS
# ==============================================================================
def sanitize_error(e: Exception) -> str:
    """Strip password and sensitive connection details from error messages."""
    msg = str(e)
    if MYSQL_PASSWORD:
        msg = msg.replace(MYSQL_PASSWORD, "********")
    if MYSQL_USER:
        msg = msg.replace(MYSQL_USER, "[USER]")
    if MYSQL_HOST:
        msg = msg.replace(MYSQL_HOST, "[HOST]")
    return msg

def safe_ident(identifier: str) -> str:
    """Safely quote a MySQL identifier using backticks, escaping internal backticks."""
    clean = str(identifier).replace("`", "``")
    return f"`{clean}`"

def get_db_connection(database: Optional[str] = None):
    """Establish a safe PyMySQL connection to the MySQL server."""
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=int(MYSQL_PORT),
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            autocommit=True
        )
        return conn
    except Exception as e:
        safe_msg = sanitize_error(e)
        st.error(f"❌ Database Connection Error: {safe_msg}")
        return None

def execute_readonly_query(sql: str, params: Optional[Tuple] = None, database: Optional[str] = None) -> List[Dict[str, Any]]:
    """Execute a parameterized read-only query safely and return results as list of dicts."""
    clean_sql = sql.strip().upper()
    allowed_prefixes = ("SELECT", "SHOW", "DESCRIBE", "EXPLAIN")
    if not any(clean_sql.startswith(prefix) for prefix in allowed_prefixes):
        raise ValueError("Security Violation: Only read-only queries (SELECT, SHOW, DESCRIBE, EXPLAIN) are permitted.")
    
    # Block destructive SQL statements
    forbidden_keywords = [" DROP ", " TRUNCATE ", " ALTER ", " DELETE ", " INSERT ", " UPDATE ", " CREATE ", " REPLACE "]
    for kw in forbidden_keywords:
        if kw in f" {clean_sql} ":
            raise ValueError(f"Security Violation: Destructive operation '{kw.strip()}' is blocked.")

    conn = get_db_connection(database=database)
    if not conn:
        return []
    
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            return rows
    except Exception as e:
        safe_msg = sanitize_error(e)
        st.error(f"Query Execution Error: {safe_msg}")
        return []
    finally:
        conn.close()

def execute_query_df(sql: str, params: Optional[Tuple] = None, database: Optional[str] = None) -> pd.DataFrame:
    """Execute a read-only query and return the result as a Pandas DataFrame."""
    rows = execute_readonly_query(sql, params=params, database=database)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Convert Decimals to float or int for clean Plotly rendering
    for col in df.columns:
        if len(df) > 0 and isinstance(df[col].iloc[0], Decimal):
            df[col] = df[col].astype(float)
    return df

# ==============================================================================
# FORMATTING UTILITIES
# ==============================================================================
def fmt_num(val: Any) -> str:
    """Format integers or floats with thousands separator."""
    if val is None or pd.isna(val):
        return "0"
    try:
        return f"{int(val):,}"
    except (ValueError, TypeError):
        try:
            return f"{float(val):,.2f}"
        except (ValueError, TypeError):
            return str(val)

def fmt_curr(val: Any, symbol: str = "₹") -> str:
    """Format numbers as currency."""
    if val is None or pd.isna(val):
        return f"{symbol}0.00"
    try:
        return f"{symbol}{float(val):,.2f}"
    except (ValueError, TypeError):
        return f"{symbol}{val}"

def fmt_pct(val: Any, total: Any) -> str:
    """Format percentage cleanly."""
    try:
        if not total or float(total) == 0:
            return "0.0%"
        pct = (float(val) / float(total)) * 100
        return f"{pct:.1f}%"
    except Exception:
        return "0.0%"

def render_kpi(title: str, value: str, subtitle: Optional[str] = None, color: str = "#1E88E5"):
    """Render a styled KPI card."""
    sub_html = f'<div class="kpi-subtitle">{subtitle}</div>' if subtitle else ""
    html = f"""
    <div class="kpi-container">
        <div class="kpi-title">{title}</div>
        <div class="kpi-value" style="color: {color};">{value}</div>
        {sub_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def mask_value(val: Any, col_type: str = "general") -> str:
    """Mask sensitive personal information (PII) for privacy."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    if not s or s == "NULL":
        return s
    if col_type == "phone":
        if len(s) > 6:
            return s[:3] + "•••" + s[-3:]
        return "••••••"
    elif col_type == "email":
        if "@" in s:
            user, domain = s.split("@", 1)
            masked_user = user[:2] + "•••" if len(user) > 2 else "•••"
            return f"{masked_user}@{domain}"
        return "•••@•••"
    return s

def apply_pii_mask(df: pd.DataFrame) -> pd.DataFrame:
    """Apply PII masking if MASK_PII is active."""
    if not MASK_PII or df.empty:
        return df
    masked_df = df.copy()
    for col in masked_df.columns:
        c_low = col.lower()
        if any(k in c_low for k in ["phone", "mobile", "cell", "number"]):
            masked_df[col] = masked_df[col].apply(lambda v: mask_value(v, "phone"))
        elif "email" in c_low:
            masked_df[col] = masked_df[col].apply(lambda v: mask_value(v, "email"))
    return masked_df

# ==============================================================================
# CACHED METADATA & SCHEMA DISCOVERY
# ==============================================================================
@st.cache_data(show_spinner="Discovering MySQL Databases and Tables...", ttl=300)
def discover_metadata() -> Dict[str, Any]:
    """
    Automatically discover all configured databases, actual tables,
    exact row counts, columns, data types, and storage sizes via MySQL information_schema.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Discover accessible databases
    available_dbs = []
    db_rows = execute_readonly_query("SHOW DATABASES;")
    all_server_dbs = [r[list(r.keys())[0]] for r in db_rows] if db_rows else []
    for db in DATABASES:
        if db in all_server_dbs:
            available_dbs.append(db)
            
    if not available_dbs:
        return {
            "timestamp": timestamp,
            "databases": [],
            "tables": [],
            "table_meta": {},
            "columns": {},
            "total_rows": 0,
            "total_size_mb": 0.0
        }

    # 2. Discover tables from information_schema
    db_placeholders = ",".join(["%s"] * len(available_dbs))
    tables_sql = f"""
        SELECT 
            TABLE_SCHEMA as db_name,
            TABLE_NAME as table_name,
            TABLE_ROWS as approx_rows,
            ROUND(DATA_LENGTH / 1024 / 1024, 2) as data_size_mb,
            ROUND(INDEX_LENGTH / 1024 / 1024, 2) as index_size_mb,
            ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) as total_size_mb,
            CREATE_TIME,
            UPDATE_TIME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA IN ({db_placeholders})
        ORDER BY TABLE_SCHEMA, TABLE_NAME;
    """
    table_rows = execute_readonly_query(tables_sql, params=tuple(available_dbs))
    
    tables_list = []
    table_meta = {}
    total_system_rows = 0
    total_size_mb = 0.0

    # 3. Obtain exact COUNT(*) for every table safely
    for row in table_rows:
        db = row["db_name"]
        tbl = row["table_name"]
        full_name = f"{db}.{tbl}"
        
        # Get exact row count via SELECT COUNT(*)
        cnt_sql = f"SELECT COUNT(*) as exact_count FROM {safe_ident(db)}.{safe_ident(tbl)};"
        cnt_res = execute_readonly_query(cnt_sql)
        exact_rows = cnt_res[0]["exact_count"] if cnt_res else int(row["approx_rows"] or 0)
        
        # Discover columns for this table
        col_sql = f"""
            SELECT 
                COLUMN_NAME,
                ORDINAL_POSITION,
                COLUMN_DEFAULT,
                IS_NULLABLE,
                DATA_TYPE,
                COLUMN_TYPE,
                COLUMN_KEY,
                EXTRA
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION;
        """
        col_res = execute_readonly_query(col_sql, params=(db, tbl))
        col_count = len(col_res)
        
        t_data_mb = float(row["data_size_mb"] or 0.0)
        t_idx_mb = float(row["index_size_mb"] or 0.0)
        t_total_mb = float(row["total_size_mb"] or 0.0)
        
        total_system_rows += exact_rows
        total_size_mb += t_total_mb
        
        meta_entry = {
            "db_name": db,
            "table_name": tbl,
            "full_name": full_name,
            "row_count": exact_rows,
            "col_count": col_count,
            "data_size_mb": t_data_mb,
            "index_size_mb": t_idx_mb,
            "total_size_mb": t_total_mb,
            "columns": col_res
        }
        table_meta[full_name] = meta_entry
        tables_list.append(meta_entry)

    return {
        "timestamp": timestamp,
        "databases": available_dbs,
        "tables": tables_list,
        "table_meta": table_meta,
        "total_rows": total_system_rows,
        "total_size_mb": round(total_size_mb, 2)
    }

# ==============================================================================
# SIDEBAR NAVIGATION & CONTROLS
# ==============================================================================
metadata = discover_metadata()

with st.sidebar:
    st.markdown("### 🗄️ MySQL Analytics")
    
    # Connection status indicator
    if metadata["databases"]:
        st.success(f"🟢 **Connected to MySQL**\n\nHost: `{MYSQL_HOST}:{MYSQL_PORT}`\n\nDatabases: `{', '.join(metadata['databases'])}`")
    else:
        st.error(f"🔴 **Database Disconnected**\n\nCould not access configured databases `{DATABASES}` on `{MYSQL_HOST}:{MYSQL_PORT}`.")
        if MYSQL_HOST in ("localhost", "127.0.0.1"):
            st.warning(
                "☁️ **Cloud Deployment Notice:**\n\n"
                "When deployed on cloud hosting (e.g. Streamlit Community Cloud), `localhost` refers to the cloud container, "
                "not your local machine. Please configure your remote or hosted MySQL credentials in **Streamlit Cloud App Settings → Secrets**."
            )
    
    # Global Refresh button
    if st.button("🔄 Refresh Data & Cache", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()

    # Session authentication status
    if DASHBOARD_PASSWORD and st.session_state.get("authenticated", False):
        if st.button("🔒 Logout / Lock", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    st.markdown("---")
    st.markdown("### 🧭 Navigation")
    pages = [
        "📊 Main Overview Dashboard",
        "🎓 Student Analytics",
        "🏫 School Analytics",
        "📈 Marketing & Contact Analytics",
        "📝 OCR & Registration Analytics",
        "🔍 Duplicate Analysis Engine",
        "🗂️ Dedicated Table Sections",
        "🧭 Dynamic Table Explorer"
    ]
    current_page = st.radio("Go to Page:", pages, index=0)
    
    st.markdown("---")
    st.caption(f"Last Refreshed:\n`{metadata.get('timestamp', 'N/A')}`")
    st.caption(f"Discovered Tables: **{len(metadata.get('tables', []))}**")
    st.caption(f"Total Rows: **{fmt_num(metadata.get('total_rows', 0))}**")

# ==============================================================================
# PAGE 1: MAIN OVERVIEW DASHBOARD
# ==============================================================================
if current_page == "📊 Main Overview Dashboard":
    st.title("📊 MySQL Data Analytics Overview")
    st.markdown("High-level system topology, discovered databases, table sizing, and record volume comparisons.")

    # Contextual Callout
    st.info(
        "ℹ️ **Record Volume Notice:** Total records represent the aggregate row count across all tables. "
        "Because operational workflows duplicate contacts, school records, and registrations across multiple tables "
        "(e.g., `students_records`, `ocr_table`, `ors_school`), total records is strictly greater than unique individuals or schools."
    )

    # Top KPI Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        render_kpi("Connected Databases", str(len(metadata["databases"])), "Target Schemas", "#2563EB")
    with col2:
        render_kpi("Discovered Tables", str(len(metadata["tables"])), "Auto-discovered", "#7C3AED")
    with col3:
        render_kpi("Total Records", fmt_num(metadata["total_rows"]), "Across all tables", "#059669")
    with col4:
        render_kpi("Storage Footprint", f"{metadata['total_size_mb']:.1f} MB", "Data + Index Size", "#D97706")
    with col5:
        render_kpi("Last Refresh", metadata["timestamp"].split(" ")[1], metadata["timestamp"].split(" ")[0], "#4B5563")

    st.markdown("---")

    # Visual Charts
    col_chart1, col_chart2 = st.columns([3, 2])
    
    table_df = pd.DataFrame(metadata["tables"])
    if not table_df.empty:
        with col_chart1:
            st.subheader("📊 Table Size Comparison (Row Counts)")
            sorted_tbls = table_df.sort_values(by="row_count", ascending=True)
            fig_bar = px.bar(
                sorted_tbls,
                x="row_count",
                y="full_name",
                orientation="h",
                color="db_name",
                text="row_count",
                labels={"row_count": "Total Rows", "full_name": "Table", "db_name": "Database"},
                color_discrete_map={"row_data": "#3B82F6", "student_1_to_12": "#10B981"}
            )
            fig_bar.update_traces(texttemplate='%{text:,}', textposition='outside')
            fig_bar.update_layout(
                margin=dict(l=20, r=40, t=20, b=20),
                height=420,
                xaxis_title="Record Count",
                yaxis_title="",
                legend_title="Database",
                hovermode="y unified"
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_chart2:
            st.subheader("🍩 Database Volume Split")
            db_agg = table_df.groupby("db_name")["row_count"].sum().reset_index()
            fig_pie = px.pie(
                db_agg,
                names="db_name",
                values="row_count",
                hole=0.45,
                color="db_name",
                color_discrete_map={"row_data": "#3B82F6", "student_1_to_12": "#10B981"}
            )
            fig_pie.update_traces(textinfo="label+percent", hovertemplate="<b>%{label}</b><br>Rows: %{value:,}<br>Share: %{percent}")
            fig_pie.update_layout(
                margin=dict(l=20, r=20, t=20, b=20),
                height=420,
                legend_title="Database"
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    # Summary Table Inventory
    st.markdown('<div class="section-header">📋 Complete Database & Table Inventory</div>', unsafe_allow_html=True)
    if not table_df.empty:
        display_tbl = table_df[["db_name", "table_name", "row_count", "col_count", "data_size_mb", "index_size_mb", "total_size_mb"]].copy()
        display_tbl.columns = ["Database", "Table Name", "Total Rows", "Columns", "Data Size (MB)", "Index Size (MB)", "Total Size (MB)"]
        display_tbl["Total Rows"] = display_tbl["Total Rows"].apply(fmt_num)
        
        st.dataframe(
            display_tbl,
            use_container_width=True,
            hide_index=True
        )

# ==============================================================================
# PAGE 2: STUDENT ANALYTICS DASHBOARD
# ==============================================================================
elif current_page == "🎓 Student Analytics":
    st.title("🎓 Student Records Analytics")
    st.markdown("Detailed analytics, order distributions, and payment metrics for `student_1_to_12.students_records`.")

    # Check if student_1_to_12.students_records exists
    if "student_1_to_12.students_records" not in metadata["table_meta"]:
        st.warning("⚠️ Table `student_1_to_12.students_records` was not discovered in the MySQL server.")
    else:
        # Load distinct filter choices safely via SQL
        @st.cache_data(ttl=600)
        def get_student_filter_options():
            classes = [r["Class"] for r in execute_readonly_query("SELECT DISTINCT `Class` FROM `student_1_to_12`.`students_records` WHERE `Class` IS NOT NULL ORDER BY `Class`;") if r["Class"]]
            states = [r["State"] for r in execute_readonly_query("SELECT DISTINCT `State` FROM `student_1_to_12`.`students_records` WHERE `State` IS NOT NULL AND TRIM(`State`) != '' ORDER BY `State`;") if r["State"]]
            exams = [r["ExamName"] for r in execute_readonly_query("SELECT DISTINCT `ExamName` FROM `student_1_to_12`.`students_records` WHERE `ExamName` IS NOT NULL AND TRIM(`ExamName`) != '' ORDER BY `ExamName`;") if r["ExamName"]]
            statuses = [r["OrderStatus"] for r in execute_readonly_query("SELECT DISTINCT `OrderStatus` FROM `student_1_to_12`.`students_records` WHERE `OrderStatus` IS NOT NULL ORDER BY `OrderStatus`;") if r["OrderStatus"]]
            min_max_date = execute_readonly_query("SELECT MIN(DATE(OrderCreated)) as min_d, MAX(DATE(OrderCreated)) as max_d FROM `student_1_to_12`.`students_records`;")
            return classes, states, exams, statuses, min_max_date[0] if min_max_date else {"min_d": None, "max_d": None}

        classes_opt, states_opt, exams_opt, statuses_opt, date_bounds = get_student_filter_options()

        # Filter Section
        with st.expander("🔍 Interactive Analytics Filters", expanded=True):
            f_col1, f_col2, f_col3, f_col4 = st.columns(4)
            with f_col1:
                sel_classes = st.multiselect("Class:", options=classes_opt, default=[])
                sel_school = st.text_input("School Name / Code (Keyword):", value="")
            with f_col2:
                sel_states = st.multiselect("State:", options=states_opt, default=[])
                sel_exams = st.multiselect("Exam Name:", options=exams_opt, default=[])
            with f_col3:
                sel_statuses = st.multiselect("Order Status:", options=statuses_opt + ["NULL / None"], default=[])
            with f_col4:
                min_d = date_bounds["min_d"] or datetime.date(2025, 1, 1)
                max_d = date_bounds["max_d"] or datetime.date(2026, 12, 31)
                date_range = st.date_input("Order Date Range:", value=(min_d, max_d), min_value=min_d, max_value=max_d)

        # Build parameterized SQL WHERE clause
        where_clauses = ["1=1"]
        params = []

        if sel_classes:
            placeholders = ",".join(["%s"] * len(sel_classes))
            where_clauses.append(f"`Class` IN ({placeholders})")
            params.extend(sel_classes)

        if sel_school.strip():
            where_clauses.append("(`SchoolName` LIKE %s OR `SchoolCode` LIKE %s)")
            params.extend([f"%{sel_school.strip()}%", f"%{sel_school.strip()}%"])

        if sel_states:
            placeholders = ",".join(["%s"] * len(sel_states))
            where_clauses.append(f"`State` IN ({placeholders})")
            params.extend(sel_states)

        if sel_exams:
            placeholders = ",".join(["%s"] * len(sel_exams))
            where_clauses.append(f"`ExamName` IN ({placeholders})")
            params.extend(sel_exams)

        if sel_statuses:
            status_clauses = []
            for st_val in sel_statuses:
                if st_val == "NULL / None":
                    status_clauses.append("`OrderStatus` IS NULL OR TRIM(`OrderStatus`) = ''")
                else:
                    status_clauses.append("`OrderStatus` = %s")
                    params.append(st_val)
            where_clauses.append(f"({' OR '.join(status_clauses)})")

        if isinstance(date_range, tuple) and len(date_range) == 2:
            where_clauses.append("DATE(OrderCreated) >= %s AND DATE(OrderCreated) <= %s")
            params.extend([str(date_range[0]), str(date_range[1])])

        where_sql = " AND ".join(where_clauses)

        # Aggregate metrics via SQL
        kpi_sql = f"""
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT `SchoolCode`) as unique_schools,
                COUNT(DISTINCT `SchoolName`) as unique_school_names,
                COUNT(DISTINCT `StudentName`) as unique_students,
                COALESCE(SUM(`ExamCount`), 0) as total_exams,
                COALESCE(SUM(`Total_paid__number`), 0) as total_paid,
                COALESCE(SUM(`Total_price__number`), 0) as total_price
            FROM `student_1_to_12`.`students_records`
            WHERE {where_sql};
        """
        kpi_data = execute_readonly_query(kpi_sql, params=tuple(params))
        k = kpi_data[0] if kpi_data else {}

        tot_rec = k.get("total_records", 0)
        tot_paid = float(k.get("total_paid", 0) or 0)
        tot_price = float(k.get("total_price", 0) or 0)
        paid_ratio = (tot_paid / tot_price * 100) if tot_price > 0 else 0.0

        # KPI Display Row
        k_c1, k_c2, k_c3, k_c4 = st.columns(4)
        with k_c1:
            render_kpi("Filtered Records", fmt_num(tot_rec), "Total rows matching filters", "#1E88E5")
        with k_c2:
            render_kpi("Unique School Codes", fmt_num(k.get("unique_schools", 0)), f"Names: {fmt_num(k.get('unique_school_names', 0))}", "#7C3AED")
        with k_c3:
            render_kpi("Unique Student Names", fmt_num(k.get("unique_students", 0)), "Distinct name strings", "#059669")
        with k_c4:
            render_kpi("Total Exams Registered", fmt_num(k.get("total_exams", 0)), "Sum of ExamCount", "#D97706")

        k_c5, k_c6, k_c7, k_c8 = st.columns(4)
        with k_c5:
            render_kpi("Total Paid Amount", fmt_curr(tot_paid), "Realized Revenue", "#2E7D32")
        with k_c6:
            render_kpi("Total Price Amount", fmt_curr(tot_price), "Order Value", "#1565C0")
        with k_c7:
            render_kpi("Collection Rate", f"{paid_ratio:.1f}%", "Paid vs Price", "#6A1B9A")
        with k_c8:
            render_kpi("Avg Order Price", fmt_curr(tot_price / tot_rec if tot_rec > 0 else 0), "Per Registration", "#455A64")

        # Clarification Note
        st.caption(
            "📌 **Limitation Note on Unique Student Names:** The unique student count represents distinct name strings. "
            "Because different students in different schools may share common names, and conversely slight typographical differences "
            "in the same student's name count as distinct entries, this number is an approximation."
        )

        st.markdown("---")

        # Analytical Charts
        c_r1_1, c_r1_2 = st.columns(2)
        
        # 1. Records by Class
        with c_r1_1:
            st.subheader("📚 Records by Class")
            class_df = execute_query_df(f"""
                SELECT `Class`, COUNT(*) as count 
                FROM `student_1_to_12`.`students_records`
                WHERE {where_sql} AND `Class` IS NOT NULL
                GROUP BY `Class`
                ORDER BY LENGTH(`Class`), `Class`;
            """, params=tuple(params))
            if not class_df.empty:
                fig_class = px.bar(
                    class_df, x="Class", y="count", text="count",
                    labels={"count": "Student Registrations", "Class": "Class Grade"},
                    color_discrete_sequence=["#3B82F6"]
                )
                fig_class.update_traces(texttemplate='%{text:,}', textposition='outside')
                fig_class.update_layout(height=380, margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig_class, use_container_width=True)

        # 2. Records by Exam Name
        with c_r1_2:
            st.subheader("📝 Records by Exam Name")
            exam_df = execute_query_df(f"""
                SELECT `ExamName`, COUNT(*) as count, SUM(`ExamCount`) as total_exams
                FROM `student_1_to_12`.`students_records`
                WHERE {where_sql} AND `ExamName` IS NOT NULL AND TRIM(`ExamName`) != ''
                GROUP BY `ExamName`
                ORDER BY count DESC;
            """, params=tuple(params))
            if not exam_df.empty:
                fig_exam = px.pie(
                    exam_df, names="ExamName", values="count", hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Bold
                )
                fig_exam.update_traces(textinfo="label+percent", hovertemplate="<b>%{label}</b><br>Records: %{value:,}<br>Share: %{percent}")
                fig_exam.update_layout(height=380, margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig_exam, use_container_width=True)

        c_r2_1, c_r2_2 = st.columns(2)

        # 3. Top Schools
        with c_r2_1:
            st.subheader("🏫 Top 15 Schools by Registrations")
            school_df = execute_query_df(f"""
                SELECT CONCAT(`SchoolCode`, ' - ', COALESCE(`SchoolName`, 'Unknown')) as school_label, COUNT(*) as count
                FROM `student_1_to_12`.`students_records`
                WHERE {where_sql}
                GROUP BY `SchoolCode`, `SchoolName`
                ORDER BY count DESC
                LIMIT 15;
            """, params=tuple(params))
            if not school_df.empty:
                fig_sch = px.bar(
                    school_df.sort_values(by="count", ascending=True),
                    x="count", y="school_label", orientation="h",
                    text="count",
                    labels={"count": "Registrations", "school_label": "School"},
                    color_discrete_sequence=["#10B981"]
                )
                fig_sch.update_traces(texttemplate='%{text:,}', textposition='outside')
                fig_sch.update_layout(height=420, margin=dict(t=20, b=20, l=20, r=20), yaxis_title="")
                st.plotly_chart(fig_sch, use_container_width=True)

        # 4. Records by State
        with c_r2_2:
            st.subheader("📍 Records by State (Top 15)")
            state_df = execute_query_df(f"""
                SELECT COALESCE(NULLIF(TRIM(`State`), ''), 'Unspecified') as state_name, COUNT(*) as count
                FROM `student_1_to_12`.`students_records`
                WHERE {where_sql}
                GROUP BY state_name
                ORDER BY count DESC
                LIMIT 15;
            """, params=tuple(params))
            if not state_df.empty:
                fig_st = px.bar(
                    state_df, x="state_name", y="count", text="count",
                    labels={"count": "Registrations", "state_name": "State"},
                    color_discrete_sequence=["#8B5CF6"]
                )
                fig_st.update_traces(texttemplate='%{text:,}', textposition='outside')
                fig_st.update_layout(height=420, margin=dict(t=20, b=20, l=20, r=20), xaxis_tickangle=-45)
                st.plotly_chart(fig_st, use_container_width=True)

        # 5. Timeline & Order Status
        c_r3_1, c_r3_2 = st.columns([3, 2])
        with c_r3_1:
            st.subheader("📈 Registration Trends Over Time (`OrderCreated`)")
            trend_df = execute_query_df(f"""
                SELECT DATE(OrderCreated) as order_date, COUNT(*) as daily_count
                FROM `student_1_to_12`.`students_records`
                WHERE {where_sql} AND OrderCreated IS NOT NULL
                GROUP BY DATE(OrderCreated)
                ORDER BY order_date;
            """, params=tuple(params))
            if not trend_df.empty:
                fig_trend = px.line(
                    trend_df, x="order_date", y="daily_count",
                    labels={"daily_count": "Orders Created", "order_date": "Date"},
                    color_discrete_sequence=["#2563EB"]
                )
                fig_trend.update_layout(height=350, margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig_trend, use_container_width=True)

        with c_r3_2:
            st.subheader("📦 Order Status Distribution")
            status_df = execute_query_df(f"""
                SELECT COALESCE(NULLIF(TRIM(`OrderStatus`), ''), 'Not Specified / Draft') as status_clean, COUNT(*) as count
                FROM `student_1_to_12`.`students_records`
                WHERE {where_sql}
                GROUP BY status_clean
                ORDER BY count DESC;
            """, params=tuple(params))
            if not status_df.empty:
                fig_status = px.pie(
                    status_df, names="status_clean", values="count",
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_status.update_layout(height=350, margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig_status, use_container_width=True)

        # Data Quality & Missing Values
        st.markdown('<div class="section-header">🔍 Data Quality & Completeness Audit</div>', unsafe_allow_html=True)
        quality_df = execute_query_df(f"""
            SELECT 
                COUNT(CASE WHEN `StudentName` IS NULL OR TRIM(`StudentName`) = '' THEN 1 END) as missing_student_name,
                COUNT(CASE WHEN `SchoolCode` IS NULL OR TRIM(`SchoolCode`) = '' THEN 1 END) as missing_school_code,
                COUNT(CASE WHEN `SchoolName` IS NULL OR TRIM(`SchoolName`) = '' THEN 1 END) as missing_school_name,
                COUNT(CASE WHEN `Class` IS NULL OR TRIM(`Class`) = '' THEN 1 END) as missing_class,
                COUNT(CASE WHEN `ExamName` IS NULL OR TRIM(`ExamName`) = '' THEN 1 END) as missing_exam_name,
                COUNT(CASE WHEN `PhoneNo` IS NULL OR TRIM(`PhoneNo`) = '' THEN 1 END) as missing_phone,
                COUNT(CASE WHEN `State` IS NULL OR TRIM(`State`) = '' THEN 1 END) as missing_state,
                COUNT(CASE WHEN `OrderStatus` IS NULL OR TRIM(`OrderStatus`) = '' THEN 1 END) as missing_order_status
            FROM `student_1_to_12`.`students_records`
            WHERE {where_sql};
        """, params=tuple(params))

        if not quality_df.empty:
            q_cols = quality_df.columns
            q_metrics = []
            for col_name in q_cols:
                clean_name = col_name.replace("missing_", "").replace("_", " ").title()
                missing_cnt = int(quality_df[col_name].iloc[0])
                complete_pct = ((tot_rec - missing_cnt) / tot_rec * 100) if tot_rec > 0 else 100.0
                q_metrics.append({
                    "Field": clean_name,
                    "Missing / NULL Count": fmt_num(missing_cnt),
                    "Completeness %": f"{complete_pct:.2f}%",
                    "Status": "✅ Complete" if missing_cnt == 0 else ("⚠️ Fair" if complete_pct >= 90 else "❌ High Nulls")
                })
            st.dataframe(pd.DataFrame(q_metrics), hide_index=True, use_container_width=True)

        # Filtered Data Sample Preview & Export
        st.markdown('<div class="section-header">📄 Filtered Records Preview & Export</div>', unsafe_allow_html=True)
        preview_limit = st.slider("Preview Records Limit:", min_value=10, max_value=500, value=50, step=10)
        sample_df = execute_query_df(f"""
            SELECT * FROM `student_1_to_12`.`students_records`
            WHERE {where_sql}
            ORDER BY id DESC
            LIMIT {int(preview_limit)};
        """, params=tuple(params))
        st.dataframe(sample_df, hide_index=True, use_container_width=True)

        csv_data = sample_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label=f"⬇️ Download Current Filtered Sample ({len(sample_df)} Rows as CSV)",
            data=csv_data,
            file_name=f"student_records_filtered_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

# ==============================================================================
# PAGE 3: SCHOOL ANALYTICS DASHBOARD
# ==============================================================================
elif current_page == "🏫 School Analytics":
    st.title("🏫 Multi-Table School Analytics")
    st.markdown("Comprehensive analysis across school tables: `ors_school`, `ors_school_8000`, `ors_mapping`, `school_ghazibad`, `school_contact`, and `ocr_table`.")

    school_tables = [
        "row_data.ors_school",
        "row_data.ors_school_8000",
        "row_data.ors_mapping",
        "row_data.school_ghazibad",
        "row_data.school_contact",
        "row_data.ocr_table"
    ]
    present_school_tables = [t for t in school_tables if t in metadata["table_meta"]]

    school_tabs = st.tabs(["📊 School Tables Overview", "🗺️ Geographic Distributions", "🔗 Cross-Table Code Reconciliation", "🔎 School Directory Search"])

    # TAB 1: OVERVIEW & COMPARISON
    with school_tabs[0]:
        st.subheader("📋 School Table Metrics Comparison")
        school_metrics = []
        for t_name in present_school_tables:
            db, tbl = t_name.split(".")
            cols = [c["COLUMN_NAME"] for c in metadata["table_meta"][t_name]["columns"]]
            
            # Detect school code column
            code_col = next((c for c in cols if any(k in c.lower() for k in ["school_code", "schoolcode"])), None)
            name_col = next((c for c in cols if any(k in c.lower() for k in ["school_name", "schoolname"])), None)
            email_col = next((c for c in cols if "email" in c.lower()), None)
            phone_col = next((c for c in cols if any(k in c.lower() for k in ["phone", "mobile", "cell", "number"])), None)

            # Build query
            q_parts = ["COUNT(*) as total_rows"]
            if code_col:
                q_parts.append(f"COUNT(DISTINCT {safe_ident(code_col)}) as unique_codes")
                q_parts.append(f"COUNT(CASE WHEN {safe_ident(code_col)} IS NULL OR TRIM({safe_ident(code_col)}) = '' THEN 1 END) as missing_codes")
            else:
                q_parts.append("0 as unique_codes, 0 as missing_codes")

            if name_col:
                q_parts.append(f"COUNT(DISTINCT {safe_ident(name_col)}) as unique_names")
                q_parts.append(f"COUNT(CASE WHEN {safe_ident(name_col)} IS NULL OR TRIM({safe_ident(name_col)}) = '' THEN 1 END) as missing_names")
            else:
                q_parts.append("0 as unique_names, 0 as missing_names")

            if email_col:
                q_parts.append(f"COUNT(CASE WHEN {safe_ident(email_col)} IS NOT NULL AND TRIM({safe_ident(email_col)}) != '' THEN 1 END) as with_email")
            else:
                q_parts.append("0 as with_email")

            if phone_col:
                q_parts.append(f"COUNT(CASE WHEN {safe_ident(phone_col)} IS NOT NULL AND TRIM({safe_ident(phone_col)}) != '' THEN 1 END) as with_phone")
            else:
                q_parts.append("0 as with_phone")

            res = execute_readonly_query(f"SELECT {', '.join(q_parts)} FROM {safe_ident(db)}.{safe_ident(tbl)};")
            if res:
                r = res[0]
                tot = r["total_rows"]
                school_metrics.append({
                    "Table": t_name,
                    "Total Records": fmt_num(tot),
                    "Unique Codes": fmt_num(r["unique_codes"]) if code_col else "N/A",
                    "Missing Codes": fmt_num(r["missing_codes"]) if code_col else "N/A",
                    "Unique Names": fmt_num(r["unique_names"]) if name_col else "N/A",
                    "Missing Names": fmt_num(r["missing_names"]) if name_col else "N/A",
                    "Has Email": fmt_num(r["with_email"]) if email_col else "N/A",
                    "Has Phone": fmt_num(r["with_phone"]) if phone_col else "N/A"
                })

        st.dataframe(pd.DataFrame(school_metrics), hide_index=True, use_container_width=True)

        # Bar chart comparing school records
        sch_chart_df = pd.DataFrame([
            {"Table": m["Table"], "Records": int(m["Total Records"].replace(",", ""))}
            for m in school_metrics
        ])
        fig_sch_comp = px.bar(
            sch_chart_df, x="Table", y="Records", text="Records",
            color_discrete_sequence=["#10B981"]
        )
        fig_sch_comp.update_traces(texttemplate='%{text:,}', textposition='outside')
        fig_sch_comp.update_layout(height=350, margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig_sch_comp, use_container_width=True)

    # TAB 2: GEOGRAPHIC DISTRIBUTIONS
    with school_tabs[1]:
        st.subheader("🗺️ Geographic Breakdown (State & City)")
        st.markdown("Analyzing `ors_school` (21,782 records) and `ors_school_8000` (8,041 records).")
        
        geo_c1, geo_c2 = st.columns(2)
        with geo_c1:
            st.markdown("#### `ors_school` States")
            ors_states = execute_query_df("""
                SELECT COALESCE(NULLIF(TRIM(STATE), ''), 'Unspecified') as state_name, COUNT(*) as school_count
                FROM row_data.ors_school
                GROUP BY state_name
                ORDER BY school_count DESC
                LIMIT 15;
            """)
            if not ors_states.empty:
                fig_geo1 = px.bar(ors_states, x="state_name", y="school_count", text="school_count", color_discrete_sequence=["#3B82F6"])
                fig_geo1.update_traces(texttemplate='%{text:,}', textposition='outside')
                fig_geo1.update_layout(height=380, margin=dict(t=20, b=20, l=20, r=20), xaxis_tickangle=-45)
                st.plotly_chart(fig_geo1, use_container_width=True)

        with geo_c2:
            st.markdown("#### `ors_school_8000` Administrative Areas")
            ors8k_states = execute_query_df("""
                SELECT COALESCE(NULLIF(TRIM(ADDRESS_ADMINISTRATIVE_AREA), ''), 'Unspecified') as state_name, COUNT(*) as school_count
                FROM row_data.ors_school_8000
                GROUP BY state_name
                ORDER BY school_count DESC
                LIMIT 15;
            """)
            if not ors8k_states.empty:
                fig_geo2 = px.bar(ors8k_states, x="state_name", y="school_count", text="school_count", color_discrete_sequence=["#8B5CF6"])
                fig_geo2.update_traces(texttemplate='%{text:,}', textposition='outside')
                fig_geo2.update_layout(height=380, margin=dict(t=20, b=20, l=20, r=20), xaxis_tickangle=-45)
                st.plotly_chart(fig_geo2, use_container_width=True)

    # TAB 3: CROSS-TABLE RECONCILIATION
    with school_tabs[2]:
        st.subheader("🔗 School Code Reconciliation Across Tables")
        st.info(
            "**Matching Methodology:** Cross-table analysis maps school identifiers between "
            "`ors_school.SCHOOL_CODE` (Primary school registration portal), `ors_school_8000.FIELD_SCHOOL_CODE` (Extended profiles), "
            "and `students_records.SchoolCode` (Student registrations). Unmatched codes represent schools active in one portal but missing in another."
        )

        recon_sql = """
            SELECT 
                COUNT(DISTINCT a.SCHOOL_CODE) as ors_school_codes,
                COUNT(DISTINCT b.FIELD_SCHOOL_CODE) as ors_8000_codes,
                COUNT(DISTINCT CASE WHEN a.SCHOOL_CODE = b.FIELD_SCHOOL_CODE THEN a.SCHOOL_CODE END) as matched_codes,
                COUNT(DISTINCT CASE WHEN b.FIELD_SCHOOL_CODE IS NULL THEN a.SCHOOL_CODE END) as only_in_ors_school,
                COUNT(DISTINCT CASE WHEN a.SCHOOL_CODE IS NULL THEN b.FIELD_SCHOOL_CODE END) as only_in_ors_8000
            FROM (SELECT DISTINCT SCHOOL_CODE FROM row_data.ors_school WHERE SCHOOL_CODE IS NOT NULL AND TRIM(SCHOOL_CODE) != '') a
            LEFT JOIN (SELECT DISTINCT FIELD_SCHOOL_CODE FROM row_data.ors_school_8000 WHERE FIELD_SCHOOL_CODE IS NOT NULL AND TRIM(FIELD_SCHOOL_CODE) != '') b
                ON a.SCHOOL_CODE = b.FIELD_SCHOOL_CODE;
        """
        recon_res = execute_readonly_query(recon_sql)
        if recon_res:
            rc = recon_res[0]
            r_c1, r_c2, r_c3, r_c4 = st.columns(4)
            with r_c1:
                render_kpi("Codes in ors_school", fmt_num(rc["ors_school_codes"]), "Primary Catalog", "#2563EB")
            with r_c2:
                render_kpi("Matched Codes", fmt_num(rc["matched_codes"]), "Present in both", "#10B981")
            with r_c3:
                render_kpi("Only in ors_school", fmt_num(rc["only_in_ors_school"]), "Missing in 8000 catalog", "#D97706")
            with r_c4:
                render_kpi("Match Rate", fmt_pct(rc["matched_codes"], rc["ors_school_codes"]), "Catalog Coverage", "#7C3AED")

        st.markdown("#### Sample Unmatched School Codes (Present in `ors_school` but Missing in `ors_school_8000`)")
        unmatched_df = execute_query_df("""
            SELECT a.SCHOOL_CODE, a.SCHOOL_NAME, a.CITY, a.STATE
            FROM row_data.ors_school a
            LEFT JOIN row_data.ors_school_8000 b ON a.SCHOOL_CODE = b.FIELD_SCHOOL_CODE
            WHERE b.FIELD_SCHOOL_CODE IS NULL AND a.SCHOOL_CODE IS NOT NULL
            LIMIT 20;
        """)
        st.dataframe(unmatched_df, hide_index=True, use_container_width=True)

    # TAB 4: DIRECTORY SEARCH
    with school_tabs[3]:
        st.subheader("🔎 Universal School Directory Search")
        search_kw = st.text_input("Enter School Name, Code, or City to search across `ors_school`:", value="")
        if search_kw.strip():
            found_schools = execute_query_df("""
                SELECT 
                    SCHOOL_CODE as `School Code`,
                    SCHOOL_NAME as `School Name`,
                    CITY as `City`,
                    STATE as `State`,
                    PRINCIPAL_NAME as `Principal`,
                    PRINCIPAL_S_EMAIL as `Principal Email`,
                    SCHOOL_CONTACT_NO as `Phone`
                FROM row_data.ors_school
                WHERE SCHOOL_NAME LIKE %s OR SCHOOL_CODE LIKE %s OR CITY LIKE %s
                LIMIT 50;
            """, params=(f"%{search_kw.strip()}%", f"%{search_kw.strip()}%", f"%{search_kw.strip()}%"))
            st.dataframe(found_schools, hide_index=True, use_container_width=True)
            st.caption(f"Showing up to 50 matches for query '{search_kw}'.")

# ==============================================================================
# PAGE 4: MARKETING AND CONTACT ANALYTICS
# ==============================================================================
elif current_page == "📈 Marketing & Contact Analytics":
    st.title("📈 Marketing & Contact Analytics")
    st.markdown("Contact quality, deduplication metrics, and email classification across `markeeting_data`, `unsubdata`, `school_contact`, and `unsubscibe_150k`.")

    st.warning("🔒 **Compliance Notice:** This dashboard provides read-only analytical metrics for data hygiene and bounce reduction. It strictly does not send emails, initiate calls, or export campaign lists.")

    mkt_tabs = st.tabs(["📊 Marketing Contact Health", "🛡️ Unsubscribe & Bounce Deliverability", "📋 Top Repeated Contacts"])

    # TAB 1: MARKETING HEALTH
    with mkt_tabs[0]:
        st.subheader("📞 Contact Information Completeness")
        
        target_mkt_tbl = st.selectbox(
            "Select Table for Contact Analysis:",
            options=["row_data.markeeting_data", "row_data.unsubdata", "row_data.school_contact"]
        )
        
        if target_mkt_tbl == "row_data.school_contact":
            sc_res = execute_readonly_query("""
                SELECT 
                    COUNT(*) as total_rows,
                    COUNT(DISTINCT `NUMBER`) as unique_numbers,
                    COUNT(CASE WHEN `NUMBER` IS NULL OR TRIM(`NUMBER`) = '' THEN 1 END) as missing_numbers
                FROM row_data.school_contact;
            """)
            if sc_res:
                r = sc_res[0]
                col1, col2, col3 = st.columns(3)
                with col1:
                    render_kpi("Total Phone Records", fmt_num(r["total_rows"]), "school_contact", "#2563EB")
                with col2:
                    render_kpi("Unique Phone Numbers", fmt_num(r["unique_numbers"]), "Distinct phones", "#10B981")
                with col3:
                    render_kpi("Duplicates / Repeats", fmt_num(r["total_rows"] - r["unique_numbers"]), "Repeat contacts", "#D97706")
        else:
            m_res = execute_readonly_query(f"""
                SELECT 
                    COUNT(*) as total_rows,
                    COUNT(CASE WHEN `CONTACT_EMAIL` IS NOT NULL AND TRIM(`CONTACT_EMAIL`) != '' THEN 1 END) as non_empty_emails,
                    COUNT(DISTINCT CASE WHEN `CONTACT_EMAIL` IS NOT NULL AND TRIM(`CONTACT_EMAIL`) != '' THEN LOWER(TRIM(`CONTACT_EMAIL`)) END) as unique_emails,
                    COUNT(CASE WHEN `PHONE` IS NOT NULL AND TRIM(`PHONE`) != '' THEN 1 END) as non_empty_phones,
                    COUNT(DISTINCT CASE WHEN `PHONE` IS NOT NULL AND TRIM(`PHONE`) != '' THEN TRIM(`PHONE`) END) as unique_phones,
                    COUNT(CASE WHEN (`CONTACT_EMAIL` IS NULL OR TRIM(`CONTACT_EMAIL`) = '') AND (`PHONE` IS NULL OR TRIM(`PHONE`) = '') THEN 1 END) as missing_both
                FROM {target_mkt_tbl};
            """)
            if m_res:
                r = m_res[0]
                tot = r["total_rows"]
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    render_kpi("Total Records", fmt_num(tot), target_mkt_tbl, "#2563EB")
                with col2:
                    render_kpi("Unique Emails", fmt_num(r["unique_emails"]), f"Available: {fmt_num(r['non_empty_emails'])}", "#10B981")
                with col3:
                    render_kpi("Unique Phones", fmt_num(r["unique_phones"]), f"Available: {fmt_num(r['non_empty_phones'])}", "#7C3AED")
                with col4:
                    render_kpi("Missing Both Contacts", fmt_num(r["missing_both"]), fmt_pct(r["missing_both"], tot), "#DC2626")

            # Account type breakdown
            st.markdown(f"#### Account Types in `{target_mkt_tbl}`")
            acc_df = execute_query_df(f"""
                SELECT COALESCE(NULLIF(TRIM(ACCOUNT_TYPE_ZOHO_CRM), ''), 'Unspecified') as acc_type, COUNT(*) as count
                FROM {target_mkt_tbl}
                GROUP BY acc_type
                ORDER BY count DESC
                LIMIT 10;
            """)
            if not acc_df.empty:
                fig_acc = px.bar(acc_df, x="acc_type", y="count", text="count", color_discrete_sequence=["#3B82F6"])
                fig_acc.update_traces(texttemplate='%{text:,}', textposition='outside')
                fig_acc.update_layout(height=350, margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig_acc, use_container_width=True)

    # TAB 2: UNSUBSCRIBE & CLASSIFICATION
    with mkt_tabs[1]:
        st.subheader("🛡️ Email Verification & Classification (`unsubscibe_150k`)")
        st.markdown("Auditing 659,574 email verification and deliverability records.")

        u_c1, u_c2 = st.columns(2)
        with u_c1:
            st.markdown("#### Email Deliverability Classification")
            class_df = execute_query_df("""
                SELECT CLASSIFICATION, COUNT(*) as count
                FROM row_data.unsubscibe_150k
                GROUP BY CLASSIFICATION
                ORDER BY count DESC;
            """)
            if not class_df.empty:
                fig_class = px.pie(
                    class_df, names="CLASSIFICATION", values="count", hole=0.45,
                    color="CLASSIFICATION",
                    color_discrete_map={
                        "Deliverable": "#10B981",
                        "Risky": "#F59E0B",
                        "Undeliverable": "#EF4444",
                        "Unknown": "#6B7280"
                    }
                )
                fig_class.update_traces(textinfo="label+percent", hovertemplate="<b>%{label}</b><br>Records: %{value:,}<br>Share: %{percent}")
                fig_class.update_layout(height=380, margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig_class, use_container_width=True)

        with u_c2:
            st.markdown("#### Delivery Status Details")
            status_df = execute_query_df("""
                SELECT STATUS, COUNT(*) as count
                FROM row_data.unsubscibe_150k
                GROUP BY STATUS
                ORDER BY count DESC
                LIMIT 10;
            """)
            if not status_df.empty:
                fig_st = px.bar(
                    status_df, x="count", y="STATUS", orientation="h", text="count",
                    color_discrete_sequence=["#6366F1"]
                )
                fig_st.update_traces(texttemplate='%{text:,}', textposition='outside')
                fig_st.update_layout(height=380, margin=dict(t=20, b=20, l=20, r=20), yaxis_title="")
                st.plotly_chart(fig_st, use_container_width=True)

    # TAB 3: TOP REPEATED CONTACTS
    with mkt_tabs[2]:
        st.subheader("🔁 Top Repeated Emails & Phone Numbers")
        
        rep_c1, rep_c2 = st.columns(2)
        with rep_c1:
            st.markdown("#### Most Repeated Emails in `markeeting_data`")
            top_emails = execute_query_df("""
                SELECT LOWER(TRIM(CONTACT_EMAIL)) as `Email Address`, COUNT(*) as `Occurrences`
                FROM row_data.markeeting_data
                WHERE CONTACT_EMAIL IS NOT NULL AND TRIM(CONTACT_EMAIL) != ''
                GROUP BY LOWER(TRIM(CONTACT_EMAIL))
                HAVING COUNT(*) > 1
                ORDER BY `Occurrences` DESC
                LIMIT 15;
            """)
            if not top_emails.empty:
                st.dataframe(top_emails, hide_index=True, use_container_width=True)
            else:
                st.info("No repeated emails detected in `markeeting_data` (all non-empty emails are unique).")

        with rep_c2:
            st.markdown("#### Most Repeated Phone Numbers in `school_contact`")
            top_phones = execute_query_df("""
                SELECT `NUMBER` as `Phone Number`, COUNT(*) as `Occurrences`
                FROM row_data.school_contact
                WHERE `NUMBER` IS NOT NULL AND TRIM(`NUMBER`) != ''
                GROUP BY `NUMBER`
                HAVING COUNT(*) > 1
                ORDER BY `Occurrences` DESC
                LIMIT 15;
            """)
            if not top_phones.empty:
                st.dataframe(top_phones, hide_index=True, use_container_width=True)
            else:
                st.info("No repeated phone numbers found.")

# ==============================================================================
# PAGE 5: OCR AND REGISTRATION ANALYTICS
# ==============================================================================
elif current_page == "📝 OCR & Registration Analytics":
    st.title("📝 OCR & Sheet Registration Analytics")
    st.markdown("Deep-dive inspection of scanned student registration sheets in `row_data.ocr_table` (339,620 rows).")

    if "row_data.ocr_table" not in metadata["table_meta"]:
        st.warning("⚠️ Table `row_data.ocr_table` was not found.")
    else:
        # Load high-level OCR metrics
        ocr_kpi = execute_readonly_query("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT SCHOOLCODE) as unique_schools,
                COUNT(DISTINCT NAME) as unique_students,
                COUNT(CASE WHEN MOBILENO IS NULL OR TRIM(MOBILENO) = '' OR MOBILENO = 'NULL' THEN 1 END) as missing_mobiles,
                COUNT(CASE WHEN ACTIVESTATUS = '1' THEN 1 END) as active_records,
                COUNT(CASE WHEN ACTIVESTATUS = '0' THEN 1 END) as inactive_records
            FROM row_data.ocr_table;
        """)
        
        if ocr_kpi:
            ok = ocr_kpi[0]
            tot = ok["total_records"]
            o_c1, o_c2, o_c3, o_c4 = st.columns(4)
            with o_c1:
                render_kpi("Total OCR Records", fmt_num(tot), "Scanned sheets", "#2563EB")
            with o_c2:
                render_kpi("Unique School Codes", fmt_num(ok["unique_schools"]), "Schools participating", "#7C3AED")
            with o_c3:
                render_kpi("Active Status (1)", fmt_num(ok["active_records"]), fmt_pct(ok["active_records"], tot), "#10B981")
            with o_c4:
                render_kpi("Missing Mobiles", fmt_num(ok["missing_mobiles"]), fmt_pct(ok["missing_mobiles"], tot), "#EF4444")

        st.markdown("---")

        # 1. Exam Appearances Breakdown
        st.subheader("🎯 Student Exam Registrations Across OCR Flags")
        st.caption("Each column (ICO, ICSO, IEO, IGKO, IHO, IMO, ISO, ISSO) marks subject participation ('1' = Enrolled).")
        
        exam_flags_sql = """
            SELECT 
                SUM(CASE WHEN ICO = '1' THEN 1 ELSE 0 END) as ICO,
                SUM(CASE WHEN ICSO = '1' THEN 1 ELSE 0 END) as ICSO,
                SUM(CASE WHEN IEO = '1' THEN 1 ELSE 0 END) as IEO,
                SUM(CASE WHEN IGKO = '1' THEN 1 ELSE 0 END) as IGKO,
                SUM(CASE WHEN IHO = '1' THEN 1 ELSE 0 END) as IHO,
                SUM(CASE WHEN IMO = '1' THEN 1 ELSE 0 END) as IMO,
                SUM(CASE WHEN ISO = '1' THEN 1 ELSE 0 END) as ISO,
                SUM(CASE WHEN ISSO = '1' THEN 1 ELSE 0 END) as ISSO
            FROM row_data.ocr_table;
        """
        flags_res = execute_readonly_query(exam_flags_sql)
        if flags_res:
            flag_row = flags_res[0]
            flag_list = [{"Exam": k, "Registrations": int(v or 0)} for k, v in flag_row.items()]
            flag_df = pd.DataFrame(flag_list).sort_values(by="Registrations", ascending=False)
            
            fig_flags = px.bar(
                flag_df, x="Exam", y="Registrations", text="Registrations",
                labels={"Registrations": "Enrolled Candidates", "Exam": "Olympiad Exam"},
                color="Exam",
                color_discrete_sequence=px.colors.qualitative.Prism
            )
            fig_flags.update_traces(texttemplate='%{text:,}', textposition='outside')
            fig_flags.update_layout(height=380, margin=dict(t=20, b=20, l=20, r=20), showlegend=False)
            st.plotly_chart(fig_flags, use_container_width=True)

        # 2. Class Distribution and Batches
        o_r2_1, o_r2_2 = st.columns(2)
        with o_r2_1:
            st.subheader("📚 Class-wise Distribution")
            class_ocr_df = execute_query_df("""
                SELECT SCHOOLCLASS as `Class`, COUNT(*) as count
                FROM row_data.ocr_table
                WHERE SCHOOLCLASS IS NOT NULL AND TRIM(SCHOOLCLASS) != ''
                GROUP BY SCHOOLCLASS
                ORDER BY LENGTH(SCHOOLCLASS), SCHOOLCLASS;
            """)
            if not class_ocr_df.empty:
                fig_c_ocr = px.bar(
                    class_ocr_df, x="Class", y="count", text="count",
                    color_discrete_sequence=["#3B82F6"]
                )
                fig_c_ocr.update_traces(texttemplate='%{text:,}', textposition='outside')
                fig_c_ocr.update_layout(height=360, margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig_c_ocr, use_container_width=True)

        with o_r2_2:
            st.subheader("📦 Top OCR Batches (`BATCHID`)")
            batch_ocr_df = execute_query_df("""
                SELECT BATCHID as `Batch ID`, COUNT(*) as `Sheets Processed`
                FROM row_data.ocr_table
                WHERE BATCHID IS NOT NULL AND TRIM(BATCHID) != ''
                GROUP BY BATCHID
                ORDER BY `Sheets Processed` DESC
                LIMIT 10;
            """)
            if not batch_ocr_df.empty:
                fig_b_ocr = px.bar(
                    batch_ocr_df, x="Sheets Processed", y="Batch ID", orientation="h", text="Sheets Processed",
                    color_discrete_sequence=["#10B981"]
                )
                fig_b_ocr.update_traces(texttemplate='%{text:,}', textposition='outside')
                fig_b_ocr.update_layout(height=360, margin=dict(t=20, b=20, l=20, r=20), yaxis_title="")
                st.plotly_chart(fig_b_ocr, use_container_width=True)

        # 3. Repeated Mobile Numbers
        st.subheader("📱 Repeated Mobile Numbers in OCR Data")
        rep_mobiles = execute_query_df("""
            SELECT MOBILENO as `Mobile Number`, COUNT(*) as `Appearances`
            FROM row_data.ocr_table
            WHERE MOBILENO IS NOT NULL AND TRIM(MOBILENO) != '' AND MOBILENO != 'NULL'
            GROUP BY MOBILENO
            HAVING COUNT(*) > 1
            ORDER BY `Appearances` DESC
            LIMIT 15;
        """)
        if not rep_mobiles.empty:
            st.dataframe(rep_mobiles, hide_index=True, use_container_width=True)

# ==============================================================================
# PAGE 6: DUPLICATE ANALYSIS ENGINE
# ==============================================================================
elif current_page == "🔍 Duplicate Analysis Engine":
    st.title("🔍 Comprehensive Duplicate Analysis Engine")
    st.markdown("Perform high-performance, SQL-aggregated deduplication and business record redundancy checks.")

    st.error("🛑 **Safety Notice:** This engine operates in **strict read-only audit mode**. Duplicate records are flagged and counted for analysis only. No records will ever be modified, merged, or deleted.")

    dup_type = st.radio(
        "Select Duplicate Check Mode:",
        [
            "1. Duplicate Email Addresses",
            "2. Duplicate Phone / Mobile Numbers",
            "3. Duplicate School Codes",
            "4. Duplicate School Names",
            "5. Duplicate Student / Order Identifiers",
            "6. Exact Composite Business Record Duplicates (Excluding Technical IDs)"
        ],
        horizontal=False
    )

    st.markdown("---")

    # Helper function to run duplicate aggregations safely
    def run_dedup_query(db: str, tbl: str, expr: str, label: str):
        st.info(f"Target: `{db}.{tbl}` | Expression: `{expr}`")
        if st.button("⚡ Execute Duplicate Scan", type="primary"):
            with st.spinner("Executing SQL aggregation and duplicate group calculation..."):
                t0 = time.time()
                # 1. Total duplicate groups and affected rows
                stat_sql = f"""
                    SELECT 
                        COUNT(*) as total_duplicate_groups,
                        COALESCE(SUM(cnt), 0) as total_affected_rows,
                        COALESCE(SUM(cnt - 1), 0) as extra_redundant_rows
                    FROM (
                        SELECT {expr} as val, COUNT(*) as cnt
                        FROM {safe_ident(db)}.{safe_ident(tbl)}
                        WHERE {expr} IS NOT NULL AND TRIM({expr}) != '' AND {expr} != 'NULL'
                        GROUP BY {expr}
                        HAVING cnt > 1
                    ) grp;
                """
                stat_res = execute_readonly_query(stat_sql)
                
                # 2. Top duplicate groups
                top_sql = f"""
                    SELECT 
                        {expr} as `{label}`,
                        COUNT(*) as `Occurrences`
                    FROM {safe_ident(db)}.{safe_ident(tbl)}
                    WHERE {expr} IS NOT NULL AND TRIM({expr}) != '' AND {expr} != 'NULL'
                    GROUP BY {expr}
                    HAVING `Occurrences` > 1
                    ORDER BY `Occurrences` DESC
                    LIMIT 50;
                """
                top_df = execute_query_df(top_sql)
                elapsed = time.time() - t0

                if stat_res:
                    s = stat_res[0]
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        render_kpi("Duplicate Groups", fmt_num(s["total_duplicate_groups"]), "Distinct repeated values", "#EF4444")
                    with c2:
                        render_kpi("Total Affected Rows", fmt_num(s["total_affected_rows"]), "All rows with duplicate value", "#D97706")
                    with c3:
                        render_kpi("Extra Redundant Rows", fmt_num(s["extra_redundant_rows"]), "Rows beyond 1st instance", "#B91C1C")
                    with c4:
                        render_kpi("Scan Duration", f"{elapsed:.2f}s", "Optimized SQL execution", "#4B5563")

                st.markdown("#### Top 50 Duplicate Groups")
                if not top_df.empty:
                    st.dataframe(top_df, hide_index=True, use_container_width=True)
                else:
                    st.success("🎉 No duplicate entries detected! Every value is completely unique.")

    if dup_type == "1. Duplicate Email Addresses":
        target = st.selectbox("Select Target Table:", ["row_data.markeeting_data", "row_data.unsubdata", "row_data.unsubscibe_150k", "row_data.ors_school"])
        db, tbl = target.split(".")
        email_col = "EMAILADDRESS" if tbl == "unsubscibe_150k" else ("SCHOOL_EMAIL" if tbl == "ors_school" else "CONTACT_EMAIL")
        run_dedup_query(db, tbl, f"LOWER(TRIM({safe_ident(email_col)}))", "Normalized Email Address")

    elif dup_type == "2. Duplicate Phone / Mobile Numbers":
        target = st.selectbox("Select Target Table:", ["student_1_to_12.students_records", "row_data.ocr_table", "row_data.school_contact", "row_data.markeeting_data"])
        db, tbl = target.split(".")
        phone_col = "PhoneNo" if tbl == "students_records" else ("MOBILENO" if tbl == "ocr_table" else ("NUMBER" if tbl == "school_contact" else "PHONE"))
        run_dedup_query(db, tbl, f"TRIM({safe_ident(phone_col)})", "Phone Number")

    elif dup_type == "3. Duplicate School Codes":
        target = st.selectbox("Select Target Table:", ["student_1_to_12.students_records", "row_data.ors_school", "row_data.ors_school_8000", "row_data.ocr_table"])
        db, tbl = target.split(".")
        code_col = "SchoolCode" if tbl == "students_records" else ("FIELD_SCHOOL_CODE" if tbl == "ors_school_8000" else ("SCHOOLCODE" if tbl == "ocr_table" else "SCHOOL_CODE"))
        run_dedup_query(db, tbl, f"TRIM({safe_ident(code_col)})", "School Code")

    elif dup_type == "4. Duplicate School Names":
        target = st.selectbox("Select Target Table:", ["student_1_to_12.students_records", "row_data.ors_school", "row_data.ors_mapping", "row_data.school_ghazibad"])
        db, tbl = target.split(".")
        name_col = "SchoolName" if tbl in ["students_records", "ors_mapping", "school_ghazibad"] else "SCHOOL_NAME"
        run_dedup_query(db, tbl, f"UPPER(TRIM({safe_ident(name_col)}))", "School Name")

    elif dup_type == "5. Duplicate Student / Order Identifiers":
        target = st.selectbox("Select Target Table:", ["student_1_to_12.students_records", "row_data.ocr_table"])
        db, tbl = target.split(".")
        id_col = "Order_Number" if tbl == "students_records" else "SERIALNO"
        run_dedup_query(db, tbl, f"TRIM({safe_ident(id_col)})", "Order / Serial Identifier")

    elif dup_type == "6. Exact Composite Business Record Duplicates (Excluding Technical IDs)":
        st.markdown("#### Configurable Composite Record Deduplication")
        st.write("Detect full-row business duplicates while ignoring technical surrogate primary keys and import filenames.")
        
        target = st.selectbox("Select Table for Composite Deduplication:", list(metadata["table_meta"].keys()))
        db, tbl = target.split(".")
        
        all_cols = [c["COLUMN_NAME"] for c in metadata["table_meta"][target]["columns"]]
        default_exclusions = [c for c in all_cols if c.lower() in ["id", "import_id", "import_file"]]
        
        excluded = st.multiselect(
            "Configurable Technical Columns to Exclude from Comparison:",
            options=all_cols,
            default=default_exclusions
        )
        
        business_cols = [c for c in all_cols if c not in excluded]
        st.caption(f"Comparing **{len(business_cols)}** business columns: `{', '.join(business_cols[:10])}` {'...' if len(business_cols)>10 else ''}")
        
        if st.button("⚡ Run Full Composite Duplicate Audit", type="primary"):
            if not business_cols:
                st.error("Please select at least one column to compare.")
            else:
                with st.spinner("Running composite group scan..."):
                    col_group_sql = ", ".join([safe_ident(c) for c in business_cols])
                    composite_sql = f"""
                        SELECT {col_group_sql}, COUNT(*) as `Occurrences`
                        FROM {safe_ident(db)}.{safe_ident(tbl)}
                        GROUP BY {col_group_sql}
                        HAVING `Occurrences` > 1
                        ORDER BY `Occurrences` DESC
                        LIMIT 50;
                    """
                    t0 = time.time()
                    dup_df = execute_query_df(composite_sql)
                    elapsed = time.time() - t0
                    
                    st.success(f"Audit completed in {elapsed:.2f} seconds.")
                    if not dup_df.empty:
                        st.warning(f"⚠️ Found {len(dup_df)} duplicate business record groups in top 50 sample.")
                        st.dataframe(dup_df, hide_index=True, use_container_width=True)
                    else:
                        st.success("🎉 No exact composite duplicates found across selected business attributes!")

# ==============================================================================
# PAGE 7: DEDICATED TABLE SECTIONS
# ==============================================================================
elif current_page == "🗂️ Dedicated Table Sections":
    st.title("🗂️ Dedicated Table Sections")
    st.markdown("A dedicated analytical section for every discovered table in the connected MySQL databases.")

    all_table_names = list(metadata["table_meta"].keys())
    if not all_table_names:
        st.warning("No tables discovered.")
    else:
        selected_full_table = st.selectbox(
            "Select Table Section to Inspect:",
            options=all_table_names,
            index=0
        )
        
        meta = metadata["table_meta"][selected_full_table]
        db = meta["db_name"]
        tbl = meta["table_name"]
        total_rows = meta["row_count"]
        col_count = meta["col_count"]

        # Table Header & KPIs
        st.markdown(f"### Section: `{selected_full_table}`")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_kpi("Database", db, "Schema", "#2563EB")
        with c2:
            render_kpi("Table Name", tbl, "MySQL Table", "#7C3AED")
        with c3:
            render_kpi("Total Records", fmt_num(total_rows), "Rows in table", "#059669")
        with c4:
            render_kpi("Columns Count", str(col_count), "Attributes", "#D97706")

        # Schema Inspector
        with st.expander("📋 View Column Names and MySQL Data Types", expanded=False):
            col_info_list = [
                {
                    "Ordinal": c["ORDINAL_POSITION"],
                    "Column Name": c["COLUMN_NAME"],
                    "Data Type": c["DATA_TYPE"],
                    "Full Type": c["COLUMN_TYPE"],
                    "Nullable": c["IS_NULLABLE"],
                    "Key": c["COLUMN_KEY"],
                    "Default": c["COLUMN_DEFAULT"]
                }
                for c in meta["columns"]
            ]
            st.dataframe(pd.DataFrame(col_info_list), hide_index=True, use_container_width=True)

        # Missing / Null value analyzer
        with st.expander("🔍 Column Completeness & NULL Value Audit", expanded=False):
            st.write("Calculate NULL or empty string counts across the columns of this table.")
            if st.button("Calculate Missing Values for Table", key=f"null_btn_{selected_full_table}"):
                with st.spinner("Analyzing column nulls..."):
                    null_checks = []
                    cols_to_check = [c["COLUMN_NAME"] for c in meta["columns"][:25]] # check up to 25 columns
                    for c in cols_to_check:
                        null_checks.append(f"COUNT(CASE WHEN {safe_ident(c)} IS NULL OR TRIM({safe_ident(c)}) = '' OR {safe_ident(c)} = 'NULL' THEN 1 END) as {safe_ident(c)}")
                    
                    null_sql = f"SELECT {', '.join(null_checks)} FROM {safe_ident(db)}.{safe_ident(tbl)};"
                    null_res = execute_readonly_query(null_sql)
                    if null_res:
                        null_row = null_res[0]
                        res_list = []
                        for c in cols_to_check:
                            m_cnt = int(null_row.get(c, 0) or 0)
                            comp_pct = ((total_rows - m_cnt) / total_rows * 100) if total_rows > 0 else 100.0
                            res_list.append({
                                "Column": c,
                                "Missing / Empty Rows": fmt_num(m_cnt),
                                "Completeness %": f"{comp_pct:.1f}%",
                                "Quality": "✅ 100%" if m_cnt == 0 else ("⚠️ Fair" if comp_pct > 80 else "❌ High Nulls")
                            })
                        st.dataframe(pd.DataFrame(res_list), hide_index=True, use_container_width=True)

        st.markdown("---")
        st.subheader("🔎 Searchable Data Preview & Pagination")

        # Column Filter
        col_names = [c["COLUMN_NAME"] for c in meta["columns"]]
        f_col1, f_col2, f_col3 = st.columns([2, 1, 2])
        with f_col1:
            filt_col = st.selectbox("Filter by Column:", ["(No Filter)"] + col_names, key=f"fcol_{selected_full_table}")
        with f_col2:
            filt_op = st.selectbox("Operator:", ["=", "LIKE", ">", "<", "IS NULL", "IS NOT NULL"], key=f"fop_{selected_full_table}")
        with f_col3:
            filt_val = st.text_input("Filter Value:", "", key=f"fval_{selected_full_table}")

        # Build filter SQL
        table_where = "1=1"
        table_params = []
        if filt_col != "(No Filter)":
            if filt_op == "=":
                table_where = f"{safe_ident(filt_col)} = %s"
                table_params.append(filt_val)
            elif filt_op == "LIKE":
                table_where = f"{safe_ident(filt_col)} LIKE %s"
                table_params.append(f"%{filt_val}%")
            elif filt_op in [">", "<"]:
                table_where = f"{safe_ident(filt_col)} {filt_op} %s"
                table_params.append(filt_val)
            elif filt_op == "IS NULL":
                table_where = f"({safe_ident(filt_col)} IS NULL OR TRIM({safe_ident(filt_col)}) = '')"
            elif filt_op == "IS NOT NULL":
                table_where = f"({safe_ident(filt_col)} IS NOT NULL AND TRIM({safe_ident(filt_col)}) != '')"

        # Count filtered rows
        f_cnt_res = execute_readonly_query(
            f"SELECT COUNT(*) as cnt FROM {safe_ident(db)}.{safe_ident(tbl)} WHERE {table_where};",
            params=tuple(table_params)
        )
        filtered_count = f_cnt_res[0]["cnt"] if f_cnt_res else total_rows

        st.caption(f"Filtered Records: **{fmt_num(filtered_count)}** of {fmt_num(total_rows)}")

        # Pagination controls
        p_c1, p_c2 = st.columns([1, 3])
        with p_c1:
            page_size = st.selectbox("Rows per page:", [10, 25, 50, 100], index=1, key=f"psize_{selected_full_table}")
        
        total_pages = max(1, (filtered_count + page_size - 1) // page_size)
        with p_c2:
            page_num = st.number_input(f"Page (1 to {total_pages}):", min_value=1, max_value=total_pages, value=1, step=1, key=f"pnum_{selected_full_table}")

        offset = (page_num - 1) * page_size

        preview_sql = f"""
            SELECT * FROM {safe_ident(db)}.{safe_ident(tbl)}
            WHERE {table_where}
            LIMIT {int(page_size)} OFFSET {int(offset)};
        """
        page_df = execute_query_df(preview_sql, params=tuple(table_params))
        st.dataframe(page_df, hide_index=True, use_container_width=True)

        # CSV Export button
        export_limit = st.slider("Export Row Limit (Max):", min_value=100, max_value=10000, value=1000, step=500, key=f"exp_{selected_full_table}")
        if st.button("📥 Generate Filtered CSV Export", key=f"exp_btn_{selected_full_table}"):
            with st.spinner("Extracting data for CSV export..."):
                export_sql = f"""
                    SELECT * FROM {safe_ident(db)}.{safe_ident(tbl)}
                    WHERE {table_where}
                    LIMIT {int(export_limit)};
                """
                export_df = execute_query_df(export_sql, params=tuple(table_params))
                csv_bytes = export_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label=f"⬇️ Download {len(export_df)} Rows as CSV",
                    data=csv_bytes,
                    file_name=f"{db}_{tbl}_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )

# ==============================================================================
# PAGE 8: DYNAMIC TABLE EXPLORER
# ==============================================================================
elif current_page == "🧭 Dynamic Table Explorer":
    st.title("🧭 Dynamic MySQL Table Explorer")
    st.markdown("Browse, filter, and inspect any discovered or newly added MySQL table dynamically.")

    # 1. Database Selector
    sel_db = st.selectbox("Select Database:", options=metadata["databases"])
    
    # Tables in this database
    available_tables = [t["table_name"] for t in metadata["tables"] if t["db_name"] == sel_db]
    if not available_tables:
        st.warning(f"No tables found in database `{sel_db}`.")
    else:
        sel_tbl = st.selectbox("Select Table:", options=available_tables)
        full_key = f"{sel_db}.{sel_tbl}"
        tbl_info = metadata["table_meta"].get(full_key, {})
        
        # 2. Column Search
        cols_list = tbl_info.get("columns", [])
        st.markdown("#### 🔎 Column Schema Inspector")
        col_search = st.text_input("Filter Column Names:", "")
        filtered_cols = [c for c in cols_list if col_search.lower() in c["COLUMN_NAME"].lower()] if col_search else cols_list
        
        col_display_df = pd.DataFrame([
            {
                "Position": c["ORDINAL_POSITION"],
                "Column Name": c["COLUMN_NAME"],
                "Data Type": c["DATA_TYPE"],
                "SQL Type": c["COLUMN_TYPE"],
                "Nullable": c["IS_NULLABLE"],
                "Key": c["COLUMN_KEY"]
            }
            for c in filtered_cols
        ])
        st.dataframe(col_display_df, hide_index=True, use_container_width=True)

        st.markdown("---")
        st.markdown("#### 📋 Data Query & Custom Filter")

        # Dynamic Filter Builder
        col_names = [c["COLUMN_NAME"] for c in cols_list]
        e_c1, e_c2, e_c3, e_c4 = st.columns([2, 1, 2, 1])
        with e_c1:
            q_col = st.selectbox("Choose Filter Column:", ["(None)"] + col_names)
        with e_c2:
            q_op = st.selectbox("Comparison:", ["=", "LIKE", ">", "<", "IS NULL", "IS NOT NULL"])
        with e_c3:
            q_val = st.text_input("Search Term / Value:", "")
        with e_c4:
            q_limit = st.selectbox("Preview Limit:", [25, 50, 100, 250, 500, 1000], index=1)

        where_expr = "1=1"
        q_params = []
        if q_col != "(None)":
            if q_op == "=":
                where_expr = f"{safe_ident(q_col)} = %s"
                q_params.append(q_val)
            elif q_op == "LIKE":
                where_expr = f"{safe_ident(q_col)} LIKE %s"
                q_params.append(f"%{q_val}%")
            elif q_op in [">", "<"]:
                where_expr = f"{safe_ident(q_col)} {q_op} %s"
                q_params.append(q_val)
            elif q_op == "IS NULL":
                where_expr = f"({safe_ident(q_col)} IS NULL OR TRIM({safe_ident(q_col)}) = '')"
            elif q_op == "IS NOT NULL":
                where_expr = f"({safe_ident(q_col)} IS NOT NULL AND TRIM({safe_ident(q_col)}) != '')"

        run_sql = f"""
            SELECT * FROM {safe_ident(sel_db)}.{safe_ident(sel_tbl)}
            WHERE {where_expr}
            LIMIT {int(q_limit)};
        """
        result_df = execute_query_df(run_sql, params=tuple(q_params))
        
        st.write(f"Displaying **{len(result_df)}** rows:")
        st.dataframe(result_df, hide_index=True, use_container_width=True)

        # CSV Download
        csv_bytes = result_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=f"⬇️ Export {len(result_df)} Records as CSV",
            data=csv_bytes,
            file_name=f"{sel_db}_{sel_tbl}_explorer_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
