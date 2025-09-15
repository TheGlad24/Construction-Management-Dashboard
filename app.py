import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="Construction Portfolio Dashboard", layout="wide")

# ---------- Files (same folder as this app) ----------
FORMS_FILE = "Construction_Data_PM_Forms_All_Projects.csv"
TASKS_FILE = "Construction_Data_PM_Tasks_All_Projects.csv"

# ---------- Load ----------
@st.cache_data
def load_csvs():
    forms = pd.read_csv(FORMS_FILE)
    tasks = pd.read_csv(TASKS_FILE)
    # try parsing some date columns if present
    for df in (forms, tasks):
        for c in ["StartDate", "EndDate", "Created", "Opened", "Reported", "Date", "Status Changed"]:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce")
    return forms, tasks

forms, tasks = load_csvs()

st.title("Construction Portfolio Dashboard")
st.caption(f"Loaded: {FORMS_FILE} and {TASKS_FILE}")

# ---------- Helpers ----------
def pick(df, candidates):
    """Return first present column name from candidates (case-insensitive)."""
    cmap = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in cmap:
            return cmap[c.lower()]
    return None

def uniq(df, col):
    return sorted(df[col].dropna().astype(str).unique()) if col and col in df.columns else []

# ---------- Column guesses ----------
# Forms
F_PROJ_NAME = pick(forms, ["ProjectName","Name","Title","Project Name","Form Name"])
F_STATUS    = pick(forms, ["Status","Report Forms Status","Report Status"])
F_OWNER     = pick(forms, ["Owner","Department","Group","Report Forms Group","Report Group"])
F_PRIORITY  = pick(forms, ["Priority","Risk","Severity"])
F_BUDGET    = pick(forms, ["Budget","Cost Budget","Planned Cost","Total Budget"])
F_SPENT     = pick(forms, ["Spent","Actual Cost","Actuals","Cost Spent","Expenditure"])
F_PROGRESS  = pick(forms, ["Progress","KPI_Progress","Percent Complete","% Complete","Completion"])
F_ID        = pick(forms, ["ProjectID","Ref","ID","Project Ref","Project"])

# Tasks
T_TASK_NAME = pick(tasks, ["TaskName","Description","Title","Activity"])
T_STATUS    = pick(tasks, ["Status","Report Status"])
T_START     = pick(tasks, ["StartDate","Start","Begin"])
T_END       = pick(tasks, ["EndDate","End","Finish"])
T_COMPLETE  = pick(tasks, ["Completion","% Complete","Percent Complete","Progress"])

# DEFAULT JOIN: forms.Project ↔ tasks.project
JOIN_LEFT = "Project" if "Project" in forms.columns else F_ID or F_PROJ_NAME
JOIN_RIGHT = "project" if "project" in tasks.columns else F_ID or F_PROJ_NAME

# ---------- Numeric conversions and derived fields ----------
for c in [F_BUDGET, F_SPENT, F_PROGRESS]:
    if c and c in forms.columns:
        forms[c] = pd.to_numeric(forms[c], errors="coerce")

forms["Variance"] = np.nan
forms["OverBudget"] = False
if F_BUDGET and F_SPENT:
    forms["Variance"] = forms[F_SPENT] - forms[F_BUDGET]
    forms["OverBudget"] = forms["Variance"] > 0

forms["_progress"] = pd.to_numeric(forms[F_PROGRESS], errors="coerce") if F_PROGRESS else np.nan

# Task durations and slippage
if T_START and T_END:
    tasks["ActualDays"] = (pd.to_datetime(tasks[T_END], errors="coerce") - pd.to_datetime(tasks[T_START], errors="coerce")).dt.days
    if "PlannedDays" not in tasks.columns or tasks["PlannedDays"].isna().all():
        tasks["PlannedDays"] = tasks["ActualDays"]
    tasks["ScheduleSlip"] = tasks["ActualDays"] > tasks["PlannedDays"] * 1.1
else:
    tasks["ActualDays"] = np.nan
    tasks["PlannedDays"] = np.nan
    tasks["ScheduleSlip"] = False

# ---------- Sidebar Filters ----------
st.sidebar.header("Filters")
status_vals = uniq(forms, F_STATUS)
owner_vals  = uniq(forms, F_OWNER)
prio_vals   = uniq(forms, F_PRIORITY)

status_sel = st.sidebar.multiselect("Status", status_vals, default=status_vals)
owner_sel  = st.sidebar.multiselect("Owner", owner_vals, default=owner_vals)
prio_sel   = st.sidebar.multiselect("Priority", prio_vals, default=prio_vals)

filt = forms.copy()
if F_STATUS:   filt = filt[filt[F_STATUS].astype(str).isin(status_sel)]
if F_OWNER:    filt = filt[filt[F_OWNER].astype(str).isin(owner_sel)]
if F_PRIORITY: filt = filt[filt[F_PRIORITY].astype(str).isin(prio_sel)]

# ---------- KPIs ----------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Projects", len(filt))
k2.metric("Total Budget", f"${filt[F_BUDGET].sum():,.0f}" if F_BUDGET else "—")
k3.metric("Total Spent",  f"${filt[F_SPENT].sum():,.0f}"  if F_SPENT else "—")
if pd.api.types.is_numeric_dtype(filt["_progress"]) and filt["_progress"].notna().any():
    k4.metric("Avg Progress", f"{filt['_progress'].mean():.1f}%")
else:
    k4.metric("Avg Progress", "—")

if "OverBudget" in filt.columns:
    over_rate = float(filt["OverBudget"].mean()*100) if len(filt) else 0.0
    st.metric("Over Budget Rate", f"{over_rate:.1f}%")

import plotly.express as px

# ---- Project Status Distribution ----
status_counts = forms['Status'].value_counts().reset_index()
status_counts.columns = ['Status', 'Count']
fig_status = px.pie(status_counts, names='Status', values='Count', title='Project Status Distribution')
st.plotly_chart(fig_status, use_container_width=True)

# ---- Budget vs Spent ----
if 'Budget' in forms.columns and 'Spent' in forms.columns:
    budget_data = forms[['Name', 'Budget', 'Spent']].dropna()
    fig_budget = px.bar(budget_data, x='Name', y=['Budget', 'Spent'], barmode='group', title='Budget vs Spent')
    st.plotly_chart(fig_budget, use_container_width=True)

# ---- Task Completion ----
task_progress = tasks.groupby('Project').apply(
    lambda x: (x['Status'] == 'Closed').sum() / len(x) * 100 if len(x) > 0 else 0
).reset_index()
task_progress.columns = ['Project', 'Completion %']
fig_tasks = px.bar(task_progress, x='Project', y='Completion %', title='Task Completion % by Project')
st.plotly_chart(fig_tasks, use_container_width=True)


# ---------- Charts ----------
if F_BUDGET and F_SPENT and F_PROJ_NAME:
    st.subheader("Budget vs Spent")
    fig1 = px.bar(filt, x=F_PROJ_NAME, y=[F_BUDGET, F_SPENT], barmode="group")
    st.plotly_chart(fig1, use_container_width=True)

if F_PROJ_NAME and F_STATUS and "_progress" in filt.columns and filt["_progress"].notna().any():
    st.subheader("Project Progress")
    fig2 = px.bar(
        filt.sort_values("_progress", ascending=False),
        x=F_PROJ_NAME, y="_progress", color=F_STATUS, text="_progress"
    )
    st.plotly_chart(fig2, use_container_width=True)

# ---------- Portfolio Table ----------
st.subheader("Portfolio Table")
cols_show = [c for c in [F_ID, F_PROJ_NAME, F_OWNER, F_STATUS, F_PRIORITY, F_BUDGET, F_SPENT, "Variance"] if c and (c in filt.columns or c == "Variance")]
df_show = filt[cols_show] if cols_show else filt
sort_cols = [c for c in [F_STATUS, F_PRIORITY, F_PROJ_NAME] if c and c in df_show.columns]
if sort_cols:
    df_show = df_show.sort_values(by=sort_cols, na_position="last")
st.dataframe(df_show, use_container_width=True)

# ---------- Drilldown ----------
st.subheader("Project Drilldown")

if F_PROJ_NAME:
    proj_names = sorted(filt[F_PROJ_NAME].dropna().astype(str).unique())
    if not proj_names:
        st.info("No projects available after filters.")
    else:
        choice = st.selectbox("Select a project", proj_names)
        left_row = filt[filt[F_PROJ_NAME].astype(str) == choice].head(1)

        # Use default join: forms.Project ↔ tasks.project, else fallbacks
        proj_tasks = pd.DataFrame()
        join_pairs = []

        # Preferred join
        if "Project" in forms.columns and "project" in tasks.columns:
            join_pairs.append(("Project", "project"))

        # Fallbacks
        if F_ID and F_ID in forms.columns and F_ID in tasks.columns:
            join_pairs.append((F_ID, F_ID))
        if F_PROJ_NAME in tasks.columns:
            join_pairs.append((F_PROJ_NAME, F_PROJ_NAME))

        for lk, rk in join_pairs:
            if lk in left_row.columns and rk in tasks.columns:
                key_val = str(left_row.iloc[0][lk])
                tmp = tasks[tasks[rk].astype(str) == key_val]
                if not tmp.empty:
                    proj_tasks = tmp.copy()
                    break

        if proj_tasks.empty:
            st.info("No tasks found for this project with the current join (Project ↔ project). Check that your tasks file has a matching 'project' value.")
        else:
            st.write(f"Tasks for **{choice}**")

            # Gantt if we have names + dates
            if T_TASK_NAME and T_START and T_END and all(c in proj_tasks.columns for c in [T_TASK_NAME, T_START, T_END]):
                if "ActualDays" not in proj_tasks.columns or proj_tasks["ActualDays"].isna().all():
                    proj_tasks["ActualDays"] = (pd.to_datetime(proj_tasks[T_END], errors="coerce") - pd.to_datetime(proj_tasks[T_START], errors="coerce")).dt.days
                if "PlannedDays" not in proj_tasks.columns or proj_tasks["PlannedDays"].isna().all():
                    proj_tasks["PlannedDays"] = proj_tasks["ActualDays"]
                proj_tasks["ScheduleSlip"] = proj_tasks["ActualDays"] > proj_tasks["PlannedDays"] * 1.1

                gantt = px.timeline(
                    proj_tasks, x_start=T_START, x_end=T_END, y=T_TASK_NAME,
                    color=T_COMPLETE if T_COMPLETE and T_COMPLETE in proj_tasks.columns else None,
                    title="Task Timeline"
                )
                gantt.update_yaxes(autorange="reversed")
                st.plotly_chart(gantt, use_container_width=True)

            # Task table
            show_tcols = [c for c in [T_TASK_NAME, T_STATUS, T_COMPLETE, "PlannedDays", "ActualDays", "ScheduleSlip"] if c and (c in proj_tasks.columns or c in ["PlannedDays","ActualDays","ScheduleSlip"])]
            st.dataframe(proj_tasks[show_tcols] if show_tcols else proj_tasks, use_container_width=True)
else:
    st.info("Could not find a project name column in forms. Make sure your forms file has something like 'Name' or 'ProjectName'.")


