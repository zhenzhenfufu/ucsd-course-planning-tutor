import streamlit as st
import pandas as pd
import json
from ai_advisor import get_ai_advice

st.set_page_config(layout="wide", page_title="UCSD Course Planner", page_icon="🔱")

st.markdown("""
    <style>
    .main { background-color: #f9fbfd; }
    .stButton>button { border-radius: 6px; font-weight: 600; }
    div[data-testid="stHorizontalBlock"] > div { min-height: 0; }
    </style>
""", unsafe_allow_html=True)


@st.cache_data
def load_data():
    with open("dsc_courses.json", "r", encoding="utf-8") as f:
        return json.load(f)


courses_data = load_data()
df = pd.DataFrame(courses_data)

DEPT_ORDER = ["DSC", "MATH", "CSE", "ECE", "COGS", "PHYS", "CHEM", "BIOL"]
DEPT_LABELS = {
    "DSC": "DSC", "MATH": "MATH", "CSE": "CSE", "ECE": "ECE",
    "COGS": "COGS", "PHYS": "PHYS", "CHEM": "CHEM", "BIOL": "BIOL",
}
all_depts_in_data = df["department"].unique().tolist()
DEPTS = [d for d in DEPT_ORDER if d in all_depts_in_data]

EDGES = [
    ("MATH 20A", "MATH 20B"), ("MATH 20B", "MATH 20C"),
    ("MATH 20B", "MATH 18"),
    ("MATH 20C", "MATH 180A"), ("MATH 20C", "MATH 189"),
    ("MATH 20C", "DSC 40A"), ("MATH 18", "DSC 40A"),
    ("MATH 20C", "DSC 120"), ("MATH 18", "DSC 120"),
    ("MATH 20C", "DSC 123A"), ("MATH 18", "DSC 123A"),
    ("MATH 20C", "ECE 101"), ("MATH 20C", "ECE 109"),
    ("MATH 18", "MATH 173A"), ("MATH 20C", "MATH 173A"),
    ("MATH 173A", "MATH 173B"), ("MATH 180A", "MATH 181A"),
    ("MATH 181A", "MATH 181B"), ("MATH 180A", "MATH 182"),
    ("MATH 180A", "DSC 155"), ("MATH 18", "DSC 155"),
    ("MATH 180A", "MATH 189"),
    ("DSC 10", "DSC 20"), ("DSC 10", "DSC 40A"), ("DSC 10", "DSC 80"),
    ("DSC 20", "DSC 30"),
    ("DSC 30", "DSC 40B"), ("DSC 40A", "DSC 40B"),
    ("DSC 40B", "DSC 100"), ("DSC 80", "DSC 100"),
    ("DSC 80", "DSC 106"), ("DSC 80", "DSC 120"),
    ("DSC 80", "DSC 140A"), ("DSC 80", "DSC 140B"), ("DSC 80", "DSC 148"),
    ("DSC 80", "DSC 160"), ("DSC 80", "DSC 167"), ("DSC 80", "DSC 170"),
    ("DSC 80", "DSC 161"),
    ("DSC 100", "DSC 102"), ("DSC 100", "DSC 104"),
    ("DSC 123A", "DSC 123B"),
    ("DSC 102", "DSC 180A"),
    ("DSC 140A", "DSC 180A"), ("DSC 140B", "DSC 180A"),
    ("DSC 148", "DSC 180A"), ("MATH 189", "DSC 180A"),
    ("DSC 180A", "DSC 180B"),
    ("CSE 11", "CSE 12"), ("CSE 12", "CSE 100"), ("CSE 100", "CSE 101"),
    ("CSE 12", "CSE 15L"), ("CSE 12", "CSE 103"),
    ("CSE 12", "CSE 151A"), ("MATH 18", "CSE 151A"), ("MATH 180A", "CSE 151A"),
    ("CSE 151A", "CSE 151B"),
    ("BILD 1", "BILD 2"), ("BILD 1", "BILD 3"),
    ("CHEM 6A", "CHEM 6B"), ("CHEM 6B", "CHEM 6C"),
    ("PHYS 2A", "PHYS 2B"), ("PHYS 2B", "PHYS 2C"),
    ("PHYS 4A", "PHYS 4B"), ("PHYS 4B", "PHYS 4C"),
]

prereqs_map: dict[str, list[str]] = {}
for src, dst in EDGES:
    prereqs_map.setdefault(dst, []).append(src)

QUARTERS = ["Fall", "Winter", "Spring", "Summer"]

RESOURCES = [
    {"category": "Enrollment", "icon": "📋", "color": "#e8f4fd", "border": "#2196F3", "links": [
        ("WebReg", "https://act.ucsd.edu/webreg2/start", "Official UCSD enrollment portal — add/drop courses, join waitlists, manage your schedule each quarter."),
        ("Schedule of Classes", "https://act.ucsd.edu/scheduleofclasses/scheduleofclassesindex.htm", "Browse every section offered in a given quarter with times, professors, locations, and seat availability."),
        ("Waitlist Guide", "https://students.ucsd.edu/academics/enroll/waitlist.html", "How UCSD waitlists work: auto-enroll thresholds, position checking, and what to do if you're stuck."),
    ]},
    {"category": "Grades & Reviews", "icon": "📊", "color": "#f0fdf4", "border": "#22c55e", "links": [
        ("CAPE Reviews", "https://cape.ucsd.edu/", "Student evaluations for every UCSD course and professor — workload, teaching quality, exam difficulty."),
        ("Capes GPA Tool", "https://capes.vercel.app/", "Visual grade distributions by professor sourced from CAPE data. Compare sections before enrolling."),
        ("Rate My Professors — UCSD", "https://www.ratemyprofessors.com/school/1078", "Professor ratings and reviews from students across all UCSD departments."),
    ]},
    {"category": "Degree Planning", "icon": "🎓", "color": "#fdf4ff", "border": "#a855f7", "links": [
        ("Degree Audit (DARS)", "https://act.ucsd.edu/studentDarsSelfservice/audit/read.html?printerFriendly=true", "Automated audit of your transcript — see exactly what requirements you've fulfilled and what's still missing."),
        ("Academic Calendar", "https://blink.ucsd.edu/instructors/resources/academic/calendars/", "Enrollment windows, add/drop deadlines, finals, and quarter dates. Bookmark this."),
        ("DSC Major Requirements", "https://datascience.ucsd.edu/current-students/course-information/", "Full list of required and elective courses for the BS in Data Science, including allowed substitutions."),
        ("DSC Course Catalog", "https://catalog.ucsd.edu/courses/DSC.html", "Official UCSD catalog with formal prerequisites, descriptions, and unit counts for all DSC courses."),
    ]},
    {"category": "Support & Advising", "icon": "💬", "color": "#fff7ed", "border": "#f97316", "links": [
        ("DSC Advising", "https://datascience.ucsd.edu/current-students/advising/", "Book an appointment with a DSC academic advisor for course selection, petitions, and graduation planning."),
        ("Triton Advising Hub", "https://advising.ucsd.edu/", "Central UCSD advising portal — college advisor, GE requirements, petitions, and academic standing."),
    ]},
]

if "plan" not in st.session_state:
    st.session_state.plan = {q: [] for q in QUARTERS}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "selected_course" not in st.session_state:
    st.session_state.selected_course = None
if "selected_dept" not in st.session_state:
    st.session_state.selected_dept = "DSC"


def all_selected() -> list[str]:
    return [c for q in QUARTERS for c in st.session_state.plan[q]]


col_left, col_mid, col_right = st.columns([0.25, 0.42, 0.33], gap="large")

# ── LEFT: Course Browser ──────────────────────────────────────────────────────
with col_left:
    st.subheader("📖 Courses")

    search = st.text_input("Search all departments", placeholder="e.g. probability, DSC 80", label_visibility="collapsed")

    if search:
        mask = (
            df["id"].str.contains(search, case=False)
            | df["name"].str.contains(search, case=False)
            | df["description"].str.contains(search, case=False)
        )
        results = df[mask]
        if results.empty:
            st.info("No courses match your search.")
        else:
            for _, row in results.iterrows():
                selected_marker = " ✓" if row["id"] in all_selected() else ""
                focused = row["id"] == st.session_state.selected_course
                btn_label = f"{'→ ' if focused else ''}{row['id']}{selected_marker}"
                if st.button(btn_label, key=f"s_{row['id']}", use_container_width=True):
                    st.session_state.selected_course = row["id"]
                    st.rerun()
                st.caption(f"{row['name'][:50]}{'…' if len(row['name'])>50 else ''} · {row['units']}u")
    else:
        dept_cols = st.columns(4)
        for i, dept in enumerate(DEPTS):
            with dept_cols[i % 4]:
                active = st.session_state.selected_dept == dept
                if st.button(dept, key=f"dept_{dept}", type="primary" if active else "secondary", use_container_width=True):
                    st.session_state.selected_dept = dept
                    st.rerun()

        dept_courses = df[df["department"] == st.session_state.selected_dept].reset_index(drop=True)

        for _, row in dept_courses.iterrows():
            selected_marker = " ✓" if row["id"] in all_selected() else ""
            focused = row["id"] == st.session_state.selected_course
            btn_label = f"{'→ ' if focused else ''}{row['id']}{selected_marker}"
            if st.button(btn_label, key=f"c_{row['id']}", use_container_width=True):
                st.session_state.selected_course = row["id"]
                st.rerun()
            st.caption(f"{row['name'][:52]}{'…' if len(row['name'])>52 else ''} · {row['units']}u")

# ── MIDDLE: Course Info Hub ───────────────────────────────────────────────────
with col_mid:
    if st.session_state.selected_course:
        match = df[df["id"] == st.session_state.selected_course]
        if match.empty:
            st.info("Course not found.")
        else:
            course = match.iloc[0]
            cid = course["id"]
            dept = course["department"]
            cid_url = cid.replace(" ", "+")
            cid_encoded = cid.replace(" ", "%20")
            links_dict = course.get("links") or {}
            site_url = links_dict.get("🌐 Course Site", "")

            # Header
            st.markdown(f"## {cid}")
            st.markdown(f"**{course['name']}** &nbsp;·&nbsp; {course['units']} units &nbsp;·&nbsp; `{dept}`")

            desc = course.get("description", "")
            if desc:
                st.write(desc)

            # Prerequisites
            prereqs = prereqs_map.get(cid, [])
            if prereqs:
                selected = all_selected()
                chips = []
                for p in prereqs:
                    met = p in selected
                    chips.append(f"{'✅' if met else '⬜'} {p}")
                st.markdown("**Prerequisites:** " + " &nbsp;·&nbsp; ".join(chips))

            # Courses this unlocks
            unlocks = [dst for (src, dst) in EDGES if src == cid]
            if unlocks:
                st.caption("Unlocks: " + " · ".join(unlocks))

            st.divider()

            # ── Link Hub ─────────────────────────────────────────────────────
            st.markdown("### 🔗 Course Info Hub")

            # Reviews & Grades
            st.markdown("#### 📊 Reviews & Grades")
            r1, r2, r3 = st.columns(3)
            with r1:
                st.markdown(
                    f"""<div style="background:#f0fdf4;border-left:3px solid #22c55e;border-radius:6px;padding:10px 12px">
                    <a href="https://cape.ucsd.edu/responses/Results.aspx?courseNumber={cid_url}" target="_blank"
                       style="font-weight:700;color:#15803d;text-decoration:none">📝 CAPE Reviews</a>
                    <p style="font-size:0.78rem;color:#444;margin-top:5px">Student evaluations — workload, exam difficulty, professor quality</p>
                    </div>""", unsafe_allow_html=True)
            with r2:
                st.markdown(
                    f"""<div style="background:#f0fdf4;border-left:3px solid #22c55e;border-radius:6px;padding:10px 12px">
                    <a href="https://capes.vercel.app/" target="_blank"
                       style="font-weight:700;color:#15803d;text-decoration:none">📈 Capes GPA</a>
                    <p style="font-size:0.78rem;color:#444;margin-top:5px">Grade distributions by professor — search "{cid}" on site</p>
                    </div>""", unsafe_allow_html=True)
            with r3:
                st.markdown(
                    f"""<div style="background:#f0fdf4;border-left:3px solid #22c55e;border-radius:6px;padding:10px 12px">
                    <a href="https://www.ratemyprofessors.com/school/1078" target="_blank"
                       style="font-weight:700;color:#15803d;text-decoration:none">⭐ Rate My Prof</a>
                    <p style="font-size:0.78rem;color:#444;margin-top:5px">UCSD professor ratings — search by professor name</p>
                    </div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Community
            st.markdown("#### 💬 Community")
            reddit_url = f"https://www.reddit.com/r/UCSD/search/?q={cid_encoded}&restrict_sr=1&sort=new"
            reddit_name_url = f"https://www.reddit.com/r/UCSD/search/?q={course['name'].split()[0:3]}&restrict_sr=1"
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(
                    f"""<div style="background:#fff7ed;border-left:3px solid #f97316;border-radius:6px;padding:10px 12px">
                    <a href="{reddit_url}" target="_blank"
                       style="font-weight:700;color:#c2410c;text-decoration:none">🟠 r/UCSD — {cid}</a>
                    <p style="font-size:0.78rem;color:#444;margin-top:5px">Student threads: tips, professor picks, workload reality, study groups</p>
                    </div>""", unsafe_allow_html=True)
            with c2:
                st.markdown(
                    f"""<div style="background:#fff7ed;border-left:3px solid #f97316;border-radius:6px;padding:10px 12px">
                    <a href="https://discord.gg/ucsd" target="_blank"
                       style="font-weight:700;color:#c2410c;text-decoration:none">💬 UCSD Discord</a>
                    <p style="font-size:0.78rem;color:#444;margin-top:5px">Live chat with UCSD students — find course-specific channels</p>
                    </div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Course Materials
            st.markdown("#### 📚 Materials")
            mat_cols = []
            if site_url:
                mat_cols.append(("🌐 Course Website", site_url, "Official site — syllabus, lecture notes, assignments, and past exams"))
            mat_cols.append(("📋 UCSD Catalog", f"https://catalog.ucsd.edu/courses/{dept}.html", f"Formal description and official prerequisite rules for {dept} courses"))
            youtube_url = f"https://www.youtube.com/results?search_query=UCSD+{cid_encoded}+lecture"
            mat_cols.append(("▶ YouTube Lectures", youtube_url, "Search for recorded lectures, review videos, or tutorial walkthroughs"))

            cols = st.columns(len(mat_cols))
            for col, (label, url, tip) in zip(cols, mat_cols):
                with col:
                    st.markdown(
                        f"""<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px 12px">
                        <a href="{url}" target="_blank"
                           style="font-weight:700;color:#1e40af;text-decoration:none">{label}</a>
                        <p style="font-size:0.78rem;color:#444;margin-top:5px">{tip}</p>
                        </div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # More Search Links
            st.markdown("#### 🔍 More")
            google_url = f"https://www.google.com/search?q=UCSD+{cid_encoded}+{course['name'].replace(' ', '+')}"
            scholar_url = f"https://scholar.google.com/scholar?q=UCSD+{cid_encoded}"
            s1, s2 = st.columns(2)
            with s1:
                st.markdown(
                    f"""<div style="background:#e8f4fd;border-left:3px solid #2196F3;border-radius:6px;padding:10px 12px">
                    <a href="{google_url}" target="_blank"
                       style="font-weight:700;color:#1565c0;text-decoration:none">🔎 Google Search</a>
                    <p style="font-size:0.78rem;color:#444;margin-top:5px">Search for past exams, cheat sheets, and student resources</p>
                    </div>""", unsafe_allow_html=True)
            with s2:
                st.markdown(
                    f"""<div style="background:#e8f4fd;border-left:3px solid #2196F3;border-radius:6px;padding:10px 12px">
                    <a href="{scholar_url}" target="_blank"
                       style="font-weight:700;color:#1565c0;text-decoration:none">📖 Google Scholar</a>
                    <p style="font-size:0.78rem;color:#444;margin-top:5px">Academic papers and research related to this course's topics</p>
                    </div>""", unsafe_allow_html=True)

            st.divider()

            # Add to Plan
            st.markdown("#### ➕ Add to My Plan")
            already = cid in all_selected()
            if already:
                st.success(f"{cid} is already in your plan ✓")
                for q in QUARTERS:
                    if cid in st.session_state.plan[q]:
                        st.caption(f"Added to: {q}")
            else:
                prereqs_missing = [p for p in prereqs if p not in all_selected() and not p.startswith("MATH")]
                if prereqs_missing:
                    st.warning(f"DSC prereqs not yet in plan: {', '.join(prereqs_missing)}", icon="⚠️")
                qa, qb = st.columns([0.6, 0.4])
                q_choice = qa.selectbox("Quarter", QUARTERS, label_visibility="collapsed")
                if qb.button("+ Add to Plan", type="primary"):
                    st.session_state.plan[q_choice].append(cid)
                    st.rerun()
    else:
        st.markdown("## Course Info Hub")
        st.info("← Click any course on the left to see reviews, links, Reddit discussions, and more.")

        # Show course websites as quick links
        sites = [(row["id"], row["name"], row["links"]["🌐 Course Site"])
                 for _, row in df.iterrows()
                 if isinstance(row.get("links"), dict) and "🌐 Course Site" in row["links"]]
        if sites:
            st.markdown("**Quick jump — course websites:**")
            for cid, name, url in sites:
                st.markdown(f"[{cid}: {name}]({url})")

# ── RIGHT: AI Advisor + My Plan ───────────────────────────────────────────────
with col_right:
    tab_ai, tab_plan, tab_res = st.tabs(["🤖 AI Advisor", "📅 My Plan", "🔗 Resources"])

    with tab_ai:
        chat_container = st.container(height=480)
        for m in st.session_state.messages:
            chat_container.chat_message(m["role"]).write(m["content"])

        if prompt := st.chat_input("Ask about courses, prerequisites, workload…"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            chat_container.chat_message("user").write(prompt)
            with chat_container.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    ans = get_ai_advice(
                        conversation_history=st.session_state.messages,
                        selected_courses=all_selected(),
                        courses_data=courses_data,
                    )
                st.markdown(ans)
            st.session_state.messages.append({"role": "assistant", "content": ans})

        if st.session_state.messages:
            if st.button("Clear Chat", key="clear_chat"):
                st.session_state.messages = []
                st.rerun()

    with tab_plan:
        q_tabs = st.tabs(QUARTERS + ["Overview"])

        for i, q in enumerate(QUARTERS):
            with q_tabs[i]:
                courses_here = st.session_state.plan[q]
                if courses_here:
                    q_rows = df[df["id"].isin(courses_here)]
                    for _, row in q_rows.iterrows():
                        ci, cb = st.columns([0.82, 0.18])
                        ci.markdown(f"**{row['id']}** · {row['units']}u")
                        ci.caption(row["name"][:44] + ("…" if len(row["name"]) > 44 else ""))
                        if cb.button("✕", key=f"rm_{q}_{row['id']}"):
                            st.session_state.plan[q].remove(row["id"])
                            st.rerun()
                    st.divider()
                    st.metric("Units", q_rows["units"].sum())
                else:
                    st.caption(f"No courses added to {q} yet.")

        with q_tabs[4]:
            all_c = all_selected()
            if all_c:
                for q in QUARTERS:
                    if st.session_state.plan[q]:
                        q_df = df[df["id"].isin(st.session_state.plan[q])]
                        st.markdown(f"**{q}**: {', '.join(st.session_state.plan[q])} — {q_df['units'].sum()} units")
                st.divider()
                st.metric("Total Units", df[df["id"].isin(all_c)]["units"].sum())
                issues = [
                    f"**{c}** needs {', '.join(m)}"
                    for c in all_c
                    if (m := [p for p in prereqs_map.get(c, []) if p.startswith("DSC") and p not in all_c])
                ]
                if issues:
                    st.warning("DSC prereq gaps:\n" + "\n".join(f"- {x}" for x in issues))
                else:
                    st.success("All DSC prerequisites covered ✓")
                if st.button("Clear All Plans"):
                    st.session_state.plan = {q: [] for q in QUARTERS}
                    st.rerun()
            else:
                st.caption("Add courses from the catalog to start planning.")

    with tab_res:
        st.markdown("### Quick Resources")
        for section in RESOURCES:
            st.markdown(f"**{section['icon']} {section['category']}**")
            for name, url, desc in section["links"]:
                st.markdown(
                    f"""<div style="background:{section['color']};border-left:3px solid {section['border']};
                    border-radius:5px;padding:8px 10px;margin-bottom:6px">
                    <a href="{url}" target="_blank" style="font-weight:700;color:#111;text-decoration:none">↗ {name}</a>
                    <p style="font-size:0.78rem;color:#444;margin:3px 0 0 0">{desc}</p>
                    </div>""", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

# ── BOTTOM: Full Resources (collapsed) ───────────────────────────────────────
with st.expander("🔗 Full Student Resources Hub", expanded=False):
    st.caption("All essential UCSD links in one place")
    for section in RESOURCES:
        cols = st.columns(len(section["links"]))
        st.markdown(f"**{section['icon']} {section['category']}**")
        for col, (name, url, desc) in zip(cols, section["links"]):
            with col:
                st.markdown(
                    f"""<div style="background:{section['color']};border-left:4px solid {section['border']};
                    border-radius:8px;padding:12px 14px;min-height:100px">
                    <a href="{url}" target="_blank" style="font-weight:700;font-size:0.95rem;color:#111;text-decoration:none">↗ {name}</a>
                    <p style="font-size:0.80rem;color:#444;margin-top:6px;line-height:1.4">{desc}</p>
                    </div>""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
