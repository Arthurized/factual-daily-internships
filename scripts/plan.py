"""Something useful. Probably..."""
import random
import re
import subprocess
from datetime import datetime, timezone

WINDOW_HOURS = 4
BOT_EMAIL = "219266778+Arthurized@users.noreply.github.com"
BOT_MESSAGE = re.compile(r"^(Add internship: |Add fact$)")

now = datetime.now(timezone.utc)
today = now.date().isoformat()
rng = random.Random("daily-log-" + today)

counts = range(1, 21)
total = rng.choices(counts, weights=[1 / k for k in counts])[0]
start = rng.randrange(24 - WINDOW_HOURS + 1)
hours = [start + rng.randrange(WINDOW_HOURS) for _ in range(total)]
planned_so_far = sum(1 for h in hours if h <= now.hour)

log = subprocess.run(
    ["git", "log", f"--since={today}T00:00:00Z", f"--author={BOT_EMAIL}", "--format=%s"],
    capture_output=True, text=True, check=True,
).stdout.splitlines()
done = sum(1 for s in log if BOT_MESSAGE.match(s))

print(max(0, planned_so_far - done))
