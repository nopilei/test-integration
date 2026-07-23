from faststream.middlewares import AckPolicy
from faststream.rabbit import (
    ExchangeType,
    RabbitBroker,
    RabbitExchange,
    RabbitQueue,
)

from backend.config import settings
from backend.transport.topology import TOPOLOGY

tickets_exchange = RabbitExchange(
    TOPOLOGY.tickets_exchange,
    type=ExchangeType.DIRECT,
    durable=True,
)

tickets_dlx_exchange = RabbitExchange(
    TOPOLOGY.tickets_dlx_exchange,
    type=ExchangeType.DIRECT,
    durable=True,
)

_provider_queue_args = {
    "x-queue-type": "quorum",
    "x-delivery-limit": settings.rmq_max_attempts,
    "x-dead-letter-exchange": TOPOLOGY.tickets_dlx_exchange,
    "x-dead-letter-routing-key": TOPOLOGY.tickets_dlq_routing_key,
}

# outbound: outbox producer -> RabbitMQ -> provider_gateway -> Websocket
provider_out_queue = RabbitQueue(
    TOPOLOGY.provider_out_queue,
    durable=True,
    routing_key=TOPOLOGY.provider_out_routing_key,
    arguments=_provider_queue_args,
)

# inbound: Websocket -> provider_gateway -> RabbitMQ -> provider_consumer
provider_in_queue = RabbitQueue(
    TOPOLOGY.provider_in_queue,
    durable=True,
    routing_key=TOPOLOGY.provider_in_routing_key,
    arguments=_provider_queue_args,
)

tickets_dlq_queue = RabbitQueue(
    TOPOLOGY.tickets_dlq_queue,
    durable=True,
    routing_key=TOPOLOGY.tickets_dlq_routing_key,
)
CONSUMER_ACK_POLICY = AckPolicy.NACK_ON_ERROR


def create_broker() -> RabbitBroker:
    return RabbitBroker(settings.rabbitmq_url, graceful_timeout=30)




async def setup_topology(broker: RabbitBroker) -> None:
    tickets_ex = await broker.declare_exchange(tickets_exchange)
    tickets_dlx_ex = await broker.declare_exchange(tickets_dlx_exchange)
    out_q = await broker.declare_queue(provider_out_queue)
    in_q = await broker.declare_queue(provider_in_queue)
    tickets_dlq_q = await broker.declare_queue(tickets_dlq_queue)
    await out_q.bind(tickets_ex, routing_key=TOPOLOGY.provider_out_routing_key)
    await in_q.bind(tickets_ex, routing_key=TOPOLOGY.provider_in_routing_key)
    await tickets_dlq_q.bind(
        tickets_dlx_ex, routing_key=TOPOLOGY.tickets_dlq_routing_key
    )


_broker: RabbitBroker | None = None


async def get_broker() -> RabbitBroker:
    global _broker
    if _broker is None:
        _broker = create_broker()
        await _broker.connect()
        await setup_topology(_broker)
    return _broker
