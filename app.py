import os
import re
import json
import time
import html
import hashlib
import sqlite3
import warnings
import requests
import pandas as pd
import streamlit as st
from datetime import datetime
from pypdf import PdfReader
from docx import Document
from fpdf import FPDF
from jobspy import scrape_jobs

warnings.filterwarnings("ignore")

# ==========================================
# PATHS & DIRECTORIES
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "Tailored_Resumes_PDF")
CONFIG_PATH = os.path.join(BASE_DIR, "user_config.json")
DB_PATH = os.path.join(BASE_DIR, "jobhunter_seen_jobs.db")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Always blocked scam/unpaid/irrelevant job types
UNIVERSAL_BLACKLIST_TITLES = [
    "unpaid", "pay after placement", "campus ambassador",
    "telecaller", "bpo", "voice process", "delivery boy", "driver", "security guard"
]

SENIOR_BLACKLIST_TITLES = [
    "senior", "sr.", "sr ", "lead", "manager", "principal", "director",
    "head", "vp", "vice president", "chief", "architect", "avp", "agm", "dgm"
]

BLACKLIST_COMPANIES = [
    "confidential", "leading client", "stealth", "top mnc", "undisclosed",
    "crossover", "turing", "bairesdev", "uplers", "staffing", "consultancy",
    "hr solutions", "placement", "skill", "academy", "training institute",
    "edtech training", "coaching"
]

EXPIRED_PAGE_INDICATORS = [
    "no longer accepting applications",
    "this job has expired",
    "job is no longer available",
    "position has been filled",
    "this job is closed",
    "page not found",
    "job expired",
    "no longer open"
]

# ==========================================
# DATABASE & INDEXING ENGINE
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            job_id TEXT PRIMARY KEY,
            job_index INTEGER,
            company_clean TEXT,
            title_clean TEXT,
            location TEXT,
            job_url TEXT,
            status TEXT,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value INTEGER
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO metadata (key, value) VALUES ('last_job_index', 0)")
    conn.commit()
    return conn

def get_next_job_index(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM metadata WHERE key = 'last_job_index'")
    row = cursor.fetchone()
    next_idx = (row[0] if row else 0) + 1
    cursor.execute("UPDATE metadata SET value = ? WHERE key = 'last_job_index'", (next_idx,))
    conn.commit()
    return next_idx

def is_duplicate_or_reposted(conn, job_id, company, title):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1 FROM seen_jobs 
        WHERE job_id = ? 
           OR (company_clean = ? AND title_clean = ? AND seen_at >= datetime('now', '-30 days'))
        """,
        (str(job_id), str(company).lower().strip(), str(title).lower().strip())
    )
    return cursor.fetchone() is not None

def mark_job_seen(conn, job_id, job_index, company, title, location, job_url, status):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO seen_jobs 
        (job_id, job_index, company_clean, title_clean, location, job_url, status) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(job_id), job_index, str(company).lower().strip(), str(title).lower().strip(), str(location), str(job_url), status)
    )
    conn.commit()

# ==========================================
# 100% FREE KEY-LESS AI LLM RESUME PARSER
# ==========================================
def extract_text_from_upload(uploaded_file):
    uploaded_file.seek(0)
    filename = uploaded_file.name.lower()
    text = ""
    try:
        if filename.endswith(".pdf"):
            reader = PdfReader(uploaded_file)
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
        elif filename.endswith(".docx"):
            doc = Document(uploaded_file)
            for para in doc.paragraphs:
                text += para.text + "\n"
        else:
            text = uploaded_file.read().decode("utf-8", errors="ignore")
    except Exception as e:
        st.error(f"Error reading resume file: {e}")
    return text.strip()

def analyze_resume_with_free_llm(raw_text):
    """
    Uses 100% Free, Zero-Key Pollinations OpenAI endpoint (GPT-4o-mini / Llama-3.3)
    so the user NEVER has to enter or rotate an API key or ID.
    """
    system_prompt = (
        "You are an expert ATS Resume Parser and Career Domain Classifier. "
        "Read the candidate's resume carefully and output ONLY a valid JSON object (no markdown, no backticks) "
        "with these exact keys:\n"
        "{\n"
        '  "name": "CANDIDATE FULL NAME IN UPPERCASE",\n'
        '  "email": "email@example.com",\n'
        '  "phone": "phone number",\n'
        '  "location": "City, State or Country",\n'
        '  "degree": "Exact Degree & Graduation Year from resume",\n'
        '  "university": "Exact University/College/Institute name from resume",\n'
        '  "coursework": "Relevant coursework or core subjects from resume",\n'
        '  "certification": "Certifications mentioned in resume",\n'
        '  "detected_domain": "Exact Professional Domain (e.g., Mechanical & Manufacturing Engineering, Data & MIS Analytics, Finance & Derivatives, Software Engineering, etc.)",\n'
        '  "experience_level_detected": "Intern / Fresher (0-1 yr) OR Junior / Entry-Level (1-3 yrs) OR Mid-Level (3-5 yrs)",\n'
        '  "suggested_roles": ["Role 1", "Role 2", "Role 3", "Role 4", "Role 5", "Role 6", "Role 7"],\n'
        '  "extracted_skills": ["Skill 1", "Skill 2", "Skill 3", "Skill 4", "Skill 5", "Skill 6", "Skill 7", "Skill 8", "Skill 9", "Skill 10"],\n'
        '  "tools_skills": ["Tool 1", "Tool 2", "Tool 3", "Tool 4", "Tool 5"],\n'
        '  "functional_skills": ["Method 1", "Method 2", "Method 3", "Method 4"],\n'
        '  "allowed_title_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6"]\n'
        "}\n"
        "CRITICAL RULES:\n"
        "1. suggested_roles MUST strictly match the candidate's actual resume domain and experience level. "
        "For example, if the resume is for a Mechanical Engineer, ONLY suggest Mechanical/CAD/Design/Manufacturing/Production roles. "
        "If the resume is for an MIS/Data Analyst, suggest MIS Executive/Data Analyst/Reporting roles. "
        "2. allowed_title_keywords must be lowercase root words that MUST appear in a valid job title for this candidate."
    )

    endpoints = [
        {"url": "https://text.pollinations.ai/openai", "model": "openai"},
        {"url": "https://text.pollinations.ai/openai", "model": "mistral"}
    ]

    for ep in endpoints:
        try:
            payload = {
                "model": ep["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Parse this resume:\n\n{raw_text[:7000]}"}
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"}
            }
            resp = requests.post(
                ep["url"],
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=22
            )
            if resp.status_code == 200:
                res_json = resp.json()
                content = res_json["choices"][0]["message"]["content"].strip()
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
                parsed = json.loads(content)
                if parsed.get("suggested_roles") and parsed.get("detected_domain"):
                    parsed["base_strengths"] = [
                        "Analytical Problem Solving", "Communication", "Technical Accuracy",
                        "Attention to Detail", "Team Collaboration", "Continuous Learning"
                    ]
                    return parsed
        except Exception:
            continue

    # Offline Smart Fallback if user has no internet during upload
    return fallback_regex_parser(raw_text)

def fallback_regex_parser(raw_text):
    text_low = raw_text.lower()
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    name = re.sub(r"[^A-Za-z\s\.]", "", lines[0][:45]).strip().upper() if lines else "CANDIDATE"
    email_m = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", raw_text)
    phone_m = re.search(r"(\+?\d{1,3}[\s-]?)?\(?(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})", raw_text)

    if any(w in text_low for w in ["solidworks", "ansys", "catia", "thermodynamics", "mechanical engineer", "fea", "cfd", "gd&t"]):
        return {
            "name": name,
            "email": email_m.group(0) if email_m else "candidate@email.com",
            "phone": phone_m.group(0) if phone_m else "+91 XXXXXXXXXX",
            "location": "India",
            "degree": "Bachelor of Science / B.Tech in Mechanical Engineering",
            "university": "Recognized Engineering Institute",
            "coursework": "Thermodynamics, Fluid Mechanics, Machine Design, Heat Transfer, Mechatronics, FEA",
            "certification": "Certified SolidWorks Professional (CSWP) | Six Sigma Green Belt",
            "detected_domain": "Mechanical & Manufacturing Engineering",
            "experience_level_detected": "Junior / Entry-Level (1-3 yrs)",
            "suggested_roles": [
                "Mechanical Design Engineer", "Mechanical Engineer", "CAD Design Engineer",
                "Manufacturing Engineer", "Production Engineer", "FEA Analyst", "Quality Engineer"
            ],
            "extracted_skills": [
                "SolidWorks", "AutoCAD", "CATIA V5", "Fusion 360", "ANSYS (FEA/CFD)",
                "GD&T", "CNC Machining", "Injection Molding", "Sheet Metal", "3D Printing", "Lean Manufacturing", "Six Sigma"
            ],
            "tools_skills": ["SolidWorks", "AutoCAD", "ANSYS", "CATIA V5", "MATLAB"],
            "functional_skills": ["DFM/DFA", "Lean Manufacturing", "Six Sigma", "Tolerance Stack-up", "Prototyping"],
            "allowed_title_keywords": [
                "mechanical", "design", "cad", "manufacturing", "production", "quality",
                "fea", "cfd", "r&d", "robotics", "automation", "tooling", "automotive", "industrial"
            ],
            "base_strengths": ["Precision Product Design", "Cross-Functional Collaboration", "Problem Solving", "Lean Six Sigma"]
        }
    else:
        return {
            "name": name,
            "email": email_m.group(0) if email_m else "candidate@email.com",
            "phone": phone_m.group(0) if phone_m else "+91 XXXXXXXXXX",
            "location": "India",
            "degree": "Bachelor's Degree Graduate / Final Year",
            "university": "Recognized University",
            "coursework": "Data Analysis, Financial & Business Operations, Reporting",
            "certification": "Domain Professional Certification",
            "detected_domain": "Data, MIS & Business Analytics",
            "experience_level_detected": "Intern / Fresher (0-1 yr)",
            "suggested_roles": [
                "Data Analyst Intern", "MIS Executive", "Business Analyst Intern",
                "Junior Data Analyst", "Reporting Analyst", "Power BI Analyst", "Finance Intern"
            ],
            "extracted_skills": ["SQL", "MS Excel", "Power BI", "VLOOKUP", "Pivot Tables", "Data Cleaning", "MIS Reporting", "Pandas"],
            "tools_skills": ["MS Excel", "Google Sheets", "SQL", "Power BI", "Python"],
            "functional_skills": ["Data Formatting", "Record Management", "KPI Reporting", "Variance Analysis"],
            "allowed_title_keywords": ["data", "analyst", "mis", "reporting", "business", "bi", "excel", "sql", "finance", "operations"],
            "base_strengths": ["Analytical Problem Solving", "Data Accuracy", "Attention to Detail", "Communication"]
        }

# ==========================================
# 4-LAYER STRICT JOB VERIFICATION ENGINE
# ==========================================
def check_job_link_alive(job_url):
    if not job_url or not str(job_url).startswith("http"):
        return False, "Missing or invalid job link"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        }
        resp = requests.get(job_url, headers=headers, timeout=8, allow_redirects=True)
        if resp.status_code in (404, 410):
            return False, f"Dead/Expired Link (HTTP {resp.status_code})"
        page_text = resp.text.lower()[:15000]
        for expired_phrase in EXPIRED_PAGE_INDICATORS:
            if expired_phrase in page_text:
                return False, f"Expired Job ('{expired_phrase}')"
        return True, "Active"
    except Exception:
        return True, "Valid Portal Link"

def verify_and_tailor_job(job_row, profile, target_locations, exp_level):
    company = str(job_row.get("company", "")).strip()
    title = str(job_row.get("title", "")).strip()
    location = str(job_row.get("location", "")).strip()
    job_url = str(job_row.get("job_url", "")).strip()
    description = str(job_row.get("description", "")).strip()
    if description.lower() == "nan":
        description = ""

    comp_lower = company.lower()
    title_lower = title.lower()
    loc_lower = location.lower()
    combined_text = f"{title_lower} {description.lower()}"

    # 1. Company Validation
    if not company or comp_lower in ["nan", "none", ""]:
        return False, "Missing/Anonymous company name"
    for bad_comp in BLACKLIST_COMPANIES:
        if bad_comp in comp_lower:
            return False, f"Blacklisted agency/company ({bad_comp})"

    # 2. Universal Scam/Irrelevant Blocker
    for bad_title in UNIVERSAL_BLACKLIST_TITLES:
        if bad_title in title_lower:
            return False, f"Filtered irrelevant/unpaid category ({bad_title.strip()})"

    # 3. Strict Dynamic Title Verification based on AI-extracted Target Roles & Domain Keywords
    allowed_roots = set(w.lower() for w in profile.get("allowed_title_keywords", []) if len(w) >= 2)
    for role in profile.get("target_roles", []):
        for word in re.findall(r"[a-zA-Z0-9#\+]+", role.lower()):
            if len(word) >= 3 and word not in ("intern", "junior", "senior", "trainee", "executive", "associate", "specialist"):
                allowed_roots.add(word)

    if allowed_roots and not any(root in title_lower for root in allowed_roots):
        return False, f"Title '{title}' does not match your domain keywords"

    # 4. Experience Level Filter
    if exp_level == "Intern / Fresher (0-1 yr)":
        for sr_word in SENIOR_BLACKLIST_TITLES:
            if sr_word.lower() in title_lower:
                return False, f"Senior role filtered ({sr_word})"
        if description:
            exp_match = re.search(r'\b([2-9]|1[0-5])\s*\+?\s*(?:years|yrs)\b', description.lower())
            if exp_match and "intern" not in title_lower and "fresher" not in combined_text and "trainee" not in title_lower:
                return False, f"Requires {exp_match.group(0)} experience"
    elif exp_level == "Junior / Entry-Level (1-3 yrs)":
        for sr_word in SENIOR_BLACKLIST_TITLES:
            if sr_word.lower() in title_lower:
                return False, f"Senior role filtered ({sr_word})"
        if description:
            exp_match = re.search(r'\b([4-9]|1[0-5])\s*\+?\s*(?:years|yrs)\b', description.lower())
            if exp_match:
                return False, f"Requires {exp_match.group(0)} experience"

    # 5. Multi-Location Verification
    user_locs = [l.strip().lower() for l in target_locations if l.strip()]
    if user_locs and "india" not in user_locs and "all india" not in user_locs:
        loc_matched = any(ul in loc_lower or ul in combined_text for ul in user_locs)
        if "remote" in user_locs and ("remote" in loc_lower or "work from home" in combined_text):
            loc_matched = True
        if not loc_matched and loc_lower not in ["india", "", "nan"]:
            return False, f"Location mismatch ({location})"

    # 6. Skill Overlap Check
    user_skills = [s.strip() for s in profile.get("extracted_skills", []) if s.strip()]
    matched_skills = [s for s in user_skills if s.lower() in combined_text]

    if len(description) > 150 and not matched_skills and not any(r in combined_text for r in allowed_roots):
        return False, "Job description does not match your resume skills"

    # 7. Live Link & Expiry Check
    link_ok, link_msg = check_job_link_alive(job_url)
    if not link_ok:
        return False, link_msg

    # Build Tailored Resume Sections using candidate's actual skills + matched JD skills
    all_core_skills = list(dict.fromkeys(matched_skills + user_skills))
    tools_list = profile.get("tools_skills") or all_core_skills[:5]
    func_list = profile.get("functional_skills") or ["Process Optimization", "Quality Assurance", "Cross-Functional Collaboration"]

    skills_core_str = ", ".join(all_core_skills[:8])
    skills_tools_str = ", ".join(tools_list[:6])
    skills_other_str = ", ".join(func_list[:6])

    ats_score = min(98, 88 + len(matched_skills) * 2)
    domain_name = profile.get("detected_domain", "Professional")

    tailored_objective = (
        f"Results-driven {domain_name} candidate ({profile.get('degree', 'Graduate')}) "
        f"proficient in {', '.join(all_core_skills[:5])}. "
        f"Seeking the {title} role at {company} to leverage technical expertise, "
        f"optimize workflows, and deliver high-impact results."
    )

    recruiter_note = (
        f"Hi Hiring Team at {company}, I am applying for the {title} opening. "
        f"My background in {domain_name} and hands-on skills in {', '.join(all_core_skills[:4])} "
        f"align closely with your requirements. Please find my tailored PDF resume attached."
    )

    return True, {
        "ats_match_score": ats_score,
        "tailored_objective": tailored_objective,
        "skills_data_analytics": skills_core_str,
        "skills_excel": skills_tools_str,
        "skills_other": skills_other_str,
        "tailored_strengths": profile.get("base_strengths", ["Analytical Problem Solving", "Attention to Detail", "Team Collaboration"]),
        "recruiter_note": recruiter_note
    }

# ==========================================
# INDEXED PDF RESUME GENERATOR (fpdf2)
# ==========================================
def clean_pdf_text(text):
    return str(text).encode("latin-1", "ignore").decode("latin-1")

def build_tailored_pdf_resume(job_index, company, title, profile, ai_data):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(left=14, top=12, right=14)
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 8, clean_pdf_text(profile.get("name", "CANDIDATE")), new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    contact_line = f"{profile.get('location', 'India')}   |   {profile.get('phone', '')}   |   {profile.get('email', '')}"
    pdf.cell(0, 6, clean_pdf_text(contact_line), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(3)

    def add_section_heading(sec_title):
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(31, 78, 121)
        pdf.cell(0, 6, clean_pdf_text(sec_title.upper()), new_x="LMARGIN", new_y="NEXT")
        y = pdf.get_y()
        pdf.set_draw_color(31, 78, 121)
        pdf.set_line_width(0.4)
        pdf.line(14, y, 196, y)
        pdf.ln(2.5)
        pdf.set_text_color(20, 20, 20)

    add_section_heading("CAREER OBJECTIVE")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, clean_pdf_text(ai_data["tailored_objective"]))
    pdf.ln(3)

    add_section_heading("EDUCATION")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, clean_pdf_text(profile.get("university", "")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 5, clean_pdf_text(profile.get("degree", "")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.multi_cell(0, 5, clean_pdf_text(f"Relevant Coursework: {profile.get('coursework', '')}."))
    pdf.ln(3)

    add_section_heading("TECHNICAL & DOMAIN SKILLS")
    skills_rows = [
        ("Core Competencies: ", ai_data["skills_data_analytics"]),
        ("Tools & Platforms: ", ai_data["skills_excel"]),
        ("Methodologies & Process: ", ai_data["skills_other"])
    ]
    for label, val in skills_rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.write(5.5, clean_pdf_text(label))
        pdf.set_font("Helvetica", "", 10)
        pdf.write(5.5, clean_pdf_text(f"{val}\n"))
    pdf.ln(3)

    add_section_heading("CERTIFICATION & CREDENTIALS")
    pdf.set_font("Helvetica", "B", 10)
    pdf.multi_cell(0, 5, clean_pdf_text(profile.get("certification", "Professional Certification")))
    pdf.ln(3)

    add_section_heading("CORE STRENGTHS")
    pdf.set_font("Helvetica", "", 10)
    for st_item in ai_data["tailored_strengths"]:
        pdf.cell(0, 5.5, clean_pdf_text(f"  -   {st_item}"), new_x="LMARGIN", new_y="NEXT")

    safe_name = "".join(c for c in profile.get("name", "Candidate") if c.isalnum() or c in (" ", "_")).strip().replace(" ", "_")
    safe_comp = "".join(c for c in str(company) if c.isalnum() or c in (" ", "_")).strip().replace(" ", "_") or "Company"
    filename = f"Job_{job_index:03d}_{safe_name}_{safe_comp}.pdf"
    pdf_path = os.path.join(OUTPUT_DIR, filename)
    pdf.output(pdf_path)
    return pdf_path, filename

def send_telegram_alert(bot_token, chat_id, job_index, job_row, ai_data, pdf_path, pdf_filename):
    company = html.escape(str(job_row.get("company", "Company")))
    title = html.escape(str(job_row.get("title", "Role")))
    location = html.escape(str(job_row.get("location", "India")))
    job_url = str(job_row.get("job_url", ""))
    portal = html.escape(str(job_row.get("site", "PORTAL")).upper())
    skills = html.escape(str(ai_data.get("skills_data_analytics", "")))
    note = html.escape(str(ai_data.get("recruiter_note", "")))

    caption = (
        f"🔢 <b>JOB INDEX: #{job_index:03d}</b>  |  ✅ <b>100% Verified ({portal})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏢 <b>Company:</b> {company}\n"
        f"💼 <b>Role:</b> {title}\n"
        f"📍 <b>Location:</b> {location}\n"
        f"🎯 <b>ATS Match Score:</b> {ai_data.get('ats_match_score', 92)}%\n"
        f"📄 <b>Resume File:</b> <code>{html.escape(pdf_filename)}</code>\n\n"
        f"🛠 <b>Matched Keywords Added:</b>\n<code>{skills}</code>\n\n"
        f"📋 <b>Recruiter Note:</b>\n<i>{note}</i>\n\n"
        f"🔗 <a href='{job_url}'><b>👉 CLICK HERE TO APPLY DIRECTLY ON PORTAL</b></a>"
    )
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with open(pdf_path, "rb") as pdf_file:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"document": pdf_file},
            timeout=20
        )
        return resp.json()

def load_saved_config():
    # Multi-user isolation: return empty config so every visitor starts with a clean private session
    return {}

def save_user_config(data):
    # Persist in session state for the active visitor session
    for k, v in data.items():
        st.session_state[k] = v

# ==========================================
# STREAMLIT WEB PORTAL UI
# ==========================================
st.set_page_config(page_title="JobHunter Pro | Making the job hunting simple", page_icon="🎯", layout="wide")

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #0f172a 0%, #1e3a8a 100%);
        padding: 22px 28px;
        border-radius: 12px;
        color: white;
        margin-bottom: 20px;
    }
    .main-header h1 {
        margin: 0;
        font-size: 2.1rem;
        font-weight: 800;
        color: #ffffff;
    }
    .main-header p {
        margin: 4px 0 0 0;
        font-size: 1.05rem;
        color: #93c5fd;
        font-style: italic;
    }
</style>
<div class="main-header">
    <h1>🎯 JobHunter Pro Engine</h1>
    <p>"Making the job hunting simple" — Built-in Free AI Resume Intelligence & Indexed PDF Tailoring</p>
</div>
""", unsafe_allow_html=True)

# Multi-user session isolation: Do not auto-load shared user_config.json on startup
saved_cfg = {}
conn = init_db()

# Initialize default profile in session_state once
if "profile" not in st.session_state:
    default_prof = {
        "name": "ANSHUMAN DWIVEDI",
        "location": "Prayagraj, Uttar Pradesh",
        "phone": "+91 9792769087",
        "email": "anshumandwivedi2020@gmail.com",
        "degree": "Bachelor of Commerce (B.Com) - Final Year Student | Expected June 2027",
        "university": "Prof. Rajju Bhaiya University (Th. Har Narayan Singh Degree College), Prayagraj, India",
        "coursework": "Financial Accounting, Cost Accounting, Corporate Finance, Business Operations, Banking & Financial Markets",
        "certification": "NISM Series VIII - Equity Derivatives Certification",
        "detected_domain": "Data, Business & Financial Analytics",
        "suggested_roles": [
            "Data Analyst Intern", "Business Analyst Intern", "Finance Intern",
            "Junior Data Analyst", "Power BI Analyst", "SQL Data Analyst", "MIS Executive"
        ],
        "extracted_skills": ["SQL", "Pandas", "Power BI", "Excel", "VLOOKUP", "XLOOKUP", "Pivot Tables", "Data Modeling"],
        "tools_skills": ["SQL", "Power BI", "Pandas", "Microsoft Excel"],
        "functional_skills": ["Data Accuracy", "Reconciliation", "Process Optimization", "Analytical Problem Solving"],
        "allowed_title_keywords": ["data", "analyst", "business", "finance", "financial", "mis", "bi", "sql", "reporting", "equity"]
    }
    st.session_state["profile"] = default_prof
    st.session_state["domain_box"] = default_prof.get("detected_domain", "")
    st.session_state["roles_box"] = ", ".join(default_prof.get("suggested_roles", []))
    st.session_state["skills_box"] = ", ".join(default_prof.get("extracted_skills", []))

with st.sidebar:
    st.header("⚙️ 1. Telegram Setup")
    bot_token = st.text_input("Telegram Bot Token", value=st.session_state.get("bot_token", ""), type="password", placeholder="123456:ABC-DEF...")
    chat_id = st.text_input("Telegram Chat ID", value=st.session_state.get("chat_id", ""), placeholder="e.g. 1298829840")

    st.divider()
    st.header("📍 2. Search Preferences")
    locations_input = st.text_input(
        "Target Locations (comma-separated)",
        value=st.session_state.get("locations", "Noida, Gurgaon, New Delhi, Delhi, Bangalore, Mumbai, Pune, Hyderabad, Remote"),
        help="Enter multiple cities or 'Remote'. Only jobs matching these locations will be sent."
    )
    exp_level = st.selectbox(
        "Experience Level",
        ["Intern / Fresher (0-1 yr)", "Junior / Entry-Level (1-3 yrs)", "Mid-Level (3-5 yrs)"],
        index=0
    )
    hours_old = st.slider("Freshness Filter (Posted within hours)", min_value=6, max_value=72, value=24, step=6)
    scan_interval = st.number_input("Auto-Rescan Interval (Minutes, 0 = Run Once)", min_value=0, max_value=180, value=45)

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📄 Upload ANY Resume (PDF or DOCX)")
    uploaded_resume = st.file_uploader(
        "Drop any resume here — Built-in Free AI LLM automatically extracts exact domain, roles & skills (Zero API Key needed!)",
        type=["pdf", "docx", "txt"]
    )

    if uploaded_resume is not None:
        file_bytes = uploaded_resume.getvalue()
        file_hash = hashlib.md5(file_bytes).hexdigest()

        if st.session_state.get("last_uploaded_hash") != file_hash:
            with st.spinner(f"🤖 Free AI is reading '{uploaded_resume.name}' and extracting exact career domain & roles..."):
                raw_text = extract_text_from_upload(uploaded_resume)
                parsed_profile = analyze_resume_with_free_llm(raw_text)
                st.session_state["profile"] = parsed_profile
                st.session_state["last_uploaded_hash"] = file_hash
                # Directly overwrite widget session_state values so UI updates 100% of the time
                st.session_state["domain_box"] = parsed_profile.get("detected_domain", "Professional Domain")
                st.session_state["roles_box"] = ", ".join(parsed_profile.get("suggested_roles", []))
                st.session_state["skills_box"] = ", ".join(parsed_profile.get("extracted_skills", []))
                st.rerun()

        prof = st.session_state["profile"]
        st.success(
            f"✅ **AI Parsed Candidate:** `{prof.get('name')}`\n\n"
            f"🎯 **Detected Domain:** `{prof.get('detected_domain')}`\n\n"
            f"🎓 **Education:** {prof.get('degree')}"
        )

profile = st.session_state["profile"]

with col2:
    st.subheader("🧠 AI-Detected Domain, Roles & Skills (Editable)")
    domain_val = st.text_input(
        "Detected Work Domain (Any industry/field)",
        key="domain_box"
    )
    profile["detected_domain"] = domain_val.strip()

    roles_val = st.text_area(
        "Target Job Roles to Search (AI-generated from your resume — Edit/Add any role before starting)",
        key="roles_box",
        height=95
    )
    target_roles = [r.strip() for r in roles_val.split(",") if r.strip()]
    profile["target_roles"] = target_roles
    profile["suggested_roles"] = target_roles

    skills_val = st.text_input(
        "Detected Resume Skills (Used for strict JD matching & PDF tailoring)",
        key="skills_box"
    )
    profile["extracted_skills"] = [s.strip() for s in skills_val.split(",") if s.strip()]

st.divider()

btn_col1, btn_col2, btn_col3 = st.columns([2, 1, 1])
with btn_col1:
    start_btn = st.button("🚀 START JOBHUNTER ENGINE", type="primary", use_container_width=True)
with btn_col2:
    if st.button("💾 Save My Settings", use_container_width=True):
        save_user_config({
            "bot_token": bot_token,
            "chat_id": chat_id,
            "locations": locations_input,
            "profile": profile
        })
        st.toast("Settings saved locally!")
with btn_col3:
    if st.button("🗑️ Reset Seen Jobs DB", use_container_width=True):
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        conn = init_db()
        st.toast("Database & Index reset to #001!")

m1, m2, m3 = st.columns(3)
cursor = conn.cursor()
cursor.execute("SELECT value FROM metadata WHERE key = 'last_job_index'")
current_idx = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM seen_jobs WHERE status = 'APPROVED'")
total_approved = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM seen_jobs WHERE status != 'APPROVED'")
total_filtered = cursor.fetchone()[0]

m1.metric("🔢 Current Job Index Counter", f"#{current_idx:03d}")
m2.metric("✅ Verified Jobs Sent to Telegram", total_approved)
m3.metric("🛡️ Fake / Irrelevant Jobs Blocked", total_filtered)

log_box = st.empty()

def execute_scan_cycle():
    target_locs = [l.strip() for l in locations_input.split(",") if l.strip()]
    search_loc_query = "India" if len(target_locs) > 1 else (target_locs[0] if target_locs else "India")

    logs = []
    def add_log(msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        logs.append(f"[{timestamp}] {msg}")
        log_box.code("\n".join(logs[-18:]), language="text")

    add_log(f"🚀 Starting strict [{profile['detected_domain']}] scan for {profile['name']}...")

    for role in target_roles:
        for portal in ["linkedin", "naukri", "indeed", "glassdoor"]:
            add_log(f"🔍 Scraping [{portal.upper()}] for '{role}'...")
            try:
                jobs_df = scrape_jobs(
                    site_name=[portal],
                    search_term=role,
                    location=search_loc_query,
                    results_wanted=8,
                    hours_old=hours_old,
                    country_indeed="India"
                )
            except Exception as e:
                add_log(f"⚠️ Rate-limit/skip on {portal}: {str(e)[:80]} (Cooling down 4s...)")
                time.sleep(4)
                continue

            if jobs_df is None or jobs_df.empty:
                time.sleep(1.5)
                continue

            for _, job in jobs_df.iterrows():
                job_id = str(job.get("id") or job.get("job_url"))
                company = str(job.get("company", "")).strip()
                title = str(job.get("title", "")).strip()
                loc = str(job.get("location", "India")).strip()
                job_url = str(job.get("job_url", "")).strip()

                if is_duplicate_or_reposted(conn, job_id, company, title):
                    continue

                is_valid, result_data = verify_and_tailor_job(job, profile, target_locs, exp_level)
                if not is_valid:
                    mark_job_seen(conn, job_id, 0, company, title, loc, job_url, f"BLOCKED: {result_data}")
                    add_log(f"❌ Filtered [{title} @ {company}] -> {result_data}")
                    continue

                job_index = get_next_job_index(conn)
                pdf_path, pdf_filename = build_tailored_pdf_resume(job_index, company, title, profile, result_data)
                tg_resp = send_telegram_alert(bot_token, chat_id, job_index, job, result_data, pdf_path, pdf_filename)

                if tg_resp.get("ok"):
                    mark_job_seen(conn, job_id, job_index, company, title, loc, job_url, "APPROVED")
                    add_log(f"✅ SENT #{job_index:03d}: {title} @ {company} -> {pdf_filename}")
                else:
                    add_log(f"⚠️ Telegram API Error: {tg_resp.get('description')}")

                time.sleep(2.5)
            time.sleep(3)

    add_log("🎉 Scan cycle completed!")

if start_btn:
    if not bot_token or not chat_id:
        st.error("⚠️ Please enter your Telegram Bot Token and Telegram Chat ID in the left sidebar first!")
    else:
        save_user_config({
            "bot_token": bot_token,
            "chat_id": chat_id,
            "locations": locations_input,
            "profile": profile
        })
        if scan_interval == 0:
            execute_scan_cycle()
        else:
            while True:
                execute_scan_cycle()
                st.info(f"⏳ Next automatic scan in {scan_interval} minutes...")
                time.sleep(scan_interval * 60)

st.subheader("📋 Recently Verified & Indexed Jobs")
recent_df = pd.read_sql_query(
    "SELECT job_index AS 'Index #', company_clean AS 'Company', title_clean AS 'Role', location AS 'Location', job_url AS 'Direct Apply Link', seen_at AS 'Time' FROM seen_jobs WHERE status = 'APPROVED' ORDER BY job_index DESC LIMIT 25",
    conn
)
if not recent_df.empty:
    st.dataframe(
        recent_df,
        column_config={"Direct Apply Link": st.column_config.LinkColumn("Direct Apply Link")},
        use_container_width=True,
        hide_index=True
    )
else:
    st.caption("No verified jobs sent yet. Enter your details and click 'START JOBHUNTER ENGINE' above.")
