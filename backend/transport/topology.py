from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Topology:
    tickets_exchange: str = "tickets"
    tickets_dlx_exchange: str = "tickets.dlx"

    provider_out_queue: str = "provider.out"
    provider_in_queue: str = "provider.in"
    tickets_dlq_queue: str = "tickets.dlq"

    provider_out_routing_key: str = "provider.out"
    provider_in_routing_key: str = "provider.in"
    tickets_dlq_routing_key: str = "tickets.dlq"


TOPOLOGY = Topology()
