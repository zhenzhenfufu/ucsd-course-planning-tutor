import streamlit as st
import pandas as pd
import json
from ai_advisor import get_ai_advice

st.set_page_config(layout="wide", page_title="UCSD DSC Course Planner", page_icon="🔱")

st.markdown("""
    <style>
    .main { background-color: #f9fbfd; }
    .stButton>button { border-radius: 6px; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)


@st.cache_data
def load_data():
    with open('dsc_courses.json', 'r', encoding='utf-8') as f:
        return json.load(f)


courses_data = load_data()
df = pd.DataFrame(courses_data)

EDGES = [
    # Math prereqs
    ("MATH 18",  "DSC 40A"), ("MATH 20C", "DSC 40A"),
    ("MATH 18",  "DSC 120"),  ("MATH 20C", "DSC 120"),
    ("MATH 18",  "DSC 123A"), ("MATH 20C", "DSC 123A"),
    ("MATH 18",  "DSC 155"),  ("MATH 180A", "DSC 155"),
    # Lower division sequence
    ("DSC 10",  "DSC 20"),   ("DSC 10",  "DSC 40A"), ("DSC 10",  "DSC 80"),
    ("DSC 20",  "DSC 30"),
    ("DSC 30",  "DSC 40B"),  ("DSC 40A", "DSC 40B"),
    # Upper division
    ("DSC 40B", "DSC 100"),  ("DSC 80",  "DSC 100"),
    ("DSC 80",  "DSC 106"),
    ("DSC 80",  "DSC 120"),
    ("DSC 80",  "DSC 140A"), ("DSC 80",  "DSC 140B"),
    ("DSC 80",  "DSC 148"),
    ("DSC 80",  "DSC 160"),  ("DSC 80",  "DSC 167"), ("DSC 80",  "DSC 170"),
    ("DSC 100", "DSC 102"),  ("DSC 100", "DSC 104"),
    ("DSC 123A","DSC 123B"),
    ("DSC 102", "DSC 180A"), ("DSC 140A","DSC 180A"), ("DSC 140B","DSC 180A"),
    ("DSC 180A","DSC 180B"),
]

prereqs_map: dict[str, list[str]] = {}
for src, dst in EDGES:
    prereqs_map.setdefault(dst, []).append(src)

QUARTERS = ["Fall", "Winter", "Spring", "Summer"]

RESOURCES = [
    {
        "category": "Enrollment",
        "icon": "📋",
        "color": "#e8f4fd",
        "border": "#2196F3",
        "links": [
            (
                "WebReg",
                "https://act.ucsd.edu/webreg2/start",
                "The official UCSD enrollment portal. Use this to add/drop courses, join waitlists, and manage your schedule each quarter. Opens during your enrollment appointment.",
            ),
            (
                "Schedule of Classes",
                "https://act.ucsd.edu/scheduleofclasses/scheduleofclassesindex.htm",
                "Browse every section offered in a given quarter — see times, professors, room locations, and available seats before enrollment opens.",
            ),
            (
                "Waitlist Guide",
                "https://students.ucsd.edu/academics/enroll/waitlist.html",
                "Explains how UCSD waitlists work: when you get automatically enrolled, how to check your position, and what to do if you're stuck on a waitlist.",
            ),
        ],
    },
    {
        "category": "Grades & Reviews",
        "icon": "📊",
        "color": "#f0fdf4",
        "border": "#22c55e",
        "links": [
            (
                "CAPE Reviews",
                "https://cape.ucsd.edu/",
                "Student-written evaluations for every UCSD course and professor. Read honest feedback on workload, teaching quality, and exam difficulty before you enroll.",
            ),
            (
                "Capes GPA Tool",
                "https://capes.vercel.app/",
                "Visual grade distribution charts sourced from CAPE data. Shows the average GPA and grade breakdown for each professor — useful for comparing sections of the same course.",
            ),
        ],
    },
    {
        "category": "Degree Planning",
        "icon": "🎓",
        "color": "#fdf4ff",
        "border": "#a855f7",
        "links": [
            (
                "Degree Audit (DARS)",
                "https://act.ucsd.edu/studentDarsSelfservice/audit/read.html?printerFriendly=true",
                "Run an automated audit of your transcript against your major requirements. Shows exactly which requirements you've fulfilled, which are in progress, and what's still missing.",
            ),
            (
                "Academic Calendar",
                "https://blink.ucsd.edu/instructors/resources/academic/calendars/",
                "Official dates for enrollment windows, add/drop deadlines, finals, holidays, and quarter start/end dates. Bookmark this to never miss a deadline.",
            ),
            (
                "DSC Major Requirements",
                "https://datascience.ucsd.edu/current-students/course-information/",
                "The complete list of courses required to graduate with a BS in Data Science. Includes lower-division, upper-division, and elective requirements with allowed substitutions.",
            ),
            (
                "DSC Course Catalog",
                "https://catalog.ucsd.edu/courses/DSC.html",
                "Official UCSD catalog listing every DSC course with formal descriptions, unit counts, and prerequisite rules. The authoritative source if you need to verify a prereq.",
            ),
        ],
    },
    {
        "category": "Support & Advising",
        "icon": "💬",
        "color": "#fff7ed",
        "border": "#f97316",
        "links": [
            (
                "DSC Advising",
                "https://datascience.ucsd.edu/current-students/advising/",
                "Schedule a meeting with a DSC academic advisor for personalized guidance on course selection, major requirements, petitions, and graduation planning.",
            ),
            (
                "Triton Advising Hub",
                "https://advising.ucsd.edu/",
                "UCSD's central advising portal. Find your college advisor, submit petitions, and get help with general education requirements and academic standing issues.",
            ),
        ],
    },
]

if "plan" not in st.session_state:
    st.session_state.plan = {q: [] for q in QUARTERS}
if "messages" not in st.session_state:
    st.session_state.messages = []


def all_selected() -> list[str]:
    return [c for q in QUARTERS for c in st.session_state.plan[q]]


col_left, col_mid, col_right = st.columns([0.30, 0.38, 0.32], gap="large")

# ── LEFT: Course Catalog ──────────────────────────────────────────────────────
with col_left:
    st.subheader("📖 Course Catalog")

    search = st.text_input("Search", placeholder="Code or keyword (e.g. DSC 80, machine learning)", label_visibility="collapsed")
    f1, f2 = st.columns(2)
    div_filter = f1.selectbox("Division", ["All", "Lower Div", "Upper Div", "Prereqs"], label_visibility="collapsed")
    unit_filter = f2.selectbox("Units", ["All units", "2 units", "4 units"], label_visibility="collapsed")

    filtered = df.copy()
    if search:
        mask = (
            df["id"].str.contains(search, case=False)
            | df["name"].str.contains(search, case=False)
            | df["description"].str.contains(search, case=False)
        )
        filtered = df[mask]
    if div_filter == "Lower Div":
        filtered = filtered[filtered["division"] == "lower"]
    elif div_filter == "Upper Div":
        filtered = filtered[filtered["division"] == "upper"]
    elif div_filter == "Prereqs":
        filtered = filtered[filtered["division"].isin(["prerequisite", "math"])]
    if unit_filter != "All units":
        u = int(unit_filter.split()[0])
        filtered = filtered[filtered["units"] == u]

    selected = all_selected()

    for _, row in filtered.iterrows():
        already = row["id"] in selected
        all_prereqs_missing = [p for p in prereqs_map.get(row["id"], []) if p not in selected]
        dsc_missing = [p for p in all_prereqs_missing if p.startswith("DSC")]

        label = f"{'✓ ' if already else ''}{row['id']} · {row['units']} units"
        with st.expander(label):
            st.markdown(f"**{row['name']}**")

            desc = row.get("description", "")
            if desc:
                st.caption(desc[:220] + ("…" if len(desc) > 220 else ""))

            stats = row.get("stats") or {}
            if stats:
                m1, m2, m3 = st.columns(3)
                m1.metric("Avg GPA", stats.get("Average GPA", "—"))
                m2.metric("Hrs/Wk", stats.get("Hours/Week", "—"))
                m3.metric("Difficulty", f"{stats.get('Content Difficulty', '—')}/100")

            if dsc_missing:
                st.warning(f"Missing prereqs: {', '.join(dsc_missing)}", icon="⚠️")

            # ── Course Info Hub ──────────────────────────────────────────
            cid_url = row["id"].replace(" ", "+")
            cid_plain = row["id"].replace(" ", "%20")
            course_links = row.get("links") or {}
            site_url = course_links.get("🌐 Course Site", "")

            with st.expander("🔍 Course Info Hub", expanded=False):
                # Reviews & Grades
                st.markdown("**📊 Reviews & Grades**")
                st.markdown(
                    f"[CAPE Reviews](https://cape.ucsd.edu/responses/Results.aspx?courseNumber={cid_url}) "
                    f"— Student evaluations: workload, professor quality, exam difficulty"
                )
                st.markdown(
                    f"[Capes GPA Tool](https://capes.vercel.app/) "
                    f"— Historical grade distributions by professor section"
                )

                # Community
                st.markdown("**💬 Community**")
                reddit_url = f"https://www.reddit.com/r/UCSD/search/?q={cid_plain}&restrict_sr=1&sort=new"
                st.markdown(
                    f"[r/UCSD — {row['id']} discussions]({reddit_url}) "
                    f"— Student threads: tips, professor recommendations, workload reality"
                )

                # Course materials
                st.markdown("**📚 Course Materials**")
                st.markdown(
                    f"[Official Catalog](https://catalog.ucsd.edu/courses/DSC.html) "
                    f"— Formal prerequisites and course description"
                )
                if site_url:
                    st.markdown(
                        f"[Course Website]({site_url}) "
                        f"— Syllabus, lecture notes, past assignments"
                    )
                youtube_url = f"https://www.youtube.com/results?search_query=UCSD+{cid_plain}"
                st.markdown(
                    f"[YouTube — UCSD {row['id']}]({youtube_url}) "
                    f"— Recorded lectures or tutorial videos"
                )

            # Add to plan
            if already:
                st.success("Already in your plan ✓")
            else:
                q_choice = st.selectbox("Add to quarter:", QUARTERS, key=f"q_{row['id']}")
                if st.button(f"+ Add to {q_choice}", key=f"add_{row['id']}"):
                    st.session_state.plan[q_choice].append(row["id"])
                    st.rerun()

# ── MIDDLE: Quarter Planner ───────────────────────────────────────────────────
with col_mid:
    st.subheader("📅 Quarter Planner")

    q_tabs = st.tabs(QUARTERS + ["Overview"])

    for i, q in enumerate(QUARTERS):
        with q_tabs[i]:
            courses_here = st.session_state.plan[q]
            if courses_here:
                q_rows = df[df["id"].isin(courses_here)]
                for _, row in q_rows.iterrows():
                    c_info, c_btn = st.columns([0.82, 0.18])
                    name_short = row["name"][:42] + ("…" if len(row["name"]) > 42 else "")
                    c_info.markdown(f"**{row['id']}** — {name_short}")
                    hrs = (row.get("stats") or {}).get("Hours/Week", "?")
                    c_info.caption(f"{row['units']} units · {hrs} hrs/wk")
                    if c_btn.button("✕", key=f"rm_{q}_{row['id']}"):
                        st.session_state.plan[q].remove(row["id"])
                        st.rerun()

                st.divider()
                total_units = q_rows["units"].sum()
                total_hrs = sum(
                    (row.get("stats") or {}).get("Hours/Week", 0)
                    for _, row in q_rows.iterrows()
                )
                cu, ch = st.columns(2)
                cu.metric("Units", total_units)
                ch.metric("Hrs/Week", total_hrs)
                if total_units > 20:
                    st.warning("Heavy quarter — consider reducing units.")
            else:
                st.info(f"No courses added to {q} yet.")

    with q_tabs[4]:  # Overview
        all_c = all_selected()
        if all_c:
            for q in QUARTERS:
                if st.session_state.plan[q]:
                    q_df = df[df["id"].isin(st.session_state.plan[q])]
                    units = q_df["units"].sum()
                    st.markdown(f"**{q}**: {', '.join(st.session_state.plan[q])} — {units} units")

            st.divider()
            all_df = df[df["id"].isin(all_c)]
            st.metric("Total Planned Units", all_df["units"].sum())

            issues = [
                f"**{c}** needs {', '.join(missing)}"
                for c in all_c
                if (missing := [
                    p for p in prereqs_map.get(c, [])
                    if p.startswith("DSC") and p not in all_c
                ])
            ]
            if issues:
                st.warning("Prerequisite gaps:\n" + "\n".join(f"- {x}" for x in issues))
            else:
                st.success("All DSC prerequisites covered!")

            if st.button("Clear All Plans"):
                st.session_state.plan = {q: [] for q in QUARTERS}
                st.rerun()
        else:
            st.info("Add courses from the catalog to start planning.")

# ── RIGHT: AI Advisor ────────────────────────────────────────────────────────
with col_right:
    st.subheader("🤖 AI Advisor")
    chat_container = st.container(height=520)
    for m in st.session_state.messages:
        chat_container.chat_message(m["role"]).write(m["content"])

    if prompt := st.chat_input("Ask about courses, workload, prerequisites…"):
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

# ── FULL-WIDTH: Resources Hub ─────────────────────────────────────────────────
st.divider()
st.markdown("## 🔗 Student Resources Hub")
st.caption("Everything you need to plan, enroll, and track your UCSD Data Science degree — in one place.")

for section in RESOURCES:
    icon = section["icon"]
    category = section["category"]
    color = section["color"]
    border = section["border"]
    links = section["links"]

    st.markdown(f"### {icon} {category}")
    cols = st.columns(len(links))
    for col, (name, url, desc) in zip(cols, links):
        with col:
            st.markdown(
                f"""
                <div style="
                    background:{color};
                    border-left: 4px solid {border};
                    border-radius: 8px;
                    padding: 14px 16px;
                    height: 100%;
                    min-height: 120px;
                ">
                    <a href="{url}" target="_blank" style="
                        font-weight: 700;
                        font-size: 1rem;
                        color: #111;
                        text-decoration: none;
                    ">↗ {name}</a>
                    <p style="font-size: 0.82rem; color: #444; margin-top: 8px; line-height: 1.45;">{desc}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown("<br>", unsafe_allow_html=True)

# Course websites row
course_sites = [
    (row["id"], row["name"], row["links"]["🌐 Course Site"])
    for _, row in df.iterrows()
    if isinstance(row.get("links"), dict) and "🌐 Course Site" in row["links"]
]
if course_sites:
    st.markdown("### 🌐 Course Websites")
    st.caption("Official websites maintained by UCSD DSC instructors, with notes, slides, and assignments.")
    site_cols = st.columns(len(course_sites))
    for col, (cid, cname, url) in zip(site_cols, course_sites):
        with col:
            st.markdown(
                f"""
                <div style="
                    background: #f8fafc;
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                    padding: 12px 14px;
                    text-align: center;
                ">
                    <a href="{url}" target="_blank" style="font-weight: 700; color: #184073; text-decoration: none;">
                        {cid}
                    </a>
                    <p style="font-size: 0.78rem; color: #666; margin-top: 4px;">{cname[:40]}{"…" if len(cname) > 40 else ""}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
