import datetime
import requests
from google.transit import gtfs_realtime_pb2

# UIC codes for Paris Gare de Lyon
STATION_CODES = ["87686030", "87686006"]
# Build list of stop_ids as they appear in the GTFS-RT feed
STOP_IDS = [f"StopPoint:OCETGV INOUI-{code}" for code in STATION_CODES]

FEED_URL = "https://proxy.transport.data.gouv.fr/resource/sncf-tgv-gtfs-rt-trip-updates"


def fetch_feed(url: str) -> gtfs_realtime_pb2.FeedMessage:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    return feed


def get_delays(feed: gtfs_realtime_pb2.FeedMessage):
    updates = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        trip = entity.trip_update
        trip_id = trip.trip.trip_id
        for stu in trip.stop_time_update:
            if stu.stop_id in STOP_IDS and stu.HasField("arrival"):
                if stu.arrival.HasField("delay") and stu.arrival.delay > 0:
                    arrival_time = datetime.datetime.fromtimestamp(stu.arrival.time)
                    updates.append((arrival_time, trip_id, stu.arrival.delay))
    return sorted(updates)


if __name__ == "__main__":
    feed = fetch_feed(FEED_URL)
    delays = get_delays(feed)
    for arrival, trip_id, delay in delays:
        print(f"{arrival.isoformat()} {trip_id} +{delay} sec")
    print(f"Total delayed trains: {len(delays)}")
