"""Work out how to reverse a recorded change, before anything is changed.

- `query.py`: `PlanUndo`, which record (the last one not undone, by default)
- `handler.py`: builds the commands that put each issue back, from the record's before
  values, and reads the issues now, to flag those changed since
- `view.py`: `UndoPlan`: the commands, their preview, and what can't be undone

Front ends run the plan through the bulk engine (`bus.bulk.run(plan.commands,
change=plan.change(), undoes=plan.entry.id)`), so it asks once and is itself recorded.
"""
