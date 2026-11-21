"""Something useful. Probably..."""
import random
from datetime import datetime, timezone

WINDOW_HOURS = 4

now = datetime.now(timezone.utc)
rng = random.Random("daily-log-" + now.date().isoformat())

counts = range(1, 21)
total = rng.choices(counts, weights=[1 / k for k in counts])[0]
start = rng.randrange(24 - WINDOW_HOURS + 1)
hours = [start + rng.randrange(WINDOW_HOURS) for _ in range(total)]

print(hours.count(now.hour))
