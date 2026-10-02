"""The application layer: use cases as CQRS messages, handled behind one mediator.

- `commands/<use_case>/`: `command.py` (the message) and `handler.py`
- `queries/<use_case>/`: `query.py`, `handler.py` and `view.py` (the read model front ends show)
- `events/<event>/`: `event.py` and `subscribers.py`
- `ports.py`: what use cases need from outside (`IssueReader`…), implemented by infrastructure
- `behaviors/`: what wraps every message (activity, cache, confirm, announce)
- `bulk.py`, `audit.py`: the bulk engine and the audit trail
- `errors.py`, `dry_run.py`, `inputs.py`: what front ends catch, a dry run's plan, `IssueInput`

It depends on the domain only (see docs/adr/0001-layers.md).
"""
