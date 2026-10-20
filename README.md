# 🎯 JobHunter Pro Engine
> **"Making the job hunting simple"** — An AI-Powered, Multi-Portal Job Aggregation, 4-Layer Verification & Automated ATS PDF Resume Tailoring Engine.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-Web%20Portal-FF4B4B?style=for-the-badge&logo=streamlit)
![SQLite](https://img.shields.io/badge/SQLite-Deduplication%20DB-003B57?style=for-the-badge&logo=sqlite)
![Telegram API](https://img.shields.io/badge/Telegram%20Bot%20API-Real--Time%20Alerts-26A5E4?style=for-the-badge&logo=telegram)
![License](https://img.shields.io/badge/Cost-100%25%20Free%20%26%20Open%20Source-success?style=for-the-badge)

---

## 🌟 Project Overview
**JobHunter Pro Engine** solves two major problems in modern job hunting: **ghost/expired job listings** and **generic, untailored resumes**. 

Users simply upload their existing resume (PDF/DOCX), enter their Telegram credentials, and select their preferred locations. The engine automatically parses their career domain and technical skills using a zero-key Cloud LLM, scrapes live job openings across **LinkedIn, Naukri, Indeed, and Glassdoor**, runs a strict **4-Layer Verification Pipeline**, dynamically generates an **ATS-optimized, indexed PDF resume (`#001`, `#002`)** tailored to each job description, and delivers the PDF + direct application link straight to the user's Telegram.

---

## 🚀 Key Features & Architecture

1. **🧠 Zero-Key AI Resume Intelligence:**
   - Automatically extracts the candidate's Name, Education, Certifications, Core Domain, Target Job Titles, and Technical Skills from any uploaded `.pdf` or `.docx` resume across any industry (Data Analytics, Finance, Mechanical Engineering, Software, MIS, etc.).
2. **🛡️ 4-Layer Strict Job Verification Pipeline:**
   - **Layer 1 (Company & Agency Filter):** Blocks anonymous/undisclosed listings and recruitment spam agencies.
   - **Layer 2 (Dynamic Domain & Title Alignment):** Ensures the job title strictly matches the candidate's target domain and selected experience bracket (`Intern/Fresher`, `Junior`, or `Mid-Level`).
   - **Layer 3 (Resume Skill Overlap):** Verifies that the job description matches the candidate's extracted technical skills.
   - **Layer 4 (Live HTTP & Expiry Validator):** Pings the live job portal URL and scans page content to reject closed, 404, or expired listings (`"no longer accepting applications"`).
3. **📄 Automated ATS PDF Resume Tailoring (`fpdf2`) & Synchronized Indexing:**
   - Dynamically injects matched ATS keywords from the job description into a clean, single-page PDF resume.
   - Assigns a synchronized Job Index (`#001`, `#002`, etc.) to both the Telegram notification and the generated PDF filename (`Job_001_Name_Company.pdf`).
4. **📲 Instant Telegram Delivery with Direct Apply Link:**
   - Sends the tailored PDF resume, ATS match score, recruiter pitch note, and a one-click **Direct Apply Link** directly to the user's Telegram via the Telegram Bot API.
5. **🗄️ SQLite Deduplication Engine:**
   - Tracks seen job IDs and `(company, title)` pairs over a 30-day rolling window to prevent duplicate or reposted job alerts.

---

## 🛠️ Tech Stack
* **Frontend / Web Portal:** `Streamlit`
* **Multi-Portal Job Scraping:** `python-jobspy` (LinkedIn, Naukri, Indeed, Glassdoor)
* **AI Resume Parsing:** Cloud LLM JSON Extraction (`Pollinations OpenAI Endpoint`) + Regex NLP Fallback (`pypdf`, `python-docx`)
* **Dynamic PDF Generation:** `fpdf2`
* **Database & State Management:** `SQLite3`, `Pandas`
* **Notifications:** `Telegram Bot HTTP API` (`requests`)

---

## 💻 How to Run Locally (One-Click Launchers)

### macOS
Double-click **`Start_Mac.command`** (or run `./Start_Mac.command` in Terminal). It automatically sets up the virtual environment, installs dependencies from `requirements.txt`, and opens the web portal in your browser.

### Windows
Double-click **`Start_Windows.bat`**. It automatically creates `.venv`, installs all required packages, and launches the Streamlit portal.

### Manual CLI Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## 👨💻 Author
**Anshuman Dwivedi**
* Built with Python, Streamlit, and AI Automation.
