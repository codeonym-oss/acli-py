"""The application layer: use cases as CQRS messages, handled behind one mediator.

- `commands/<use_case>/`: `command.py` (the message) and `handler.py`
- `queries/<use_case>/`: `query.py`, `handler.py` and `view.py` (the read model front ends show)
- `events/<event>/`: `event.py` and `subscribers.py`
- `ports.py`: what use cases need from outside (`IssueReader`…), implemented by infrastructure
- `behaviors/`: what wraps every message (activity, cache, announce; later confirm, bulk, audit)

It depends on the domain only. `messages.py` and `handlers.py` hold the use cases written
before this layout; they move into their own packages one by one (see docs/adr/0001).
"""
