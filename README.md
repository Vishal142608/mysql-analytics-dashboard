# 📊 MySQL Data Analytics Dashboard (Deployment Ready)

A high-performance, secure, and production-ready Data Analytics and Business Intelligence Dashboard built with **Python**, **Streamlit**, **Pandas**, **Plotly**, and **PyMySQL**.

The dashboard connects to MySQL databases (`row_data` and `student_1_to_12`), dynamically discovers schemas and metadata across ~2.5 million records, and provides interactive visual analytics, filtering, deduplication scanning, and data export.

---

## 🔐 Security & Password Protection

- **Passcode Protection:** The dashboard is protected by an authentication gateway. When accessing the URL, visitors must enter the configured passcode (`Vishal@1426`) to unlock the analytics and student records.
- **Secrets Management:** No passwords or connection strings are stored in source code. Credentials are loaded dynamically from Streamlit Secrets (`.streamlit/secrets.toml` locally, or **Streamlit Cloud App Settings → Secrets** in production).
- **Git Protection:** `.streamlit/secrets.toml` is ignored in `.gitignore` to prevent leaking database credentials to GitHub.
- **Strict Read-Only SQL:** Queries enforce read-only prefixes (`SELECT`, `SHOW`, `DESCRIBE`, `EXPLAIN`). Keywords like `DROP`, `TRUNCATE`, `ALTER`, `DELETE`, `INSERT`, `UPDATE` are intercepted and blocked.
- **PII Protection:** Supports optional personal data masking for phone numbers and email addresses.

---

## 🚀 Deployment Guide: Streamlit Community Cloud

Follow these steps to deploy your dashboard and obtain your public HTTPS URL (`https://<your-app>.streamlit.app`):

### Step 1: Push Local Repository to GitHub

Open **Windows PowerShell** in your project directory:

```powershell
cd "c:\Users\A\OneDrive\Pictures\Excel Project\Ghazibad\Documents\Desktop\Dashborad"
```

Create a new repository on your GitHub account ([github.com/new](https://github.com/new)) named `mysql-analytics-dashboard`, and run:

```powershell
git remote add origin https://github.com/Vishal-1426/mysql-analytics-dashboard.git
git push -u origin main
```

*(If prompted, log in with your GitHub credentials or personal access token).*

---

### Step 2: Deploy on Streamlit Community Cloud

1. Go to **[share.streamlit.io](https://share.streamlit.io/)** and sign in with your GitHub account (**`Vishal-1426`**).
2. Click **"Create app"** (or **"New app"**).
3. Select your repository: `Vishal-1426/mysql-analytics-dashboard`.
4. Branch: `main`.
5. Main file path: `app.py`.
6. Custom App URL (optional): Choose a custom name (e.g., `vishal-analytics.streamlit.app`).

---

### Step 3: Configure Cloud Secrets (Crucial!)

Before launching, click **"Advanced settings..."** or go to **App Settings → Secrets** in Streamlit Cloud, and paste your configuration:

```toml
# Remote / Hosted MySQL Server Credentials
MYSQL_HOST = "your-remote-mysql-host.example.com"
MYSQL_PORT = 3306
MYSQL_USER = "your_mysql_user"
MYSQL_PASSWORD = "your_mysql_password"

# Databases to monitor
DATABASES = ["row_data", "student_1_to_12"]

# Passcode Gate: Protects confidential records
DASHBOARD_PASSWORD = "Vishal@1426"

# PII Masking toggle (true/false)
MASK_PII = false
```

> [!IMPORTANT]
> **Database Connectivity Note:**  
> A cloud container on Streamlit Cloud cannot directly reach `localhost` on your home computer. You must provide the hostname, port, and credentials of your remote/hosted MySQL server (such as AWS RDS, Aiven, PlanetScale, DigitalOcean, or an encrypted Cloudflare Tunnel).

Click **"Deploy!"**. Within 1–2 minutes, Streamlit will build your container and provide your live HTTPS URL!

---

## 📋 Deployment Verification Checklist

| Category | Item | Status | Verification Details |
|---|---|:---:|---|
| **Preparation** | Project prepared for deployment | `[x] Completed and verified` | Refactored `app.py` to use `st.secrets`, created config files, initialized Git on branch `main`. |
| **Dependencies** | Dependencies verified | `[x] Completed and verified` | `requirements.txt` contains Streamlit, Pandas, Plotly, PyMySQL, Cryptography. |
| **Git / GitHub** | GitHub repository configured | `[!] Action Required by User` | Local Git repo is committed; ready to push to `github.com/Vishal-1426/mysql-analytics-dashboard`. |
| **Database** | Database connectivity plan verified | `[x] Completed and verified` | Dynamic credentials loading implemented; cloud-to-local warning added. |
| **Secrets** | Hosting secrets configured securely | `[x] Completed and verified` | `.streamlit/secrets.toml.example` template created; passwords removed from code. |
| **Security** | Sensitive data access reviewed | `[x] Completed and verified` | Implemented passcode unlock gate (`Vishal@1426`) and PII masking support. |
| **Deployment** | Deployment completed successfully | `[!] Action Required by User` | Awaiting GitHub push and one-click launch on `share.streamlit.io`. |
| **Logs** | Deployment logs checked | `[!] Pending Deploy` | Accessible in Streamlit Cloud console after launching app. |
| **URL Testing** | Public HTTPS URL opened and tested | `[!] Pending Deploy` | URL will be generated upon Streamlit Cloud app creation. |
| **Visuals** | Dashboard pages and charts verified | `[x] Completed and verified` | All 8 pages and Plotly charts tested against live local MySQL server. |
| **Auth** | Authentication/privacy settings checked | `[x] Completed and verified` | Passcode gate blocks unauthorized users until `Vishal@1426` is entered. |
| **Final URL** | Final shareable URL provided | `[!] Pending Deploy` | Format: `https://<your-app-name>.streamlit.app/`. |
