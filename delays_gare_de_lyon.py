import datetime
import re
import requests
from functools import lru_cache
from google.transit import gtfs_realtime_pb2

# UIC codes for Paris Gare de Lyon
STATION_CODES = ["87686030", "87686006"]
# Build list of stop_ids as they appear in the GTFS-RT feed
STOP_IDS = [f"StopPoint:OCETGV INOUI-{code}" for code in STATION_CODES]

FEED_URL = "https://proxy.transport.data.gouv.fr/resource/sncf-tgv-gtfs-rt-trip-updates"

# API endpoints to resolve station names
FRENCH_STATIONS_URL = (
    "https://data.sncf.com/api/records/1.0/search/"
    "?dataset=gares-de-voyageurs&rows=1&q="
)
SWISS_STATIONS_URL = "https://transport.opendata.ch/v1/locations?query="


def fetch_feed(url: str) -> gtfs_realtime_pb2.FeedMessage:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    return feed


@lru_cache(maxsize=512)
def station_name(stop_id: str) -> str:
    """Resolve a GTFS stop_id to a human readable station name."""
    code = stop_id.split("-")[-1]
    if code.startswith("85"):
        # Swiss stop using transport.opendata.ch
        resp = requests.get(SWISS_STATIONS_URL + code, timeout=10)
        if resp.ok:
            j = resp.json()
            if j.get("stations"):
                return j["stations"][0]["name"]
    else:
        resp = requests.get(FRENCH_STATIONS_URL + code, timeout=10)
        if resp.ok:
            j = resp.json()
            if j.get("records"):
                return j["records"][0]["fields"].get("nom", code)
    return code


def parse_train_number(trip_id: str) -> str:
    m = re.search(r"[A-Z]+(\d+)", trip_id)
    return m.group(1) if m else trip_id


def get_delays(feed: gtfs_realtime_pb2.FeedMessage):
    updates = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        trip_upd = entity.trip_update
        trip_id = trip_upd.trip.trip_id
        stop_times = trip_upd.stop_time_update
        for idx, stu in enumerate(stop_times):
            if stu.stop_id in STOP_IDS and stu.HasField("arrival"):
                if stu.arrival.HasField("delay") and stu.arrival.delay > 0:
                    arrival_time = datetime.datetime.fromtimestamp(stu.arrival.time)
                    origin = station_name(stop_times[0].stop_id)
                    swiss_stops = [
                        station_name(st.stop_id)
                        for st in stop_times[: idx + 1]
                        if st.stop_id.split("-")[-1].startswith("85")
                    ]
                    updates.append(
                        {
                            "arrival": arrival_time,
                            "train": parse_train_number(trip_id),
                            "origin": origin,
                            "delay": stu.arrival.delay,
                            "swiss_stops": swiss_stops,
                        }
                    )
    return sorted(updates, key=lambda x: x["arrival"])


if __name__ == "__main__":
    feed = fetch_feed(FEED_URL)
    delays = get_delays(feed)
    for upd in delays:
        arrival = upd["arrival"].isoformat()
        train = upd["train"]
        origin = upd["origin"]
        delay = upd["delay"]
        swiss = ", ".join(upd["swiss_stops"]) if upd["swiss_stops"] else "-"
        print(f"{arrival} | Train {train} | from {origin} | Swiss stops: {swiss} | +{delay}s")
    print(f"Total delayed trains: {len(delays)}")
