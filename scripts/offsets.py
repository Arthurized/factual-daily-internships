"""Print N sorted random delays in seconds, spread over the next 55 minutes
but ending before midnight UTC (so commits stay on the planned day)."""
import random
import sys
from datetime import datetime, timedelta, timezone

n = int(sys.argv[1])
now = datetime.now(timezone.utc)
midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
limit = max(0, min(55 * 60, int((midnight - now).total_seconds()) - 120))
print(" ".join(str(x) for x in sorted(random.randint(0, limit) for _ in range(n))))
