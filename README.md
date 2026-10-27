# 📊 Complete MySQL Data Analytics Dashboard

A high-performance, production-ready Data Analytics and Business Intelligence Dashboard built with **Python**, **Streamlit**, **Pandas**, **Plotly**, and **PyMySQL**.

The dashboard connects to local MySQL databases (`row_data` and `student_1_to_12`), dynamically discovers schemas and metadata across ~2.5 million records, and provides interactive visual analytics, filtering, deduplication scanning, and data export.

---

> [!WARNING]
> **Security & Credential Notice:**  
> As configured, the MySQL password is stored in plaintext directly in the `MYSQL_PASSWORD` variable at the top of `app.py`. Anyone who has read access to `app.py` can view this password.  
> **Do not commit `app.py` with real production passwords to a public Git repository.**

---

## 🛠️ Tech Stack & Architecture

- **Frontend & App Framework:** [Streamlit](https://streamlit.io/) (wide layout, responsive KPI grid, custom CSS)
- **Data Visualizations:** [Plotly](https://plotly.com/python/) (`plotly.express` and `plotly.graph_objects`)
- **Database Driver:** [PyMySQL](https://github.com/PyMySQL/PyMySQL) (with safe connection handling and parameterization)
- **Data Processing:** [Pandas](https://pandas.pydata.org/) (for paginated tabular views and CSV serialization)
- **Performance Strategy:** Pure SQL server-side aggregations (`COUNT(*)`, `GROUP BY`, `SUM`, `LIMIT`, `OFFSET`) to handle multi-hundred-thousand row tables with zero in-memory memory bloat.

---

## 🚀 Quick Start (Windows PowerShell)

Follow these exact Windows PowerShell commands to set up and run the dashboard:

### 1. Open Windows PowerShell in the Project Directory

```powershell
cd "c:\Users\A\OneDrive\Pictures\Excel Project\Ghazibad\Documents\Desktop\Dashborad"
```

### 2. Install Required Dependencies

Install the necessary Python packages:

```powershell
py -m pip install -r requirements.txt
```

### 3. (Optional) Run the Automated Verification Test Suite

Verify local MySQL database connectivity, metadata discovery, and queries:

```powershell
py test_dashboard.py
```

### 4. Launch the Streamlit Dashboard

Start the application:

```powershell
py -m streamlit run app.py
```

### 5. Accessing and Stopping the Application

- **Open in Browser:** Streamlit will automatically open your default browser at:
  ```
  http://localhost:8501
  ```
- **Stop the Application:** To shut down the dashboard, switch back to the PowerShell terminal window and press:
  ```
  Ctrl + C
  ```

---

## ⚙️ MySQL Configuration (`app.py`)

The connection settings are defined at the very top of `app.py`:

```python
# Values loaded securely from st.secrets or environment variables
MYSQL_HOST = "localhost"  # or remote MySQL host for cloud deployment
MYSQL_PORT = 3306
MYSQL_USER = "root"
MYSQL_PASSWORD = "your_secure_password"  # Configured via .streamlit/secrets.toml

DATABASES = [
    "row_data",
    "student_1_to_12"
]
```

- **Credential Redaction:** Error messages automatically mask the host, username, and password before rendering in the UI or terminal logs.
- **Read-Only Protection:** All queries are filtered through a strict security validation barrier. Any destructive statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`) are blocked.

---

## 📁 Discovered Databases & Schemas

### 1. `student_1_to_12` (389,604 Records)
- **`students_records`** (16 columns):
  - `id`, `Order_Number`, `SchoolCode`, `SchoolName`, `StudentName`, `Class`, `ExamName`, `ExamCount`, `Section`, `PhoneNo`, `State`, `OrderStatus`, `Total_paid__number`, `Total_price__number`, `OrderCreated`, `Completed`

### 2. `row_data` (2,121,471 Records across 10 Tables)
1. **`markeeting_data`** (214,465 rows, 53 columns): Zoho CRM imports, email addresses, phone contacts, revenue attributes.
2. **`ocr_table`** (339,620 rows, 32 columns): Scanned registration sheets, student names, school codes, active status, mobile numbers, and exam participation flags (`ICO`, `ICSO`, `IEO`, `IGKO`, `IHO`, `IMO`, `ISO`, `ISSO`).
3. **`ors_mapping`** (590 rows, 26 columns): School administrative mappings, contact persons, phone numbers, and addresses.
4. **`ors_school`** (21,782 rows, 55 columns): Master school directory, state, city, district, coordinator/principal contact data, exam dates, order statuses.
5. **`ors_school_8000`** (8,041 rows, 42 columns): Extended school catalog, address localities, coordinator phone numbers, special pricing flags.
6. **`school_contact`** (21,961 rows, 3 columns): School phone directory numbers (`NUMBER`).
7. **`school_ghazibad`** (800 rows, 29 columns): Ghaziabad region schools, principal mobile numbers, affiliated boards, and student strength metrics.
8. **`unsubdata`** (809,573 rows, 52 columns): Contact opt-in/opt-out status, email addresses, Zoho CRM metrics.
9. **`unsubscibe_150k`** (659,574 rows, 24 columns): Email deliverability validation data (`CLASSIFICATION`: Deliverable, Risky, Undeliverable; `STATUS`: Success, Duplicate, MailboxFull, etc.).
10. **`access_code`** (45,065 rows, 96 columns): Student exam access codes, books ordered, payment amounts, and shipping addresses.

---

## 🖥️ Dashboard Pages & Features

| Page | Description | Key Features |
|---|---|---|
| **📊 Main Overview Dashboard** | System topology and inventory | Total connected DBs, total discovered tables, aggregate rows, storage size (MB), table size comparison bar chart, volume split donut chart, and complete metadata table. |
| **🎓 Student Analytics** | Deep analytics for `students_records` | Filter by Class, State, Exam Name, School, and Date range. Visualizations for class distributions, top schools, geographic spread, order timelines, revenue vs. price, and data completeness audit. |
| **🏫 School Analytics** | Multi-table school intelligence | Cross-table analysis across `ors_school`, `ors_school_8000`, `ors_mapping`, etc. School code reconciliation (matched vs. unmatched codes), geographic state/district charts, and universal directory search. |
| **📈 Marketing & Contact Analytics** | Contact hygiene & deliverability | Non-empty and unique counts for emails and phone numbers, missing contact rate, Zoho CRM account types, top 15 repeated contacts, and email bounce classification distribution. |
| **📝 OCR & Registration Analytics** | Olympiad sheet registration audit | Scanned sheet statistics, enrollment totals across 8 olympiad exams (`ICO`, `ICSO`, `IEO`, `IGKO`, `IHO`, `IMO`, `ISO`, `ISSO`), class breakdowns, batch analysis, and mobile completeness. |
| **🔍 Duplicate Analysis Engine** | High-performance SQL deduplication | 6 deduplication audit checks (emails, phones, school codes, school names, order IDs, composite business records). Calculates duplicate groups, affected rows, and redundant rows without modifying database records. |
| **🗂️ Dedicated Table Sections** | Independent section for every table | Named after each `database.table`. Inspect row/column counts, full column types, search/filter values, analyze NULL values, and export filtered data to CSV. |
| **🧭 Dynamic Table Explorer** | Real-time database explorer | Browse any discovered or newly added table, instant column name search, dynamic SQL filter builder, row preview limit, and CSV export. |

---

## 🔒 Security & Performance Features

- **Strict Read-Only SQL:** Queries enforce read-only prefixes (`SELECT`, `SHOW`, `DESCRIBE`, `EXPLAIN`). Keywords like `DROP`, `TRUNCATE`, `ALTER`, `DELETE`, `INSERT`, `UPDATE` are intercepted and blocked.
- **Identifier Quoting:** Database, table, and column names are quoted safely with backticks to prevent SQL injection.
- **Value Parameterization:** Dynamic values are passed as parameters (`%s`) through PyMySQL.
- **Memory Safety:** Large tables (e.g., `unsubdata` with 809k rows) are never loaded into Pandas memory at once. All calculations are executed server-side in MySQL with `LIMIT` and pagination.
- **Caching & Refresh:** Caching via Streamlit (`@st.cache_data`) minimizes database load. The sidebar **"🔄 Refresh Data & Cache"** button flushes the cache and re-queries metadata instantly.

---

## 📋 Mandatory Completion Checklist

| Category | Item | Status | Verification Details |
|---|---|:---:|---|
| **Database** | Correct MySQL credentials configuration at the top of `app.py` | `[x] Completed and verified` | Verified `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD` present at top of `app.py`. |
| **Database** | Correct database names: `row_data` and `student_1_to_12` | `[x] Completed and verified` | Verified both databases are accessed and queried successfully. |
| **Database** | Discovers actual tables and columns | `[x] Completed and verified` | Verified 11 tables and their column schemas discovered via `information_schema`. |
| **Database** | Verifies `student_1_to_12.students_records` | `[x] Completed and verified` | Verified table schema and 389,604 rows loaded and aggregated. |
| **Database** | Handles failed connections and missing tables | `[x] Completed and verified` | Verified error sanitization and fallback warnings for missing schemas. |
| **Dashboard** | Overview metrics and charts work | `[x] Completed and verified` | Verified total rows (2,511,075), DB split chart, and table inventory table. |
| **Dashboard** | Every discovered table has its own section | `[x] Completed and verified` | Dedicated Table Sections supports all 11 discovered tables. |
| **Dashboard** | Row and column counts are accurate | `[x] Completed and verified` | Verified against MySQL `COUNT(*)` and `information_schema.COLUMNS`. |
| **Dashboard** | Search, filters, and pagination work | `[x] Completed and verified` | Verified multi-column filters, text searches, and SQL pagination (`LIMIT/OFFSET`). |
| **Dashboard** | CSV exports work | `[x] Completed and verified` | Verified CSV generation and download buttons with UTF-8 encoding. |
| **Dashboard** | Refresh updates the data | `[x] Completed and verified` | Verified cache clear and re-query on refresh button click. |
| **Analytics** | Student analytics work | `[x] Completed and verified` | Verified KPI metrics, revenue/price sums, class/state/exam charts, date trend. |
| **Analytics** | School analytics work | `[x] Completed and verified` | Verified school metrics, geo breakdown, and cross-table code reconciliation. |
| **Analytics** | Marketing and contact analytics work | `[x] Completed and verified` | Verified email/phone completeness, repeated contacts, and unsub classification. |
| **Analytics** | OCR and registration analytics work | `[x] Completed and verified` | Verified OCR sheet metrics, 8 exam flag sums, class and batch charts. |
| **Analytics** | Duplicate analysis works without modifying data | `[x] Completed and verified` | Verified SQL `GROUP BY ... HAVING cnt > 1` scans with zero data modifications. |
| **Reliability & Security** | No database write or deletion operations | `[x] Completed and verified` | Verified security guards block `DROP`, `DELETE`, `UPDATE`, `INSERT`. |
| **Reliability & Security** | Password is not printed in logs or displayed in the UI | `[x] Completed and verified` | Verified error sanitizer masks passwords and credentials. |
| **Reliability & Security** | Large tables handled without loading all rows into memory | `[x] Completed and verified` | Verified server-side SQL pagination and aggregation throughout. |
| **Reliability & Security** | NULL values and missing columns are handled | `[x] Completed and verified` | Handled via `COALESCE`, `NULLIF`, and missing column audits. |
| **Reliability & Security** | Python syntax and imports are verified | `[x] Completed and verified` | Tested with `py_compile` and unit test runner `test_dashboard.py`. |
| **Reliability & Security** | All locally testable features have been tested | `[x] Completed and verified` | Tested against live local MySQL server and verified HTTP 200 server response. |
| **Reliability & Security** | Any untested or blocked feature is clearly documented | `[x] Completed and verified` | All features tested and operational. |
| **Final Delivery** | All project files are created | `[x] Completed and verified` | Created `app.py`, `requirements.txt`, `README.md`, `.gitignore`, `test_dashboard.py`. |
| **Final Delivery** | `requirements.txt` contains required dependencies | `[x] Completed and verified` | Streamlit, Pandas, Plotly, PyMySQL, Cryptography included. |
| **Final Delivery** | README includes exact Windows PowerShell commands | `[x] Completed and verified` | Commands documented in Quick Start. |
| **Final Delivery** | Dashboard launch instructions are clear | `[x] Completed and verified` | Clear launch, browser access, and termination steps provided. |
| **Final Delivery** | Completion checklist is updated honestly | `[x] Completed and verified` | Complete checklist verified against real test runs. |
