"""Run once locally (or from a daily OS scheduler) for maturity and overdue alerts."""

from app.db.session import SessionLocal
from app.services.operations_service import (
    advance_matured_instruments,
    generate_maturity_reminders,
    generate_overdue_action_escalations,
)


def main() -> None:
    with SessionLocal() as session:
        matured = advance_matured_instruments(session)
        count = generate_maturity_reminders(session)
        escalations = generate_overdue_action_escalations(session)
    print(f"Advanced {matured} approved instrument(s) to matured status.")
    print(f"Created {count} maturity reminder(s).")
    print(f"Created {escalations} overdue escalation notification(s). Re-running is safe.")


if __name__ == "__main__":
    main()
