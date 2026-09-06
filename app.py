import json
import streamlit as st
from pypdf import PdfReader
from docx import Document
from google import genai

st.set_page_config(
    page_title="ResumeLens",
    page_icon="📄",
    layout="wide"
)

# ---------- Helpers ----------

def extract_pdf_text(uploaded_file):
    reader = PdfReader(uploaded_file)
    text = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text.append(page_text)
    return "\n".join(text)


def extract_docx_text(uploaded_file):
    document = Document(uploaded_file)
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def extract_text(uploaded_file):
    if uploaded_file.name.lower().endswith(".pdf"):
        return extract_pdf_text(uploaded_file)
    return extract_docx_text(uploaded_file)


def analyze_resume(resume_text, job_description):
    api_key = st.secrets.get("GEMINI_API_KEY")

    if not api_key:
        st.error("GEMINI_API_KEY is missing. Add it to Streamlit Secrets.")
        st.stop()

    client = genai.Client(api_key=api_key)

    if job_description.strip():
        job_section = f"""
JOB DESCRIPTION:
{job_description}
"""
        job_instruction = """
Compare the resume against the supplied job description.
Evaluate how well the candidate's actual experience and skills match the role.
Identify important keywords or requirements that appear to be missing or weak.
Do not recommend adding a keyword unless the candidate's resume supports it.
"""
    else:
        job_section = "No job description was provided."
        job_instruction = """
No job description was supplied. Give a general resume/ATS assessment.
Do not calculate a job-specific match. Set job_match_score to null.
"""

    prompt = f"""
You are an expert resume reviewer, ATS specialist, and recruiter.

Analyze the resume below. Your goal is to give practical, honest feedback
that helps the candidate improve the resume.

IMPORTANT RULES:
- Never invent facts about the candidate.
- Never invent employers, job titles, dates, degrees, certifications,
  skills, achievements, metrics, or responsibilities.
- Do not reward keyword stuffing.
- If something is not supported by the resume, say so.
- ATS score is an ESTIMATE based on common ATS-friendly practices, not a
  guaranteed score from a real ATS system.
- Be specific rather than giving generic advice.
- Prioritize the most important improvements.
- For the recruiter review, imagine you have approximately 20 seconds for
  an initial scan.
- If a job description is supplied, distinguish between actual matches and
  missing/weak requirements.

{job_instruction}

Return ONLY valid JSON using exactly this structure:

{{
  "overall_score": 0,
  "ats_score": 0,
  "job_match_score": null,
  "summary": "Short overall assessment.",
  "strengths": [
    "strength 1",
    "strength 2",
    "strength 3"
  ],
  "top_improvements": [
    {{
      "priority": "High",
      "issue": "Specific issue",
      "recommendation": "Specific recommendation"
    }}
  ],
  "missing_keywords": [
    "keyword 1",
    "keyword 2"
  ],
  "formatting_issues": [
    "issue 1"
  ],
  "content_issues": [
    "issue 1"
  ],
  "recruiter_20_second_review": {{
    "first_impression": "What a recruiter is likely to understand quickly.",
    "what_stands_out": [
      "item 1",
      "item 2"
    ],
    "what_gets_overlooked": [
      "item 1",
      "item 2"
    ],
    "would_continue_reading": true,
    "reason": "Short explanation."
  }},
  "rewritten_summary": "Improved professional summary using only facts supported by the resume.",
  "improved_bullets": [
    {{
      "original": "Original bullet copied from resume.",
      "improved": "Improved version without inventing facts.",
      "why": "Why this version is stronger."
    }}
  ]
}}

SCORING GUIDANCE:
- overall_score: 0-100
- ats_score: 0-100
- job_match_score: 0-100 when a job description exists, otherwise null.
- Use the full range where appropriate. Do not automatically give high scores.

RESUME:
{resume_text}

{job_section}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json"
        }
    )

    try:
        return json.loads(response.text)
    except Exception:
        # Fallback in case the model returns fenced JSON or extra whitespace.
        cleaned = response.text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "", 1).replace("```", "", 1).strip()
        return json.loads(cleaned)


def score_color(score):
    if score >= 80:
        return "🟢"
    if score >= 60:
        return "🟡"
    return "🔴"


# ---------- UI ----------

st.title("📄 ResumeLens")
st.caption("AI-powered resume & ATS compatibility checker")

st.markdown(
    "Upload your CV and optionally paste the job description you are applying for. "
    "ResumeLens will evaluate ATS compatibility, job relevance, content quality, "
    "and how your CV looks to a recruiter during a quick first scan."
)

uploaded_file = st.file_uploader(
    "Upload your CV",
    type=["pdf", "docx"],
    help="PDF or Word document"
)

job_description = st.text_area(
    "Job Description (optional)",
    height=220,
    placeholder="Paste the job description here if you want a job-specific match analysis..."
)

analyze_button = st.button(
    "🔍 Analyze My Resume",
    type="primary",
    use_container_width=True
)

if analyze_button:
    if not uploaded_file:
        st.warning("Please upload a PDF or DOCX resume first.")
        st.stop()

    with st.spinner("Reading your resume and generating the analysis..."):
        try:
            resume_text = extract_text(uploaded_file)

            if not resume_text.strip():
                st.error(
                    "I couldn't extract readable text from this file. "
                    "If it is a scanned/image-only PDF, try an editable PDF or DOCX."
                )
                st.stop()

            # Avoid sending extremely large documents unnecessarily.
            resume_text = resume_text[:50000]
            job_description = job_description[:30000]

            result = analyze_resume(resume_text, job_description)

        except Exception as e:
            st.error(f"Something went wrong: {e}")
            st.stop()

    st.success("Analysis complete.")

    # ---------- Scores ----------
    st.subheader("📊 Your Scores")

    score_cols = st.columns(3)

    with score_cols[0]:
        st.metric(
            "Overall Score",
            f"{result.get('overall_score', 0)}/100"
        )

    with score_cols[1]:
        ats = result.get("ats_score", 0)
        st.metric(
            "ATS Compatibility",
            f"{ats}/100"
        )

    with score_cols[2]:
        job_match = result.get("job_match_score")
        if job_match is None:
            st.metric("Job Match", "Not assessed")
        else:
            st.metric("Job Match", f"{job_match}/100")

    st.divider()

    # ---------- Summary ----------
    st.subheader("📝 Overall Assessment")
    st.write(result.get("summary", ""))

    # ---------- Strengths / improvements ----------
    left, right = st.columns(2)

    with left:
        st.subheader("✅ What's Working")
        for item in result.get("strengths", []):
            st.write(f"• {item}")

    with right:
        st.subheader("🚨 Top Improvements")
        for item in result.get("top_improvements", []):
            priority = item.get("priority", "Medium")
            issue = item.get("issue", "")
            recommendation = item.get("recommendation", "")
            st.markdown(f"**{priority}: {issue}**")
            st.write(recommendation)

    # ---------- Job match ----------
    if result.get("job_match_score") is not None:
        st.divider()
        st.subheader("🎯 Job Description Match")

        missing_keywords = result.get("missing_keywords", [])

        if missing_keywords:
            st.markdown("**Missing or weak keywords/requirements:**")
            st.write(" • ".join(missing_keywords))
        else:
            st.success("No major missing keywords were identified.")

        st.caption(
            "Only add a keyword if it genuinely reflects your skills or experience."
        )

    # ---------- Recruiter ----------
    st.divider()
    st.subheader("👀 20-Second Recruiter Review")

    recruiter = result.get("recruiter_20_second_review", {})

    if recruiter.get("would_continue_reading") is True:
        st.success("Likely to continue reading")
    elif recruiter.get("would_continue_reading") is False:
        st.warning("The recruiter may not continue reading")
    else:
        st.info("Recruiter continuation assessment unavailable")

    st.write(recruiter.get("first_impression", ""))

    r1, r2 = st.columns(2)

    with r1:
        st.markdown("**What stands out**")
        for item in recruiter.get("what_stands_out", []):
            st.write(f"• {item}")

    with r2:
        st.markdown("**What gets overlooked**")
        for item in recruiter.get("what_gets_overlooked", []):
            st.write(f"• {item}")

    st.markdown(f"**Why:** {recruiter.get('reason', '')}")

    # ---------- Detailed checks ----------
    st.divider()
    st.subheader("🔎 Detailed Checks")

    tab1, tab2 = st.tabs(["Formatting", "Content"])

    with tab1:
        issues = result.get("formatting_issues", [])
        if issues:
            for issue in issues:
                st.warning(issue)
        else:
            st.success("No major formatting issues identified.")

    with tab2:
        issues = result.get("content_issues", [])
        if issues:
            for issue in issues:
                st.warning(issue)
        else:
            st.success("No major content issues identified.")

    # ---------- Rewrites ----------
    st.divider()
    st.subheader("✍️ Rewrite Suggestions")

    st.markdown("### Improved Professional Summary")
    st.info(result.get("rewritten_summary", ""))

    bullets = result.get("improved_bullets", [])

    if bullets:
        st.markdown("### Improved Resume Bullets")

        for i, bullet in enumerate(bullets, start=1):
            with st.expander(f"Suggestion {i}"):
                st.markdown("**Original**")
                st.write(bullet.get("original", ""))

                st.markdown("**Improved**")
                st.write(bullet.get("improved", ""))

                st.markdown("**Why it's better**")
                st.write(bullet.get("why", ""))

    st.divider()
    st.caption(
        "ResumeLens provides AI-generated guidance and an estimated ATS compatibility "
        "score. It does not represent the scoring system of any specific ATS platform."
    )
