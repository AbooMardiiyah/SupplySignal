"""PHC SupplySignal demonstration interface."""

from __future__ import annotations

import base64
import json
import logging
import tempfile
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from supplysignal.decisions import AS_OF, create_queue, facility_call_plan
from supplysignal.import_preview import expected_report_period, preview_worklist
from supplysignal.ingest import normalize
from supplysignal.logging_config import configure_logging
from supplysignal.worksheet import call_worksheet
from supplysignal.operations import (
    list_case_events, list_events, record_case_event, record_event,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
configure_logging()
logger = logging.getLogger("supplysignal.app")

st.set_page_config(page_title="PHC SupplySignal", page_icon="🏥", layout="wide")


@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, dict, dict, dict, dict, dict]:
    facilities = pd.read_csv(DATA / "facilities.csv")
    ledger = pd.read_csv(DATA / "synthetic_lmis.csv")
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    baselines = json.loads((DATA / "baseline_results.json").read_text(encoding="utf-8"))
    training = json.loads((DATA / "training_report.json").read_text(encoding="utf-8"))
    ranking = json.loads((DATA / "ranking_report.json").read_text(encoding="utf-8"))
    workload = json.loads((DATA / "workload_report.json").read_text(encoding="utf-8"))
    return facilities, ledger, manifest, baselines, training, ranking, workload


required = [
    DATA / name
    for name in (
        "facilities.csv",
        "synthetic_lmis.csv",
        "manifest.json",
        "baseline_results.json",
        "training_report.json",
        "ranking_report.json",
        "workload_report.json",
    )
]
if any(not path.exists() for path in required):
    logger.error("demo_artifacts_missing", extra={"context": {
        "files": [path.name for path in required if not path.exists()],
    }})
    st.error("Demo data is missing. Run the setup commands in README.md.")
    st.stop()

facilities, ledger, manifest, baselines, training, ranking, workload = load_data()
events = list_events(as_of=AS_OF)
case_events = list_case_events(as_of=AS_OF)
policy = ranking["deployment_gate"]["deployed_policy"]
all_cases = pd.DataFrame(create_queue(as_of=AS_OF, events=events, include_clear=True, priority_policy=policy))
latest_case_events = {
    (event["facility_id"], event["commodity_id"]): event for event in case_events
}
case_status_labels = {
    "contact_attempted": "Contact attempted",
    "facility_unreachable": "Facility unreachable",
    "referred_to_lga": "Referred to LGA",
    "follow_up_completed": "Follow-up completed",
}
all_cases["follow_up_status"] = [
    case_status_labels.get(
        latest_case_events.get((row.facility_id, row.commodity_id), {}).get("event_type"),
        "Not contacted",
    )
    for row in all_cases.itertuples()
]
queue = all_cases[all_cases["action"] != "no_action"].copy()

ACTION_COLORS = {
    "Escalate resupply": "#C0392B",
    "Check transfer": "#E67E22",
    "Verify donor": "#8E44AD",
    "Verify stock": "#2471A3",
    "No immediate action": "#95A5A6",
}

ACTION_SYMBOLS = {
    "Escalate resupply": "triangle-up",
    "Check transfer": "square",
    "Verify donor": "diamond",
    "Verify stock": "circle",
    "No immediate action": "circle",
}


@st.cache_data
def basemap() -> tuple[str, dict]:
    snapshots = ROOT / "data" / "snapshots"
    encoded = base64.b64encode((snapshots / "afijio_basemap.jpg").read_bytes()).decode("ascii")
    bounds = json.loads((snapshots / "afijio_basemap.json").read_text(encoding="utf-8"))
    return f"data:image/jpeg;base64,{encoded}", bounds


def facility_map(frame: pd.DataFrame):
    """Facilities on a frozen street basemap, plotted in Web Mercator tile units."""
    import plotly.graph_objects as go

    image, bounds = basemap()
    scale = 2 ** bounds["zoom"]
    frame = frame.assign(
        x=(frame["longitude"] + 180) / 360 * scale,
        y=-(1 - np.arcsinh(np.tan(np.radians(frame["latitude"]))) / np.pi) / 2 * scale,
    )
    figure = go.Figure()
    for action, color in ACTION_COLORS.items():
        subset = frame[frame["Most urgent action"] == action]
        if subset.empty:
            continue
        figure.add_trace(go.Scatter(
            x=subset["x"], y=subset["y"], mode="markers+text", name=action,
            text=subset["label"], textfont={"color": "white", "size": 13, "family": "sans-serif"},
            marker={
                "symbol": ACTION_SYMBOLS[action], "color": color, "opacity": 0.95,
                "size": 12 if action == "No immediate action" else 16 + 5 * subset["Products to check"],
                "line": {"color": "white", "width": 2},
            },
            customdata=subset[["Facility", "Ward", "Call", "Products"]],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Ward: %{customdata[1]} · %{customdata[2]}"
                "<br><br>%{customdata[3]}<extra></extra>"
            ),
        ))
    x0, x1 = frame["x"].min(), frame["x"].max()
    y_mid, y_half = frame["y"].mean(), (frame["y"].max() - frame["y"].min()) * 0.56
    x_half = max((x1 - x0) * 0.56, y_half * 2.1)
    x_mid = (x0 + x1) / 2
    figure.add_layout_image(
        source=image, xref="x", yref="y", layer="below", sizing="stretch",
        x=bounds["tile_x0"], y=-bounds["tile_y0"],
        sizex=bounds["tile_x1"] - bounds["tile_x0"], sizey=bounds["tile_y1"] - bounds["tile_y0"],
    )
    figure.update_xaxes(visible=False, range=[x_mid - x_half, x_mid + x_half])
    figure.update_yaxes(visible=False, range=[y_mid - y_half, y_mid + y_half], scaleanchor="x")
    figure.update_layout(
        height=470, margin={"l": 0, "r": 0, "t": 0, "b": 0}, plot_bgcolor="#F2EFE9",
        dragmode="pan", hoverlabel={"bgcolor": "white", "font_size": 13},
        legend={"orientation": "h", "x": 0.01, "y": 0.99, "bgcolor": "rgba(255,255,255,0.9)",
                "title": {"text": "Most urgent action  "}, "itemsizing": "constant"},
    )
    return figure


st.title("PHC SupplySignal")
st.caption(
    f"Afijio LGA, Oyo State · four-week worklist for an LGA supply officer · as of {AS_OF.isoformat()}  \n"
    "Real public-registry facilities · **simulated stock history** · do not move real medicines from this demo"
)

with st.sidebar:
    st.header("How to use")
    st.markdown(
        "1. Pick a facility call from the worklist.\n"
        "2. Confirm stock with the facility.\n"
        "3. Record the count or delivery; the next action updates."
    )
    st.divider()
    st.markdown("**What each action means**")
    for label, meaning in (
        ("Verify stock", "report missing, late or not a fresh count"),
        ("Verify donor", "shortage counted; check a nearby donor"),
        ("Check transfer", "both counts fresh; review and approve"),
        ("Escalate resupply", "shortage counted; no local donor"),
    ):
        st.markdown(
            f"<span style='color:{ACTION_COLORS[label]};font-size:1.1em'>●</span> "
            f"**{label}** — {meaning}",
            unsafe_allow_html=True,
        )
    st.divider()
    with st.expander("Power or connection interrupted?"):
        st.write(
            "Download the call worksheet before leaving; print it or open it in any text editor. "
            "Record unknown stock as unknown, not zero."
        )
        st.write(
            "A locally installed app works without internet while powered; a hosted app needs a connection. "
            "Saved observations persist; check the history before re-entering."
        )
    st.caption(f"Pilot: {manifest['pilot']} · monthly reports due day 10")

counts = queue["action"].value_counts()
signal_counts = queue["signal"].value_counts()
columns = st.columns(4)
columns[0].metric("PHCs with work", queue["facility_id"].nunique())
columns[1].metric(
    "Direct report signals",
    int(signal_counts.get("Zero in last report", 0) + signal_counts.get("Recent reported stockout", 0)
        + signal_counts.get("Low reported cover", 0)),
    help="A zero balance, stockout days, or at most four weeks of cover in the last report; still needs a fresh count.",
)
columns[2].metric(
    "Reporting gaps",
    int(signal_counts.get("No submitted report", 0) + signal_counts.get("Late or expired evidence", 0)),
)
columns[3].metric("Forecast-only checks", int(signal_counts.get("Forecast-only gap", 0)))
if any(counts.get(action, 0) for action in ("verify_donor", "propose_transfer_for_verification", "escalate_resupply")):
    st.success(
        f"Counted shortages: {int(counts.get('verify_donor', 0) + counts.get('propose_transfer_for_verification', 0) + counts.get('escalate_resupply', 0))} "
        "cases need a donor check, conditional transfer review, or resupply escalation."
    )
def open_call(facility_id: str, commodity_id: str) -> None:
    st.session_state["facility_selection"] = facility_id
    st.session_state["commodity_selection"] = commodity_id
    st.session_state["main_tab"] = "Verify and update"


queue_tab, facility_tab, import_tab, data_tab = st.tabs(
    ["Worklist", "Verify and update", "Import preview", "Data and evidence"],
    key="main_tab", on_change="rerun",
)

with queue_tab:
    st.subheader("What needs attention")
    st.caption("A report is a reason to check, not proof of today's stock. Open a case to record fresh evidence.")
    action_labels = {
        "verify_stock": "Verify stock",
        "verify_donor": "Verify donor",
        "propose_transfer_for_verification": "Check transfer",
        "escalate_resupply": "Escalate resupply",
        "no_action": "No immediate action",
    }
    all_calls = facility_call_plan(queue.to_dict("records"))
    calls = all_calls[:10]
    st.markdown("#### Where the work is")
    severity = ["escalate_resupply", "propose_transfer_for_verification", "verify_donor", "verify_stock"]
    call_rank = {call["facility_id"]: rank for rank, call in enumerate(calls, start=1)}
    map_rows = []
    for facility in facilities.itertuples():
        cases = queue[queue["facility_id"] == facility.facility_id]
        actions = set(cases["action"])
        top = next((action for action in severity if action in actions), "no_action")
        rank = call_rank.get(facility.facility_id)
        map_rows.append({
            "Facility": facility.facility_name,
            "Ward": facility.ward,
            "latitude": facility.latitude,
            "longitude": facility.longitude,
            "Most urgent action": action_labels[top],
            "Products to check": len(cases),
            "Products": "<br>".join(
                f"{row.commodity_name.split(',')[0]}: {action_labels[row.action]}" for row in cases.itertuples()
            ) or "None flagged",
            "Call": f"Call #{rank}" if rank else "Later in backlog" if len(cases) else "—",
            "label": str(rank) if rank else "",
        })
    try:
        st.plotly_chart(facility_map(pd.DataFrame(map_rows)), width="stretch",
                        config={"displayModeBar": False, "scrollZoom": False})
        st.caption(
            "Numbered markers are the first ten calls; marker size shows products to check. "
            "Hover a marker for its products and next action. Street map stored locally, so it works offline. "
            "Basemap tiles © Esri, HERE, Garmin, OpenStreetMap contributors."
        )
    except Exception:
        logger.exception("map_render_failed")
        st.caption("Map unavailable; the call list below has the same information.")

    st.markdown("#### First ten facility calls")
    worksheet_columns = st.columns([3, 1])
    worksheet_columns[0].caption(
        f"{len(calls)} calls cover {sum(call['case_count'] for call in calls)} product checks: "
        "one call checks every flagged product at that PHC."
    )
    worksheet_columns[1].download_button(
        "Download call worksheet (text)",
        data=call_worksheet(queue.to_dict("records"), AS_OF),
        file_name=f"supplysignal_demo_calls_{AS_OF.isoformat()}.txt",
        mime="text/plain", on_click="ignore",
        help="First ten facilities, all their flagged products, and spaces to record checks offline.",
    )
    for row_start in range(0, len(calls), 2):
        row = st.columns(2)
        for column, rank in zip(row, range(row_start + 1, min(row_start + 3, len(calls) + 1))):
            call = calls[rank - 1]
            cases = queue[queue["facility_id"] == call["facility_id"]]
            with column.container(border=True):
                head = st.columns([4, 1.3])
                head[0].markdown(f"**{rank}. {call['facility_name']}**")
                head[1].button(
                    "Open call", key=f"open_call_{rank}", width="stretch",
                    on_click=open_call, args=(call["facility_id"], cases.iloc[0]["commodity_id"]),
                )
                st.markdown(
                    "  \n".join(
                        f"<span style='color:{ACTION_COLORS[action_labels[case.action]]}'>●</span> "
                        f"{case.commodity_name.split(',')[0]} — <b>{action_labels[case.action]}</b> "
                        f"<span style='color:#7a7f87'>· {case.signal.lower()}</span>"
                        for case in cases.itertuples()
                    ),
                    unsafe_allow_html=True,
                )
    backlog = st.expander(f"Full backlog: all {len(queue)} product cases, filters and CSV export")
    view = queue.copy()
    view["Action"] = view["action"].map(action_labels)
    with backlog.popover("Filter cases"):
        selected_actions = st.multiselect(
            "Action type",
            options=[label for key, label in action_labels.items() if key != "no_action"],
            default=[label for key, label in action_labels.items() if key != "no_action"],
        )
        selected_signals = st.multiselect(
            "Why it appeared",
            options=list(queue["signal"].drop_duplicates()),
            default=list(queue["signal"].drop_duplicates()),
        )
        selected_statuses = st.multiselect(
            "Follow-up status",
            options=["Not contacted", *case_status_labels.values()],
            default=["Not contacted", *case_status_labels.values()],
        )
        capacity = st.radio(
            "Worklist size", [10, 20, "All"], horizontal=True,
            index=2 if not ranking["deployment_gate"]["worklist_validated_for_field_use"] else 0,
        )
    view = view[view["Action"].isin(selected_actions)]
    view = view[view["signal"].isin(selected_signals)]
    view = view[view["follow_up_status"].isin(selected_statuses)]
    if capacity != "All":
        view = view.head(capacity)
    backlog.caption(
        f"Showing {len(view)} of {len(queue)} product cases across {view['facility_id'].nunique()} facilities. "
        "The full backlog stays visible; order is a working heuristic, not a stockout probability."
    )
    display = view.rename(
        columns={
            "facility_name": "Facility",
            "commodity_name": "Commodity",
            "signal": "Why it appeared",
            "follow_up_status": "Follow-up",
            "next_step": "Next step",
            "evidence_status": "Report status",
            "last_report_period": "Last report",
            "effective_stock": "Latest known stock",
            "four_week_demand_baseline": "Four-week demand forecast",
            "suggested_units": "Suggested units",
            "remaining_shortage_units": "Unfilled units",
            "donor_facility_name": "Potential donor",
            "expected_receipt_units": "Expected receipt (not counted)",
        }
    )
    for numeric_column in ("Latest known stock", "Four-week demand forecast", "Suggested units", "Unfilled units"):
        display[numeric_column] = pd.to_numeric(display[numeric_column].replace("", pd.NA)).astype("Int64")
    backlog.dataframe(
        display[
            [
                "Facility", "Commodity", "Action", "Why it appeared", "Follow-up", "Next step",
                "Report status", "Last report", "Latest known stock", "Four-week demand forecast",
                "Suggested units", "Unfilled units", "Potential donor",
            ]
        ],
        width="stretch",
        hide_index=True,
    )
    backlog.caption("The reported stock may be old. Expected deliveries do not count as available stock.")
    export_columns = [
        "facility_id", "facility_name", "commodity_id", "commodity_name", "action",
        "signal", "follow_up_status", "next_step", "evidence_status",
        "last_report_period", "effective_stock", "four_week_demand_baseline",
        "suggested_units", "remaining_shortage_units", "donor_facility_name", "reason",
    ]
    displayed_csv = view[export_columns].to_csv(index=False).encode("utf-8-sig")
    full_csv = queue[export_columns].to_csv(index=False).encode("utf-8-sig")
    download_columns = backlog.columns(2)
    download_columns[0].download_button(
        f"Download displayed cases ({len(view)})",
        data=displayed_csv,
        file_name="phc_supplysignal_displayed_cases_demo.csv",
        mime="text/csv",
        on_click="ignore",
    )
    download_columns[1].download_button(
        f"Download full backlog ({len(queue)})",
        data=full_csv,
        file_name="phc_supplysignal_full_backlog_demo.csv",
        mime="text/csv",
        on_click="ignore",
    )
    with backlog.popover("Copy CSV text (if downloads are blocked)"):
        copy_scope = st.radio("Copy", ["Displayed cases", "Full backlog"], horizontal=True)
        copy_csv = displayed_csv if copy_scope == "Displayed cases" else full_csv
        st.text_area(
            "Select and copy the CSV below, then save it as a .csv file",
            value=copy_csv.decode("utf-8-sig"), height=180,
        )
    if queue.empty:
        st.success("No cases currently require action from the available evidence.")

with facility_tab:
    st.subheader("Close the information gap")
    if not queue.empty:
        work_items = queue.to_dict("records")
        selected_work_item = st.selectbox(
            "Open a worklist case",
            options=range(len(work_items)),
            format_func=lambda index: (
                f"{work_items[index]['facility_name']} · {work_items[index]['commodity_name']} "
                f"— {action_labels[work_items[index]['action']]}"
            ),
            key="worklist_case",
        )
        if st.button("Open selected case"):
            st.session_state["facility_selection"] = work_items[selected_work_item]["facility_id"]
            st.session_state["commodity_selection"] = work_items[selected_work_item]["commodity_id"]
            st.rerun()
    st.caption(
        "Counts and received deliveries change stock; a promised delivery never does. "
        "If a count follows a delivery, record the delivery first."
    )
    facility_names = dict(zip(facilities["facility_id"], facilities["facility_name"]))
    selected = st.selectbox(
        "Facility", options=facilities.sort_values("facility_name")["facility_id"].tolist(),
        format_func=lambda facility_id: facility_names[facility_id],
        key="facility_selection",
    )
    facility_cases = all_cases[all_cases["facility_id"] == selected]
    selected_commodity = st.selectbox(
        "Product", options=sorted(facility_cases["commodity_id"].tolist()),
        format_func=lambda commodity_id: facility_cases.loc[
            facility_cases["commodity_id"] == commodity_id, "commodity_name"
        ].iloc[0],
        key="commodity_selection",
    )
    case = facility_cases[facility_cases["commodity_id"] == selected_commodity].iloc[0]
    st.markdown(
        "**Products at this clinic:** " + " &nbsp; ".join(
            f"<span style='color:{ACTION_COLORS[action_labels[row.action]]}'>●</span> "
            f"{row.commodity_name.split(',')[0]} — {action_labels[row.action]}"
            for row in facility_cases.itertuples()
        ),
        unsafe_allow_html=True,
    )
    st.markdown(f"#### Current decision: {action_labels[case['action']]}")
    st.info(f"**Why it appeared:** {case['signal']}. **Next step:** {case['next_step']}")
    st.write(f"**Follow-up status:** {case['follow_up_status']}. Contact progress does not change stock.")
    st.write(case["reason"])
    details = st.columns(4)
    details[0].metric("Last reported / counted", case["effective_stock"] if case["effective_stock"] != "" else "Unknown")
    details[1].metric("Four-week forecast", case["four_week_demand_baseline"] if case["four_week_demand_baseline"] != "" else "Unknown")
    details[2].metric("Evidence", case["evidence_status"].replace("_", " ").title())
    details[3].metric("Expected, unconfirmed", case["expected_receipt_units"])
    if case["last_verified_at"]:
        st.caption(f"Last physical count: {case['last_verified_at']}. Counts expire after seven days in this prototype.")
    elif case["last_report_period"]:
        st.caption(f"Last monthly report: {case['last_report_period']}; submitted stock: {case['stock_on_last_report']}.")
    if case["next_expected_arrival"]:
        st.info(f"An unconfirmed delivery is expected on {case['next_expected_arrival']}; it is not included in stock.")
    if case["donor_facility_name"]:
        st.info(
            f"Potential donor: {case['donor_facility_name']} · {case['donor_distance_km']} km straight-line. "
            "Check physical stock, expiry, product specification, travel route and approval before transfer."
        )
    if case["action"] == "propose_transfer_for_verification":
        st.success(
            f"**Proposed transfer: {case['suggested_units']} units from {case['donor_facility_name']}**, "
            "after its own forecast demand and safety reserve are protected."
        )
        if case["remaining_shortage_units"]:
            st.warning(f"This proposal leaves {case['remaining_shortage_units']} units to escalate for resupply.")
        st.caption("Donor surplus is shared across this plan's proposals. Record fresh stock counts after any actual transfer; proposals do not move stock.")
    st.markdown("#### Follow-up trail")
    st.caption("Log what happened when the facility was contacted. This does not close an alert or alter inventory.")
    follow_up_labels = {
        "Contact attempted": "contact_attempted",
        "Facility unreachable": "facility_unreachable",
        "Referred to LGA": "referred_to_lga",
        "Follow-up completed": "follow_up_completed",
    }
    with st.form("record_follow_up", clear_on_submit=True):
        follow_up_kind = st.selectbox("Follow-up outcome", options=list(follow_up_labels))
        follow_up_recorder = st.text_input("Follow-up recorded by (name or role)")
        follow_up_note = st.text_area("Follow-up note", max_chars=500)
        saved_follow_up = st.form_submit_button("Save follow-up")
    if saved_follow_up:
        try:
            record_case_event(
                selected, selected_commodity, follow_up_labels[follow_up_kind], AS_OF,
                note=follow_up_note, recorded_by=follow_up_recorder, as_of=AS_OF,
            )
        except ValueError as error:
            logger.warning("follow_up_rejected", extra={"context": {"error_type": type(error).__name__}})
            st.error(str(error))
        except Exception:
            logger.exception("follow_up_save_failed")
            st.error("Could not save follow-up. Check the application logs and retry.")
        else:
            st.success("Follow-up saved. Supply decision is unchanged until stock evidence changes.")
            st.rerun()
    case_history = [
        event for event in case_events
        if event["facility_id"] == selected and event["commodity_id"] == selected_commodity
    ]
    if case_history:
        st.dataframe(
            pd.DataFrame(case_history)[
                ["event_date", "event_type", "recorded_by", "note", "recorded_at"]
            ],
            width="stretch", hide_index=True,
        )
    st.markdown("#### Stock evidence")
    kind_labels = {
        "Physical stock count": "stock_count",
        "Delivery received": "receipt_confirmed",
        "Delivery expected": "receipt_expected",
    }
    kind = st.selectbox("Observation", options=list(kind_labels))
    with st.form("record_observation", clear_on_submit=True):
        units = st.number_input("Units", min_value=0, step=1, value=0)
        arrival = st.date_input("Expected arrival", value=AS_OF + timedelta(days=3)) if kind == "Delivery expected" else None
        reference = st.text_input("Delivery reference", help="Required for a received delivery") if kind == "Delivery received" else ""
        recorder = st.text_input("Recorded by (name or role)")
        note = st.text_area("Note", max_chars=500)
        submitted = st.form_submit_button("Save observation and update queue", type="primary")
    if submitted:
        try:
            record_event(
                selected, selected_commodity, kind_labels[kind], int(units), AS_OF,
                expected_date=arrival, reference=reference, note=note, recorded_by=recorder,
                as_of=AS_OF,
            )
        except ValueError as error:
            logger.warning("observation_rejected", extra={"context": {"error_type": type(error).__name__}})
            st.error(str(error))
        except Exception:
            logger.exception("observation_save_failed")
            st.error("Could not save the observation. Check the application logs and retry.")
        else:
            st.success("Observation saved. Recalculating decisions from the new evidence.")
            st.rerun()

    history_events = [
        event for event in events
        if event["facility_id"] == selected and event["commodity_id"] == selected_commodity
    ]
    if history_events:
        st.subheader("Observation history")
        st.dataframe(
            pd.DataFrame(history_events)[
                ["event_date", "event_type", "units", "expected_date", "reference", "recorded_by", "note", "recorded_at"]
            ],
            width="stretch", hide_index=True,
        )
    history = ledger[
        (ledger["facility_id"] == selected) & (ledger["commodity_id"] == selected_commodity)
    ].copy()
    history["period"] = pd.to_datetime(history["period"])
    st.line_chart(history.set_index("period")[["closing_stock", "consumption"]])
    st.caption("Chart values are simulated monthly reports; officer observations are displayed separately above.")

with import_tab:
    st.subheader("Turn an LMIS extract into a verification worklist")
    st.warning(
        "Preview only: uploaded records are not combined with the Afijio demo, the synthetic-trained model, "
        "or the demo observation log. Output requests checks; it never authorises a transfer or resupply."
    )
    st.write(
        "Supply a monthly facility-product report and an expected facility-product roster. "
        "The roster exposes PHCs that never reported. Source-field mappings are optional for canonical files. "
        f"Under the example day-10 reporting rule, {expected_report_period(AS_OF)} is the latest due month."
    )
    sample = st.checkbox("Use fictional sample files", value=True)
    reports_upload = roster_upload = mapping_upload = None
    if not sample:
        st.caption("Upload de-identified facility-level operational data only; no patient records. Files are processed in a temporary directory.")
        reports_upload = st.file_uploader("Monthly LMIS CSV", type=["csv"])
        roster_upload = st.file_uploader("Expected facility-product roster CSV", type=["csv"])
        mapping_upload = st.file_uploader("Column mapping JSON (optional)", type=["json"])
    if st.button("Create verification preview", type="primary"):
        if not sample and (reports_upload is None or roster_upload is None):
            st.error("Both the monthly report and expected roster are required.")
        elif not sample and any(
            upload.size > 2_000_000
            for upload in (reports_upload, roster_upload, mapping_upload)
            if upload is not None
        ):
            st.error("Each upload must be at most 2 MB for this browser preview.")
        else:
            try:
                with tempfile.TemporaryDirectory(prefix="supplysignal-preview-") as directory:
                    temp = Path(directory)
                    reports_path = ROOT / "data" / "example_lmis_input.csv" if sample else temp / "reports.csv"
                    roster_path = ROOT / "data" / "example_roster.csv" if sample else temp / "roster.csv"
                    mapping_path = ROOT / "data" / "example_mapping.json" if sample else None
                    if not sample:
                        reports_path.write_bytes(reports_upload.getvalue())
                        roster_path.write_bytes(roster_upload.getvalue())
                        if mapping_upload is not None:
                            mapping_path = temp / "mapping.json"
                            mapping_path.write_bytes(mapping_upload.getvalue())
                    normalized_path = temp / "normalized.csv"
                    audit = normalize(reports_path, normalized_path, mapping_path)
                    normalized = pd.read_csv(normalized_path)
                    roster = pd.read_csv(roster_path, dtype=str, keep_default_na=False)
                    preview = preview_worklist(normalized, roster, AS_OF)
                st.session_state["import_preview"] = preview
                st.session_state["import_audit"] = audit
                st.session_state["import_source"] = "Fictional sample" if sample else "Uploaded extract"
            except (ValueError, KeyError, json.JSONDecodeError, pd.errors.ParserError) as error:
                logger.warning("import_rejected", extra={"context": {"error_type": type(error).__name__}})
                st.error(f"Import rejected: {error}")
            except Exception:
                logger.exception("import_preview_failed")
                st.error("Could not process the import. Check the application logs and retry.")
    if "import_preview" in st.session_state:
        imported = st.session_state["import_preview"]
        st.success(
            f"{st.session_state['import_source']}: {len(imported)} expected facility-product pairs; "
            f"{int(imported['action'].ne('No immediate check').sum())} need a verification check."
        )
        st.caption(
            "This order groups missing reports and direct warnings for review; it is not a validated risk ranking. "
            "Consumption baseline uses at least two recent uncensored reports when available."
        )
        st.dataframe(imported, width="stretch", hide_index=True)
        st.download_button(
            "Download import verification worklist",
            data=imported.to_csv(index=False).encode("utf-8-sig"),
            file_name="phc_supplysignal_import_verification.csv",
            mime="text/csv",
            on_click="ignore",
        )
        audit = st.session_state["import_audit"]
        st.write(
            f"Import checks: {audit['rows']} reports, {audit['balance_discrepancies']} stock-balance "
            f"discrepancies, {audit['unknown_stockout_days']} reports without stockout days."
        )

with data_tab:
    st.subheader("Evidence and limits")
    st.write(
        "The public facility registry supplies identity and location. The NBS 2023 figure "
        "in the source manifest describes Oyo public-primary facilities as a group; it is "
        "not a measurement for any PHC shown here."
    )
    st.write(f"**Simulation:** {manifest['operational_row_count']:,} facility-commodity-month rows; seed {manifest['seed']}.")
    st.write(
        f"**Registry matching issue:** {manifest['missing_nhfr_codes']} of {manifest['facility_count']} "
        "facilities lack an NHFR code; one code is duplicated."
    )
    st.subheader("Ten PHC calls: does the order help?")
    st.write(
        "On the same flagged candidates and ten unique facility calls per month, compare our "
        "gap order with two simple rules. Every flagged product at a called PHC counts as a "
        "check; an unflagged shortage does not count as found. Earlier months use a simple "
        "demand baseline; later months show both that baseline and the trained model. "
        "All results are from already-inspected simulation months, not a fresh field test."
    )
    workload_rows = [
        {
            "Block": row["group"].replace("_already_inspected", "").replace("_", " ").title(),
            "Forecast": "Trained model" if row["forecast_strategy"] == "model" else "3-report mean",
            "Order": row["policy"],
            "PHC calls": row["facility_calls"],
            "Product checks": row["product_checks"],
            "Calls finding shortage": row["shortage_calls"],
            "Shortage products found": row["shortage_product_checks"],
            "Shortage products missed": row["missed_shortage_products"],
            "Unmet units found": int(row["unmet_units_found"]),
        }
        for row in workload["summary"]
    ]
    st.dataframe(pd.DataFrame(workload_rows), width="stretch", hide_index=True)
    st.warning(
        "With the trained model in the later synthetic months, the gap order found shortages "
        "in 5 of 40 calls versus 8 of 40 for oldest-report first. "
        "This is a verification workflow, not a validated shortage ranking or stockout probability."
    )
    st.write(
        "**Forecast baseline, simulation only:** three-report mean WAPE "
        f"{baselines['mean_last_3_reports']['wape']:.1%}; last-report WAPE "
        f"{baselines['last_report']['wape']:.1%}."
    )
    st.subheader("Verification worklist backtest")
    st.write(
        "Policies were compared on earlier synthetic months with a three-report demand baseline. "
        "The original coverage rule was selected on development months and then failed its March–May check. "
        "Those months and June–September have since been inspected; new ranking comparisons there are exploratory."
    )
    comparisons = []
    for phase, key in (
        ("Development", "development"),
        ("Ranking validation", "validation_untouched_during_selection"),
        ("Exploratory later months", "exploratory_test_already_inspected"),
    ):
        for name, metrics in ranking[key].items():
            comparisons.append({
                "Phase": phase, "Ranking": name,
                "Shortages found in top 10": metrics["top_k_hits"],
                "Actual shortages": metrics["event_cases"],
                "Cases checked": metrics["top_k_cases"],
                "Facility calls": metrics["facility_calls"],
                "Calls reaching shortage PHCs": metrics["facility_call_hits"],
                "Random-candidate expected hits": metrics["random_candidate_expected_hits"],
            })
    st.dataframe(pd.DataFrame(comparisons), width="stretch", hide_index=True)
    st.warning(ranking["deployment_gate"]["reason"] + ". These are simulation results, not a field guarantee.")
    stress = ranking["receipt_challenger_stress_test"]
    st.write(
        "**Receipt-aware challenger:** It raises investigation priority when the last two visible "
        "reports show no deliveries or the last report recorded stockout days. "
        "On six alternate seeds of the same simulator, it found "
        f"{stress['top_10_product_hits']['receipt_gap']} shortage cases in the first ten checks "
        f"versus {stress['top_10_product_hits']['absolute_gap']} for the current rule. "
        f"But it captured {stress['top_10_unmet_units']['receipt_gap']:.0f} unmet units versus "
        f"{stress['top_10_unmet_units']['absolute_gap']:.0f}; the trade-off does not justify "
        "silently replacing the current order. This is a simulator robustness check, not an external test."
    )
    chosen = training["selected_model"]
    st.write(
        f"**Selected demand model:** {chosen}, chosen on validation MAE. "
        f"Held-out simulation WAPE {training['test_metrics'][chosen]['wape']:.1%}, "
        f"vs {training['test_metrics']['mean_last_3_reports']['wape']:.1%} "
        "for the three-report mean. These are not field accuracy estimates."
    )
    alerts = training["selected_test_alert_metrics"]
    if "precision" in alerts:
        st.error(
            f"**Earlier naive stock-projection rule:** on the synthetic test months its alerts "
            f"were only {alerts['precision']:.1%} precise "
            f"({alerts['true_positives']} true, {alerts['false_positives']} false). "
            "Unknown receipts and stale counts make these verification prompts, not confirmed stockouts."
        )
    st.write(
        "Transfer distance uses straight-line coordinates. Roads, stock expiry, product "
        "formulation and real physical counts are not available in this prototype. "
        "Manually entered demo observations are stored separately from the synthetic LMIS and training data."
    )
    st.write(f"**Recorded demo observations:** {len(events)}. Confirmed receipts add units; expected receipts do not.")
    st.write(f"**Logged demo follow-ups:** {len(case_events)}. These do not change stock or suppress alerts.")
    st.json(manifest)
