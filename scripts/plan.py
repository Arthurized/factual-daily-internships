"""Print how many commits to make in the current UTC hour.

Every hourly run on the same day rebuilds the same plan from the date:
  - total commits today: 1-20, weight 1/k (1 is most likely, 20 rarest)
  - a random 4-hour window somewhere in the day
  - each commit lands in a random hour inside that window
"""
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
