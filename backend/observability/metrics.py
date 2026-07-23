from prometheus_client import CollectorRegistry, Counter, Gauge

REGISTRY = CollectorRegistry(auto_describe=True)


process_up = Gauge(
    "app_process_up",
    "1 if the process is running and its readiness probe has ever succeeded.",
    labelnames=("component",),
    registry=REGISTRY,
)

process_ready = Gauge(
    "app_process_ready",
    "1 if all readiness dependencies (db, broker, provider) are currently ok.",
    labelnames=("component",),
    registry=REGISTRY,
)


tickets_created_total = Counter(
    "tickets_created_total",
    "Number of tickets accepted from clients via the API.",
    labelnames=("currency",),
    registry=REGISTRY,
)

tickets_by_status = Gauge(
    "tickets_by_status",
    "Snapshot count of tickets in each status, refreshed by the reconciler.",
    labelnames=("status",),
    registry=REGISTRY,
)

ticket_state_transition_total = Counter(
    "ticket_state_transition_total",
    "Ticket state transitions.",
    labelnames=("from_status", "to_status"),
    registry=REGISTRY,
)

ticket_stuck_recovered_total = Counter(
    "ticket_stuck_recovered_total",
    "Tickets picked up by the reconciler and progressed.",
    labelnames=("from_status", "action"),
    registry=REGISTRY,
)
