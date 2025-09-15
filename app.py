import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Construction Portfolio Dashboard", layout="wide")

FORMS_PATH = "data/Construction_Data_PM_Forms_All_Projects.csv"
TASKS_PATH = "data/Construction_Data_PM_Tasks_All_Projects.csv"

# ------------------------------- Utilities ---------------------------------- #

def first_present(df: pd.DataFrame, candidates):
    """Return the first matching column name (case-insensitive) from candidates, else None."""
    colmap = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c and c.lower() in colmap:
            return colmap[c.lower()]
    return None

def to_numeric_inplace(df: pd.DataFrame, col: str):
    if col and col in df.columns:
        with pd.option_context("mode.chained_assignment", None):
            df[col] = pd.to_numeric(df[col], errors="coerce")

def to_datetime_inplace(df: pd.DataFrame, col: str):
    if col and col in df.columns:
        with pd.option_context("mode.chained_assignment", None):
            df[col] = pd.to_datetime(df[col], errors="coerce")

def safe_get(df: pd.DataFrame, col: str, default=np.nan):
    if col and col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)

def _selectbox_with_default(label, options, default):
    opts = [None] + list(options)
    try:
        idx = opts.index(default) if default in opts else 0
    except ValueError:
        idx = 0
    return st.selectbox(label, opts, index=idx)

@st.cache_data
def load_data(forms_path: str, tasks_path: str):
    forms = pd.read_csv(forms_path)
    tasks = pd.read_csv(tasks_path)

    # Parse any date-like fields we might encounter
    date_like = ["StartDate", "EndDate", "Created", "Date", "Created On", "Opened", "Reported"]
    for c in date_like:
        to_datetime_inplace(forms, c)
        to_datetime_inplace(tasks, c)

    return forms, tasks

# ----------------------- Load and initial auto-mapping ---------------------- #

forms, tasks = load_data(FORMS_PATH, TASKS_PATH)

st.title("Construction Portfolio Dashboard")
st.caption("Loaded files:")
st.write(f"• {FORMS_PATH}")
st.write(f"• {TASKS_PATH}")

# Candidates for column mapping (case-insensitive)
FORM_NAME_CANDS     = ["ProjectName", "Name", "Title", "Project"]
FORM_STATUS_CANDS   = ["Status", "Report Forms Status", "Report Status"]
FORM_OWNER_CANDS    = ["Owner", "Department", "Group", "Report Forms Group", "Report Group"]
FORM_PRIORITY_CANDS = ["Priority", "Risk", "Severity"]
FORM_BUDGET_CANDS   = ["Budget", "Cost Budget", "Planned Cost", "Total Budget"]
FORM_SPENT_CANDS    = ["Spent", "Actual Cost", "Actuals", "Cost Spent", "Expenditure"]
FORM_ID_CANDS       = ["ProjectID", "Ref", "ID", "Project Ref", "Project"]

TASK_ID_CANDS       = ["TaskID", "Ref", "ID"]
TASK_NAME_CANDS     = ["TaskName", "Description", "Title", "Activity"]
TASK_STATUS_CANDS   = ["Status", "Report Status"]
TASK_PROJECT_LINK   = ["ProjectID", "Project", "project", "Ref", "Parent Ref", "Parent"]
TASK_COMPLETE_CANDS = ["Completion", "% Complete", "Percent Complete", "Progress"]

def auto_map_forms(df: pd.DataFrame):
    return dict(
        proj_id   = first_present(df, FORM_ID_CANDS),
        proj_name = first_present(df, FORM_NAME_CANDS),
        status    = first_present(df, FORM_STATUS_CANDS),
        owner     = first_present(df, FORM_OWNER_CANDS),
        priority  = first_present(df, FORM_PRIORITY_CANDS),
        budget    = first_present(df, FORM_BUDGET_CANDS),
        spent     = first_present(df, FORM_SPENT_CANDS),
        start     = first_present(df, ["StartDate", "Start", "Begin"]),
        end       = first_present(df, ["EndDate", "End", "Finish"]),
        progress  = first_present(df, ["KPI_Progress", "Progress", "Percent Complete", "% Complete", "Completion"]),
    )

def auto_map_tasks(df: pd.DataFrame):
    return dict(
        task_id   = first_present(df, TASK_ID_CANDS),
        task_name = first_present(df, TASK_NAME_CANDS),
        status    = first_present(df, TASK_STATUS_CANDS),
        proj_link = first_present(df, TASK_PROJECT_LINK),
        start     = first_present(df, ["StartDate", "Start", "Begin"]),
        end       = first_present(df, ["EndDate", "End", "Finish"]),
        complete  = first_present(df, TASK_COMPLETE_CANDS),
    )

fmap = auto_map_forms(forms)
tmap = auto_map_tasks(tasks)

with st.expander("Column mapping — adjust if needed"):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Forms mapping**")
        for key in list(fmap.keys()):
            fmap[key] = _selectbox_with_default(f"Forms: {key}", forms.columns, fmap[key])
    with col2:
        st.markdown("**Tasks mapping**")
        for key in list(tmap.keys()):
            tmap[key] = _selectbox_with_default(f"Tasks: {key}", tasks.columns, tmap[key])

# Convenience getters
def fcol(key):  # forms col
    val = fmap.get(key)
    return val if val in forms.columns else None

def tcol(key):  # tasks col
    val = tmap.get(key)
    return val if val in tasks.columns else None

# ------------------------------ Derivations --------------------------------- #

forms_use = forms.copy()
tasks_use = tasks.copy()

# Numeric conversions
to_numeric_inplace(forms_use, fcol("budget"))
to_numeric_inplace(forms_use, fcol("spent"))
to_numeric_inplace(forms_use, fcol("progress"))

# Variance and OverBudget if possible
if fcol("budget") and fcol("spent"):
    with pd.option_context("mode.chained_assignment", None):
        forms_use["Variance"] = forms_use[fcol("spent")] - forms_use[fcol("budget")]
        forms_use["OverBudget"] = forms_use["Variance"] > 0
else:
    forms_use["Variance"] = np.nan
    forms_use["OverBudget"] = False

# Progress normalized into _progress
with pd.option_context("mode.chained_assignment", None):
    forms_use["_progress"] = pd.to_numeric(safe_get(forms_use, fcol("progress")), errors="coerce")

# If tasks have no planned or actual days, compute from dates
if tcol("start") and tcol("end"):
    with pd.option_context("mode.chained_assignment", None):
        to_datetime_inplace(tasks_use, tcol("start"))
        to_datetime_inplace(tasks_use, tcol("end"))
        if "ActualDays" not in tasks_use.columns or tasks_use["ActualDays"].isna().all():
            tasks_use["ActualDays"] = (tasks_use[tcol("end")] - tasks_use[tcol("start")]).dt.days
        if "PlannedDays" not in tasks_use.columns or tasks_use["PlannedDays"].isna().all():
            # fallback: assume planned equals actual if not provided
            tasks_use["PlannedDays"] = tasks_use["ActualDays"]
        # schedule slip if actual > 110% planned
        tasks_use["ScheduleSlip"] = tasks_use["ActualDays"] > tasks_use["PlannedDays"] * 1.1
else:
    tasks_use["ActualDays"] = np.nan
    tasks_use["PlannedDays"] = np.nan
    tasks_use["ScheduleSlip"] = False

# ------------------------------- Filters ------------------------------------ #

st.sidebar.header("Filters")
status_vals = sorted(forms_use[fcol("status")].dropna().astype(str).unique()) if fcol("status") else []
owner_vals  = sorted(forms_use[fcol("owner")].dropna().astype(str).unique()) if fcol("owner") else []
prio_vals   = sorted(forms_use[fcol("priority")].dropna().astype(str).unique()) if fcol("priority") else []

status_sel = st.sidebar.multiselect("Status", status_vals, default=status_vals)
owner_sel  = st.sidebar.multiselect("Owner", owner_vals, default=owner_vals)
prio_sel   = st.sidebar.multiselect("Priority", prio_vals, default=prio_vals)

filt = forms_use.copy()
if fcol("status"):
    filt = filt[filt[fcol("status")].astype(str).isin(status_sel)]
if fcol("owner"):
    filt = filt[filt[fcol("owner")].astype(str).isin(owner_sel)]
if fcol("priority"):
    filt = filt[filt[fcol("priority")].astype(str).isin(prio_sel)]

# ---------------------------------- KPIs ------------------------------------ #

k1, k2, k3, k4 = st.columns(4)
k1.metric("Projects", len(filt))
if fcol("budget"):
    k2.metric("Total Budget", f"${filt[fcol('budget')].sum():,.0f}")
else:
    k2.metric("Total Budget", "—")
if fcol("spent"):
    k3.metric("Total Spent", f"${filt[fcol('spent')].sum():,.0f}")
else:
    k3.metric("Total Spent", "—")
if filt["_progress"].notna().any():
    k4.metric("Avg Progress", f"{filt['_progress'].mean():.1f}%")
else:
    k4.metric("Avg Progress", "—")

if "OverBudget" in filt.columns:
    ob_rate = float(filt["OverBudget"].mean() * 100) if len(filt) else 0.0
    st.metric("Over Budget Rate", f"{ob_rate:.1f}%")

# --------------------------------- Charts ----------------------------------- #

# Budget vs Spent
if fcol("budget") and fcol("spent") and fcol("proj_name"):
    st.markdown("### Budget vs Spent by Project")
    fig_budget = px.bar(
        filt,
        x=fcol("proj_name"),
        y=[fcol("budget"), fcol("spent")],
        barmode="group",
        title="Budget vs Spent",
    )
    st.plotly_chart(fig_budget, use_container_width=True)

# Progress chart
if fcol("proj_name") and fcol("status"):
    st.markdown("### Project Progress")
    prog_df = filt.dropna(subset=["_progress"])
    if len(prog_df) > 0:
        fig_prog = px.bar(
            prog_df.sort_values("_progress", ascending=False),
            x=fcol("proj_name"),
            y="_progress",
            color=fcol("status"),
            text="_progress",
            title="KPI or Progress %",
        )
        st.plotly_chart(fig_prog, use_container_width=True)

# Owner budget allocation
if fcol("owner") and fcol("budget"):
    st.markdown("### Budget Allocation by Owner")
    fig_owner = px.pie(
        filt,
        names=fcol("owner"),
        values=fcol("budget"),
        hole=0.3,
        title="Budget Allocation by Owner",
    )
    st.plotly_chart(fig_owner, use_container_width=True)

# --------------------------------- Table ------------------------------------ #

st.markdown("### Portfolio Table")

# Build display columns safely
cols_for_table = []
for c in [
    fcol("proj_id"),
    fcol("proj_name"),
    fcol("owner"),
    fcol("status"),
    fcol("priority"),
    fcol("budget"),
    fcol("spent"),
    "Variance",
]:
    if c is None:
        continue
    if c == "Variance" or c in filt.columns:
        cols_for_table.append(c)

df_to_show = filt[cols_for_table] if cols_for_table else filt

# Sort only by columns that exist
sort_cols = [c for c in [fcol("status"), fcol("priority"), fcol("proj_name")] if c and c in df_to_show.columns]
if sort_cols:
    df_to_show = df_to_show.sort_values(by=sort_cols, na_position="last")

st.dataframe(df_to_show)

# ------------------------------- Drilldown ---------------------------------- #

st.markdown("## Project Drilldown")

left_key = st.selectbox(
    "Forms project key",
    [fcol("proj_id"), fcol("proj_name"), "Ref", "Project", "Name", None],
)
right_key = st.selectbox(
    "Tasks project link",
    [tcol("proj_link"), "project", "Project", "Ref", None],
)

if fcol("proj_name"):
    project_names = sorted(filt[fcol("proj_name")].dropna().astype(str).unique())
    if project_names:
        project_choice = st.selectbox("Select a project", project_names)
        left_row = filt[filt[fcol("proj_name")].astype(str) == project_choice].head(1)
    else:
        st.info("No projects available after filters.")
        left_row = pd.DataFrame()
        project_choice = None
else:
    st.info("Project name column not found. Set it in the mapping above.")
    left_row = pd.DataFrame()
    project_choice = None

if project_choice and left_key and right_key and left_key in filt.columns and right_key in tasks_use.columns:
    left_val = left_row.iloc[0][left_key]
    proj_tasks = tasks_use[tasks_use[right_key].astype(str) == str(left_val)].copy()

    st.subheader(f"Tasks for {project_choice}")

    # Build timeline if we have required fields
    if tcol("task_name") and tcol("start") and tcol("end") and all(c in proj_tasks.columns for c in [tcol("task_name"), tcol("start"), tcol("end")]):
        # Ensure planned/actual and slip flags are present
        with pd.option_context("mode.chained_assignment", None):
            proj_tasks["PlannedDays"] = pd.to_numeric(proj_tasks.get("PlannedDays", np.nan), errors="coerce")
            proj_tasks["ActualDays"] = pd.to_numeric(proj_tasks.get("ActualDays", np.nan), errors="coerce")
            if proj_tasks["ActualDays"].isna().all():
                proj_tasks["ActualDays"] = (pd.to_datetime(proj_tasks[tcol("end")], errors="coerce") - pd.to_datetime(proj_tasks[tcol("start")], errors="coerce")).dt.days
            if proj_tasks["PlannedDays"].isna().all():
                proj_tasks["PlannedDays"] = proj_tasks["ActualDays"]
            proj_tasks["ScheduleSlip"] = proj_tasks["ActualDays"] > proj_tasks["PlannedDays"] * 1.1

        fig = px.timeline(
            proj_tasks,
            x_start=tcol("start"),
            x_end=tcol("end"),
            y=tcol("task_name"),
            color=tcol("complete") if tcol("complete") and tcol("complete") in proj_tasks.columns else None,
            title="Task Timeline",
        )
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

        # Show table with useful columns if present
        show_cols = [c for c in [
            tcol("task_id"), tcol("task_name"), tcol("status"),
            tcol("complete"), "PlannedDays", "ActualDays", "ScheduleSlip"
        ] if c and c in proj_tasks.columns or c in ["PlannedDays", "ActualDays", "ScheduleSlip"]]
        st.dataframe(
            proj_tasks[show_cols].sort_values(by=[tcol("status"), tcol("task_name")], na_position="last")
            if show_cols else proj_tasks
        )
    else:
        st.info("Set task name and date columns in the mapping above to see the Gantt chart.")
else:
    st.caption("Set join keys that match a common value between forms and tasks, for example Forms.Ref ↔ Tasks.project.")
