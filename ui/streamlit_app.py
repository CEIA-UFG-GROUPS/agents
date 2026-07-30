"""Conversational demo UI for the corporate travel multi-agent backend.

A simple Streamlit chat that drives the existing FastAPI API — it only makes
HTTP calls, it does not change any backend behavior.

Run the backend first, then:

    uv add streamlit requests        # one-time
    uv run uvicorn app.main:app --reload
    uv run streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("TRAVEL_BACKEND_URL", "http://127.0.0.1:8000")
TIMEOUT = 15

# The ordered phases shown in the timeline (matches the backend state machine).
PHASES = [
    "UNDERSTANDING",
    "PLANNING",
    "RETRIEVING_MEMORY",
    "RESOLVING_LOCATIONS",
    "SEARCHING_FLIGHTS",
    "SEARCHING_HOTELS",
    "RANKING_FLIGHTS",
    "RANKING_HOTELS",
    "RECOMMENDING",
    "ESTIMATING_BUDGET",
    "VALIDATING_POLICY",
    "AWAITING_APPROVAL",
    "GENERATING_REPORT",
]


# --------------------------------------------------------------------------- #
# Backend calls (thin wrappers; every action refreshes the full TripRun)
# --------------------------------------------------------------------------- #
def _notify(kind: str, text: str) -> None:
    """Stash a message so it survives the next st.rerun() (rendered at the top)."""
    st.session_state.notice = (kind, text)


def _post(path: str, payload: dict | None = None) -> requests.Response | None:
    try:
        return requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        _notify("error", f"Falha ao contatar o backend ({BACKEND_URL}): {exc}")
        return None


def create_trip(request_text: str) -> None:
    resp = _post("/trips", {"request_text": request_text})
    if resp is None:
        return
    if resp.status_code == 201:
        run = resp.json()
        st.session_state.trip_id = run["id"]
        st.session_state.run = run
    else:
        _notify("error", f"POST /trips falhou: {resp.status_code} — {resp.text}")


def advance_trip() -> None:
    trip_id = st.session_state.trip_id
    resp = _post(f"/trips/{trip_id}/advance")
    if resp is None:
        return
    if resp.ok:
        st.session_state.run = resp.json()
    else:
        # 409 (gate/block/clarification) or 501 (phase not implemented yet).
        detail = _detail(resp)
        if resp.status_code == 501:
            _notify("info", f"Fase ainda não implementada no backend: {detail}")
        else:
            _notify("warning", detail)
        _refresh()  # keep the displayed state consistent


def run_workflow() -> None:
    """Auto-run: advance until a human/terminal stop (POST /trips/{id}/run)."""
    trip_id = st.session_state.trip_id
    resp = _post(f"/trips/{trip_id}/run")
    if resp is None:
        return
    if not resp.ok:
        _notify("warning", _detail(resp))
        _refresh()
        return
    data = resp.json()
    st.session_state.run = data["trip"]
    st.session_state.exec_summary = data["execution_summary"]


def clarify_trip(message: str) -> None:
    """Answer a clarification on the CURRENT trip (POST /trips/{id}/clarify)."""
    trip_id = st.session_state.trip_id
    resp = _post(f"/trips/{trip_id}/clarify", {"message": message})
    if resp is None:
        return
    if resp.ok:
        st.session_state.run = resp.json()
    else:
        _notify("warning", _detail(resp))
        _refresh()


def decide(action: str, reviewer: str, comments: str) -> None:
    trip_id = st.session_state.trip_id
    resp = _post(f"/trips/{trip_id}/{action}", {"reviewer": reviewer, "comments": comments or None})
    if resp is None:
        return
    if not resp.ok:
        _notify("warning", _detail(resp))
        _refresh()
        return
    st.session_state.run = resp.json()
    # After approval, continue the workflow automatically until COMPLETED.
    if action == "approve":
        run_workflow()


def _refresh() -> None:
    trip_id = st.session_state.get("trip_id")
    if not trip_id:
        return
    try:
        resp = requests.get(f"{BACKEND_URL}/trips/{trip_id}", timeout=TIMEOUT)
        if resp.ok:
            st.session_state.run = resp.json()
    except requests.RequestException:
        pass


def _detail(resp: requests.Response) -> str:
    try:
        return str(resp.json().get("detail", resp.text))
    except ValueError:
        return resp.text


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #
def render_timeline(run: dict | None) -> None:
    st.header("Linha do tempo")
    current = run.get("phase") if run else None
    current_idx = PHASES.index(current) if current in PHASES else -1
    for idx, phase in enumerate(PHASES):
        if current_idx == -1:
            marker = "⚪"
        elif idx < current_idx:
            marker = "✅"
        elif idx == current_idx:
            marker = "🔵"
        else:
            marker = "⚪"
        st.write(f"{marker} {phase}")
    if current in ("REJECTED", "COMPLETED", "CREATED"):
        st.caption(f"Estado atual: **{current}**")


def render_cards(run: dict) -> None:
    """Key cards shown only when the corresponding data is available."""
    flight = (run.get("flight_ranking") or {}).get("recommended_flight")
    hotel = run.get("recommended_hotel")
    budget = run.get("budget_estimate")
    policy = run.get("policy_result")
    approval = run.get("approval_result")

    if flight:
        with st.container(border=True):
            st.subheader("✈️ Voo recomendado")
            st.write(
                f"**{flight['airline']} {flight['flight_number']}** — "
                f"{flight['origin_airport']} → {flight['destination_airport']}"
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("Preço", f"{flight['price']:.2f} {flight['currency']}")
            c2.metric("Paradas", flight["stops"])
            c3.metric("Duração", f"{flight['duration_minutes']} min")

    if hotel:
        with st.container(border=True):
            st.subheader("🏨 Hotel recomendado")
            st.write(f"**{hotel['hotel_name']}** ({hotel['chain']}) — {hotel['address']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Diária", f"{hotel['nightly_rate']:.2f} {hotel['currency']}")
            c2.metric("Noites", hotel["nights"])
            c3.metric("Total", f"{hotel['total_price']:.2f} {hotel['currency']}")

    if budget:
        with st.container(border=True):
            st.subheader("💰 Orçamento estimado")
            c1, c2 = st.columns(2)
            c1.metric("Total", f"{budget['total']:.2f} {budget['currency']}")
            c2.metric("Dias / Noites", f"{budget['inclusive_days']} / {budget['hotel_nights']}")
            for line in budget.get("breakdown", []):
                st.write(f"- {line}")

    if policy:
        with st.container(border=True):
            status = policy["status"]
            icon = {"pass": "✅", "warn": "⚠️", "block": "⛔"}.get(status, "•")
            st.subheader(f"📋 Política — {icon} {status.upper()}")
            for f in policy.get("findings", []):
                st.write(f"- `{f['rule_id']}` **{f['severity']}** — {f['message']}")

    if approval:
        with st.container(border=True):
            st.subheader(f"🧑‍⚖️ Aprovação — {approval['status'].upper()}")
            decision = approval.get("decision")
            if decision:
                st.write(
                    f"Revisor: **{decision['reviewer']}** · "
                    f"{decision['decision']} · {decision.get('comments') or '—'}"
                )
                st.caption(decision["timestamp"])

    report = run.get("report")
    if report:
        with st.container(border=True):
            st.subheader(f"📄 {report.get('title', 'Relatório final')}")
            if report.get("purpose"):
                st.write(f"**Propósito:** {report['purpose']}")
            itinerary = report.get("itinerary") or {}
            st.write(
                f"**Itinerário:** {itinerary.get('origin')} → "
                f"{itinerary.get('destination')} "
                f"({itinerary.get('start_date')} a {itinerary.get('end_date')})"
            )
            for line in report.get("justification", []):
                st.write(f"- {line}")
            if report.get("generated_at"):
                st.caption(f"Gerado em {report['generated_at']}")


def render_approval_actions(run: dict) -> None:
    """Approve / Reject buttons, shown only at AWAITING_APPROVAL (pending)."""
    approval = run.get("approval_result") or {}
    if run.get("phase") != "AWAITING_APPROVAL" or approval.get("status") != "pending":
        return
    st.divider()
    st.subheader("Decisão humana")
    reviewer = st.text_input("Revisor", value="gestor.demo", key="reviewer")
    comments = st.text_input("Comentários (opcional)", key="comments")
    c1, c2 = st.columns(2)
    if c1.button("✅ Approve", use_container_width=True):
        decide("approve", reviewer, comments)
        st.rerun()
    if c2.button("❌ Reject", use_container_width=True):
        decide("reject", reviewer, comments)
        st.rerun()


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Planejador de Viagens — Multi-Agente", layout="wide")

st.session_state.setdefault("trip_id", None)
st.session_state.setdefault("run", None)
st.session_state.setdefault("history", [])
st.session_state.setdefault("notice", None)
st.session_state.setdefault("exec_summary", None)
st.session_state.setdefault("mode", "Auto")

with st.sidebar:
    st.session_state.mode = st.radio(
        "Modo de execução",
        ["Auto", "Passo a passo"],
        index=0 if st.session_state.mode == "Auto" else 1,
        help="Auto roda o workflow até um ponto de parada humano. "
             "Passo a passo avança uma fase por clique (modo didático).",
    )
    st.divider()
    render_timeline(st.session_state.run)
    st.divider()
    st.caption(f"Backend: {BACKEND_URL}")

st.title("🧳 Planejador de Viagens Corporativas")
st.caption("Demonstração de um sistema multi-agente (UI conversacional sobre a API FastAPI).")

# Render any message stashed by the previous action (survives st.rerun()).
if st.session_state.notice:
    kind, text = st.session_state.notice
    getattr(st, kind)(text)
    st.session_state.notice = None

# Replay the conversation.
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Chat input — context-aware: new trip vs. clarification reply vs. in-progress.
prompt = st.chat_input("Descreva a viagem que você deseja planejar")
if prompt:
    st.session_state.history.append({"role": "user", "content": prompt})
    current = st.session_state.run
    phase = current.get("phase") if current else None

    if current is None or phase in ("COMPLETED", "REJECTED"):
        # No active trip (or the previous one is finished) -> start a new trip.
        st.session_state.exec_summary = None
        create_trip(prompt)
        if st.session_state.run and st.session_state.mode == "Auto":
            run_workflow()
        if st.session_state.run:
            st.session_state.history.append(
                {"role": "assistant",
                 "content": f"Viagem criada — `{st.session_state.trip_id}` "
                            f"(fase {st.session_state.run['phase']})."}
            )
    elif current.get("requires_clarification"):
        # Active trip waiting on info -> answer it on the SAME trip.
        clarify_trip(prompt)
        run = st.session_state.run
        if run and not run.get("requires_clarification") and st.session_state.mode == "Auto":
            run_workflow()
        run = st.session_state.run
        if run and run.get("requires_clarification"):
            st.session_state.history.append(
                {"role": "assistant", "content": f"Ainda falta: {run['clarification_question']}"}
            )
        elif run:
            st.session_state.history.append(
                {"role": "assistant",
                 "content": f"Informações atualizadas — fase {run['phase']}."}
            )
    else:
        # Active trip mid-flight and not asking anything.
        _notify(
            "info",
            "Já existe uma viagem em andamento. Use o modo Auto ou Passo a passo "
            "para continuar.",
        )
    st.rerun()

run = st.session_state.run
if run:
    st.subheader(f"Fase atual: `{run['phase']}`")

    if run.get("requires_clarification"):
        st.warning(f"❓ {run.get('clarification_question')}")

    # Execution summary from the last auto-run.
    summary = st.session_state.exec_summary
    if summary:
        st.caption(
            f"Auto-run: `{summary['started_phase']}` → `{summary['ended_phase']}` · "
            f"parada: **{summary['stop_reason']}** · "
            f"{len(summary['steps_executed'])} passos"
        )

    # Step-by-step (teaching/debug) button — only in "Passo a passo" mode.
    if st.session_state.mode == "Passo a passo":
        c1, _ = st.columns([1, 3])
        if c1.button("▶️ Executar próximo passo", use_container_width=True):
            advance_trip()
            st.rerun()

    # Latest recorded step.
    steps = run.get("steps") or []
    if steps:
        last = steps[-1]
        with st.expander(f"Último passo: **{last['name']}** ({last['status']})", expanded=True):
            st.json(last.get("output"))

    render_approval_actions(run)

    st.divider()
    render_cards(run)

    with st.expander("TripRun completo (JSON)"):
        st.json(run)
else:
    st.info("Envie uma mensagem no chat para criar uma viagem. "
            "Ex.: *Preciso planejar uma viagem corporativa para Belo Horizonte "
            "entre 08 e 13 de junho para reuniões do EnergyGPT.*")
