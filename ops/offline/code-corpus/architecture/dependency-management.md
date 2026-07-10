---
language: python
tags: [architecture, dependencies, di, patterns]
title: Dependency Management Patterns
description: Dependency inversion, dependency injection, interface segregation, circular import avoidance, and DI containers with Python and TypeScript examples
source: pattern
---

```python
# === DEPENDENCY INVERSION (DIP) ===
# High-level modules should NOT depend on low-level modules — both depend on abstractions.

# ❌ Bad: High-level service depends directly on low-level Postgres implementation
class OrderService:
    def __init__(self):
        self.db = PostgresOrderRepository()  # tight coupling

    def get_order(self, order_id: str) -> Order:
        return self.db.find_by_id(order_id)


# ✅ Good: Both depend on an abstraction (interface)
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class Order:
    id: str
    customer_id: str
    total: float
    status: str

class OrderRepository(ABC):
    @abstractmethod
    def find_by_id(self, order_id: str) -> Order | None:
        ...

    @abstractmethod
    def save(self, order: Order) -> None:
        ...

class OrderService:
    def __init__(self, repo: OrderRepository):  # depends on abstraction
        self._repo = repo

    def get_order(self, order_id: str) -> Order | None:
        return self._repo.find_by_id(order_id)

# Low-level implementation depends on the same abstraction
class PostgresOrderRepository(OrderRepository):
    def find_by_id(self, order_id: str) -> Order | None:
        # ... SQL query ...
        pass

    def save(self, order: Order) -> None:
        # ... SQL insert/update ...
        pass

class InMemoryOrderRepository(OrderRepository):
    def __init__(self):
        self._store: dict[str, Order] = {}

    def find_by_id(self, order_id: str) -> Order | None:
        return self._store.get(order_id)

    def save(self, order: Order) -> None:
        self._store[order.id] = order
```

```python
# === INTERFACE SEGREGATION (ISP) ===
# Clients should not be forced to depend on interfaces they don't use.

# ❌ Bad: Fat interface forces every notifier to implement methods it doesn't need
class NotificationService(ABC):
    @abstractmethod
    def send_email(self, to: str, subject: str, body: str) -> None: ...
    @abstractmethod
    def send_sms(self, phone: str, message: str) -> None: ...
    @abstractmethod
    def send_push(self, device_token: str, payload: dict) -> None: ...


# ✅ Good: Segregated interfaces
class EmailSender(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None: ...

class SmsSender(ABC):
    @abstractmethod
    def send(self, phone: str, message: str) -> None: ...

class PushNotifier(ABC):
    @abstractmethod
    def send(self, device_token: str, payload: dict) -> None: ...

# Implementations only satisfy what they actually do
class SendGridEmailSender(EmailSender):
    def send(self, to: str, subject: str, body: str) -> None:
        # SendGrid API call
        pass

# Composed where needed
class NotificationOrchestrator:
    def __init__(
        self,
        email: EmailSender | None = None,
        sms: SmsSender | None = None,
        push: PushNotifier | None = None,
    ):
        self._email = email
        self._sms = sms
        self._push = push
```

```python
# === AVOIDING CIRCULAR IMPORTS ===

# ❌ Bad: Circular dependency
# services/order_service.py
from services.payment_service import PaymentService  # also imports OrderService -> circular
class OrderService:
    def complete(self, order_id: str) -> None:
        PaymentService().process(order_id)

# services/payment_service.py
from services.order_service import OrderService
class PaymentService:
    def process(self, order_id: str) -> None:
        OrderService().get_order(order_id)


# ✅ Strategy 1: Use late imports (acceptable for type-checking only)
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.payment_service import PaymentService

class OrderService:
    def __init__(self, payment_service: PaymentService) -> None:
        self._payment = payment_service  # type is checked, no runtime import


# ✅ Strategy 2: Extract shared abstractions to a separate module
# domain/interfaces.py
from abc import ABC, abstractmethod

class PaymentProcessor(ABC):
    @abstractmethod
    def process(self, order_id: str) -> bool: ...

class OrderRepository(ABC):
    @abstractmethod
    def get_order(self, order_id: str) -> Order: ...

# services/order_service.py
from domain.interfaces import OrderRepository, PaymentProcessor

class OrderService:
    def __init__(self, repo: OrderRepository, payment: PaymentProcessor):
        self._repo = repo
        self._payment = payment

# services/payment_service.py — no import of OrderService needed
from domain.interfaces import PaymentProcessor

class StripePaymentProcessor(PaymentProcessor):
    def process(self, order_id: str) -> bool:
        # ... stripe API call ...
        return True


# ✅ Strategy 3: Use dependency injection + composition root
# The composition root (app bootstrap) is the ONLY place that imports everything.
# app/composition_root.py
from services.order_service import OrderService
from services.payment_service import StripePaymentProcessor
from infrastructure.repositories import PostgresOrderRepository

def bootstrap() -> OrderService:
    repo = PostgresOrderRepository()
    payment = StripePaymentProcessor()
    return OrderService(repo, payment)
```

```python
# === DI CONTAINERS — Python ===

# Using dependency_injector library
# pip install dependency-injector
from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    # Repositories
    order_repo = providers.Singleton(PostgresOrderRepository)

    # Services
    payment_processor = providers.Singleton(
        StripePaymentProcessor,
        api_key=config.stripe.api_key,
    )

    order_service = providers.Factory(
        OrderService,
        repo=order_repo,
        payment=payment_processor,
    )

# Usage — wiring injects dependencies automatically
@inject
def handle_create_order(
    order_data: dict,
    service: OrderService = Provide[Container.order_service],
) -> Order:
    return service.create(order_data)

# Bootstrap
container = Container()
container.config.stripe.api_key.from_env("STRIPE_API_KEY")
container.wire(modules=[__name__])
```

```python
# === TYPE HINTS FOR DI (mypy-friendly) ===
# Use Protocols (structural typing) instead of ABCs for loose coupling

from typing import Protocol, runtime_checkable

@runtime_checkable
class SupportsFindById(Protocol):
    def find_by_id(self, entity_id: str) -> object | None: ...

class GenericLookupService:
    def __init__(self, repo: SupportsFindById):
        self._repo = repo

    def lookup(self, entity_id: str) -> object | None:
        return self._repo.find_by_id(entity_id)
```

```typescript
// === DI CONTAINERS — TypeScript (inversify / tsyringe) ===

// Using inversify
// npm install inversify reflect-metadata
import 'reflect-metadata';
import { Container, injectable, inject } from 'inversify';

// TYPES — symbol-based service identifiers
const TYPES = {
  OrderRepository: Symbol.for('OrderRepository'),
  PaymentProcessor: Symbol.for('PaymentProcessor'),
  OrderService: Symbol.for('OrderService'),
};

// Interfaces
interface OrderRepository {
  findById(id: string): Promise<Order | null>;
  save(order: Order): Promise<void>;
}

interface PaymentProcessor {
  process(orderId: string): Promise<boolean>;
}

// Implementations
@injectable()
class PostgresOrderRepository implements OrderRepository {
  async findById(id: string): Promise<Order | null> {
    // SQL query
    return null;
  }
  async save(order: Order): Promise<void> {
    // SQL insert
  }
}

@injectable()
class StripePaymentProcessor implements PaymentProcessor {
  async process(orderId: string): Promise<boolean> {
    return true;
  }
}

@injectable()
class OrderService {
  constructor(
    @inject(TYPES.OrderRepository) private repo: OrderRepository,
    @inject(TYPES.PaymentProcessor) private payment: PaymentProcessor,
  ) {}

  async getOrder(id: string): Promise<Order | null> {
    return this.repo.findById(id);
  }
}

// Container setup — composition root
const container = new Container();
container.bind<OrderRepository>(TYPES.OrderRepository).to(PostgresOrderRepository);
container.bind<PaymentProcessor>(TYPES.PaymentProcessor).to(StripePaymentProcessor);
container.bind<OrderService>(TYPES.OrderService).to(OrderService);

// Resolve
const orderService = container.get<OrderService>(TYPES.OrderService);
```