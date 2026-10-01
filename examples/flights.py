"""Live Google Flights search. Calls TypeSafe; never selects or books a flight."""

import argparse
import base64
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from datetime import date, timedelta

from jev_ultrafast import Agent

URL = "https://www.google.com/travel/flights?hl=en"
FLIGHT_DATE = date.today() + timedelta(days=7)
FLIGHT_DATE_ISO = FLIGHT_DATE.isoformat()
FLIGHT_DATE_GOAL = f"{FLIGHT_DATE.strftime('%B')} {FLIGHT_DATE.day}, {FLIGHT_DATE.year}"
FLIGHT_DATE_SHORT = f"{FLIGHT_DATE.strftime('%a, %b')} {FLIGHT_DATE.day}"
FLIGHT_DATE_LONG = f"{FLIGHT_DATE.strftime('%A, %B')} {FLIGHT_DATE.day}"
GOALS = (
    f"Find one-way flights from Zurich to London on {FLIGHT_DATE_GOAL}, for one adult in economy. "
    "Stop when matching flight options are visible. Do not select or book a flight."
)


def verify(page):
    """Independent checks on the resulting page, not the model's DONE answer."""
    parsed = urlparse(page["url"])
    encoded = parse_qs(parsed.query).get("tfs", [""])[0]
    try:
        date_in_url = FLIGHT_DATE_ISO.encode() in base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except ValueError:
        date_in_url = False
    actions = page["actions"]
    values = {a["label"].strip(): a.get("value") for a in actions}
    flights = [a["label"] for a in actions if "Select flight" in a["label"]]
    checks = {
        "search_page": parsed.hostname == "www.google.com" and parsed.path == "/travel/flights/search",
        "one_way": values.get("Change ticket type. One way") == "One way",
        "origin": values.get("Where from?") == "Zürich",
        "destination": values.get("Where to?") == "London",
        "date": values.get("Departure") == FLIGHT_DATE_SHORT,
        "year": date_in_url or f"departing {FLIGHT_DATE_ISO}" in page["text"],
        "results": bool(flights) and all(FLIGHT_DATE_LONG in f for f in flights),
    }
    return {"passed": all(checks.values()), "checks": checks, "visible_flights": flights}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/flights/latest")
    parser.add_argument("--keep-open", action="store_true")
    args = parser.parse_args()
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)
    agent = Agent(URL, GOALS)
    try:
        for state in agent.run():
            last = state["history"][-1] if state["history"] else {}
            print(state["elapsed_ms"], state["status"], last.get("action", ""), flush=True)
    finally:
        state = agent.snapshot()
        state["verification"] = verify(state["page"])
        (folder / "state.json").write_text(json.dumps(state, indent=2))
        (folder / "session.json").write_text(
            json.dumps({"target": agent.browser.target, "session": agent.browser.session})
        )
        if not args.keep_open:
            agent.close()
    print(json.dumps(state["verification"], indent=2))
    if not state["verification"]["passed"]:
        raise SystemExit("Final page did not satisfy the route/date checks")


if __name__ == "__main__":
    main()
