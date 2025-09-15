import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Construction Portfolio Dashboard", layout="wide")

FORMS_PATH = "data/Construction_Data_PM_Forms_All_Projects.csv"
TASKS_PATH = "data/Construction_Data_PM_Tasks_All_Projects.csv"

# ---- helpers ---------------------------------------------------------------

def first_present(df, candidates):
    """Return the first matching column (case-insensitive) from candidates, else None."""
    cols = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in cols:
            return cols[c.lower()]
    return None

@st.cache_data
def load_data():
    forms = pd.read_csv(FORMS_PATH)
    tasks = pd.read_csv(TASKS_PATH)

    # Try to parse dates if present
    for c in ["StartDate","EndDate","Created","Date","Created On","Opened","Reported"]:
        if c in forms.columns:
            with pd.option_context("mode.chained_assignment", None):
                forms[c] = pd.to_datetime(forms[c], errors="coerce")
        if c in tasks.columns:
            with pd.option_context("mode.chained_assignment", None):
                tasks[c] = pd.to_datetime(tasks[c], errors="coerce")

    return forms, tasks

forms, tasks = load_data()

st.title("Construction Portfolio Dashboard")

st.caption("Loaded files:")
st.write(f"• {FORMS_PATH}")
st.write(f"• {TASKS_PATH}")

# ---- column mapping (auto + override UI) -----------------------------------

# Candidate names for common concepts (case-insensitive)
FORM_NAME_CANDS    = ["ProjectName","Name","Title","Project"]
FORM_STATUS_CANDS  = ["Status","Report Forms Status","Report Status"]
FORM_OWNER_CANDS   = ["Owner","Department","Group","Report Forms Group","Report Group"]
FORM_PRIORITY_CANDS= ["Priority","Risk","Severity"]
FORM_BUDGET_CANDS  = ["Budget","Cost Budget","Planned Cost"]
FORM_SPENT_CANDS   = ["Spent","Actual Cost","Actuals","Cost Spent","Expenditure"]
FORM_ID_CANDS      = ["ProjectID","Ref","ID","Project Ref","Project"]

TASK_ID_CANDS      = ["TaskID","Ref","ID"]
TASK_NAME_CANDS    = ["TaskName","Description","Title","Activity"]
TASK_STATUS_CANDS  = ["Status","Report Status"]
TASK_PROJECT_LINK  = ["ProjectID","Project","project","Ref","Parent Ref","Parent"]

def auto_map_forms(df):
    return dict(
        proj_id   = first_present(df, FORM_ID_CANDS),
        proj_name = first_present(df, FORM_NAME_CANDS),
        status    = first_present(df, FORM_STATUS_CANDS),
        owner     = first_present(df, FORM_OWNER_CANDS),
        priority  = first_present(df, FORM_PRIORITY_CANDS),
        budget    = first_present(df, FORM_BUDGET_CANDS),
        spent     = first_present(df, FORM_SPENT_CANDS),
        start     = first_present(df, ["StartDate","Start","Begin"]),
        end       = first_present(df, ["EndDate","End","Finish"]),
        progress  = first_present(df, ["KPI_Progress","Progress","Percent Complete","% Complete","Completion"])
    )

def auto_map_tasks(df):
    return dict(
        task_id   = first_present(df, TASK_ID_CANDS),
        task_name = first_present(df, TASK_NAME_CANDS),
        status    = first_present(df, TASK_STATUS_CANDS),
        proj_link = first_present(df, TASK_PROJECT_LINK),
        start     = first_present(df, ["StartDate","Start","Begin"]),
        end       = first_present(df, ["EndDate","End","Finish"]),
        complete  = first_present(df, ["Completion","% Complete","Percent Complete","Progress"])
    )

fmap = auto_map_forms(forms)
tmap = auto_map_tasks(tasks)

with st.expander("Column mapping — adjust if needed"):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Forms mapping**")
        for k in fmap:
            fmap[k] = st.selectbox(f"Forms: {k}", [None] + list(forms.columns), index=( [None]+list(forms.columns) ).index(fmap[k]) if fmap[k] in forms.columns else 0)
    with col2:
        st.markdown("**Tasks mapping**")
        for k in tmap:
            tmap[k] = st.selectbox(f"Tasks: {k}", [None] + list(tasks.columns), index=( [None]+list(tasks.columns) ).index(tmap[k]) if tmap[k] in tasks.columns else 0)

# Derived convenience columns with safe fallbacks
def safe_col(df, key):
    return fmap.get(key) if fmap.get(key) in df.columns else None

def safe_col_t(df, key):
    return tmap.get(key) if tmap.get(key) in df.columns else None

forms_use = forms.copy()
tasks_use = tasks.copy()

# Budget and spent numeric conversions if present
for c in [safe_col(forms, "budget"), safe_col(forms, "spent")]:
    if c and c in forms_use.columns:
        with pd.option_context("mode.chained_assignment", None):
            forms_use[c] = pd.to_numeric(forms_use[c], errors="coerce")

# Simple variance and overbudget if we have both
if safe_col(forms, "budget") and safe_col(forms, "spent"):
    forms_use["Variance"] = forms_use[safe_col(forms,"spent")] - forms_use[safe_col(forms,"budget")]
    forms_use["OverBudget"] = forms_use["Variance"] > 0
else:
    forms_use["Variance"] = np.nan
    forms_use["OverBudget"] = False

# Progress normalization if present
if safe_col(forms,"progress"):
    with pd.option_context("mode.chained_assignment", None):
        forms_use["_progress"] = pd.to_numeric(forms_use[safe_col(forms,"progress")], errors="coerce")
else:
    forms_use["_progress"] = np.nan

# ---- filters ----------------------------------------------------------------

def get_unique(df, col):
    return sorted(df[col].dropna().astype(str).unique()) if col and col in df.columns else []

st.sidebar.header("Filters")
status_col  = safe_col(forms,"status")
owner_col   = safe_col(forms,"owner")
prio_col    = safe_col(forms,"priority")
name_col    = safe_col(forms,"proj_name")

status_sel = st.sidebar.multiselect("Status", get_unique(forms_use, status_col), default=get_unique(forms_use, status_col))
owner_sel  = st.sidebar.multiselect("Owner",  get_unique(forms_use, owner_col), default=get_unique(forms_use, owner_col))
prio_sel   = st.sidebar.multiselect("Priority", get_unique(forms_use, prio_col), default=get_unique(forms_use, prio_col))

filt = forms_use.copy()
if status_col:
    filt = filt[filt[status_col].astype(str).isin(status_sel)]
if owner_col:
    filt = filt[filt[owner_col].astype(str).isin(owner_sel)]
if prio_col:
    filt = filt[filt[prio_col].astype(str).isin(prio_sel)]

# ---- KPIs -------------------------------------------------------------------

k1, k2, k3, k4 = st.columns(4)
k1.metric("Projects", len(filt))
if safe_col(forms,"budget"):
    k2.metric("Total Budget", f"${filt[safe_col(forms,'budget')].sum():,.0f}")
else:
    k2.metric("Total Budget", "—")
if safe_col(forms,"spent"):
    k3.metric("Total Spent",  f"${filt[safe_col(forms,'spent')].sum():,.0f}")
else:
    k3.metric("Total Spent", "—")
k4.metric("Avg Progress", f"{filt['_progress'].mean():.1f}%" if filt['_progress'].notna().any() else "—")

# Optional over budget rate
if "OverBudget" in filt.columns:
    ob_rate = float(filt["OverBudget"].mean()*100) if len(filt)>0 else 0.0
    st.metric("Over Budget Rate", f"{ob_rate:.1f}%")

# ---- charts -----------------------------------------------------------------

if safe_col(forms,"budget") and safe_col(forms,"spent") and name_col:
    st.markdown("### Budget vs Spent by Project")
    fig_budget = px.bar(
        filt,
        x=name_col,
        y=[safe_col(forms,"budget"), safe_col(forms,"spent")],
        barmode="group",
        title="Budget vs Spent"
    )
    st.plotly_chart(fig_budget, use_container_width=True)

if name_col and status_col:
    st.markdown("### Project Progress")
    prog_df = filt.dropna(subset=["_progress"])
    if len(prog_df) > 0:
        fig_prog = px.bar(
            prog_df.sort_values("_progress", ascending=False),
            x=name_col,
            y="_progress",
            color=status_col,
            text="_progress",
            title="KPI or Progress %",
        )
        st.plotly_chart(fig_prog, use_container_width=True)

if safe_col(forms,"owner") and safe_col(forms,"budget"):
    st.markdown("### Budget Allocation by Owner")
    fig_owner = px.pie(
        filt,
        names=safe_col(forms,"owner"),
        values=safe_col(forms,"budget"),
        hole=0.3,
        title="Budget Allocation by Owner"
    )
    st.plotly_chart(fig_owner, use_container_width=True)

# ---- table ------------------------------------------------------------------

cols_for_table = [c for c in [
    safe_col(forms,"proj_id"),
    name_col,
    safe_col(forms,"owner"),
    status_col,
    prio_col,
    safe_col(forms,"budget"),
    safe_col(forms,"spent"),
    "Variance"
] if c and c in filt.columns or c in ["Variance"]]

st.markdown("### Portfolio Table")
st.dataframe(filt[cols_for_table].sort_values(by=[status_col, prio_col, name_col], na_position="last") if len(cols_for_table)>0 else filt)

# ---- drilldown --------------------------------------------------------------

st.markdown("## Project Drilldown")

# Choose join keys between forms and tasks
st.caption("If drilldown is empty, try different join keys below.")
left_key = st.selectbox("Forms project key", [fmap["proj_id"], fmap["proj_name"], "Ref", "Project", "Name", None])
right_key = st.selectbox("Tasks project link", [tmap["proj_link"], "project", "Project", "Ref", None])

# Project selector
if name_col:
    project_choice = st.selectbox("Select a project", sorted(filt[name_col].dropna().astype(str).unique()))
    left_row = filt[filt[name_col].astype(str) == project_choice].head(1)
else:
    st.info("Project name column not found. Set it in the mapping above.")
    project_choice = None
    left_row = pd.DataFrame()

if project_choice and left_key and right_key and left_key in filt.columns and right_key in tasks_use.columns:
    left_val = left_row.iloc[0][left_key]
    proj_tasks = tasks_use[tasks_use[right_key].astype(str) == str(left_val)].copy()

    # Build a Gantt if we have dates and task name
    task_name = tmap["task_name"]
    t_start   = tmap["start"]
    t_end     = tmap["end"]
    t_comp    = tmap["complete"]

    st.subheader(f"Tasks for {project_choice}")

    if task_name and t_start and t_end and all(c in proj_tasks.columns for c in [task_name, t_start, t_end]):
        # Compute durations and basic slip
        with pd.option_context("mode.chained_assignment", None):
            proj_tasks["PlannedDays"] = pd.to_numeric(proj_tasks.get("PlannedDays", np.nan), errors="coerce")
            proj_tasks["ActualDays"]  = pd.to_numeric(proj_tasks.get("ActualDays", np.nan), errors="coerce")
            if proj_tasks["ActualDays"].isna().all():
                proj_tasks["ActualDays"] = (pd.to_datetime(proj_tasks[t_end], errors="coerce") - pd.to_datetime(proj_tasks[t_start], errors="coerce")).dt.days
            if proj_tasks["PlannedDays"].isna().all():
                proj_tasks["PlannedDays"] = proj_tasks["ActualDays"]

            proj_tasks["ScheduleSlip"] = proj_tasks["ActualDays"] > proj_tasks["PlannedDays"] * 1.1

        fig = px.timeline(
            proj_tasks,
            x_start=t_start,
            x_end=t_end,
            y=task_name,
            color=t_comp if t_comp and t_comp in proj_tasks.columns else None,
            title="Task Timeline",
        )
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

        show_cols = [c for c in [tmap["task_id"], task_name, t_comp, "PlannedDays", "ActualDays", "ScheduleSlip", tmap["status"]] if c and c in proj_tasks.columns]
        st.dataframe(proj_tasks[show_cols].sort_values(by=[tmap["status"], task_name], na_position="last") if len(show_cols)>0 else proj_tasks)
    else:
        st.info("Set task name and date columns in the mapping above to see the Gantt chart.")
else:
    st.caption("Set join keys that match a common value between forms and tasks, for example Forms.Ref ↔ Tasks.project.")
