# Token-bucket rate limiter

Build `TokenBucket(capacity, refill_per_second, clock=time.monotonic)` for API rate limiting.
`clock` is injectable so the bucket can be tested without sleeping.

R1: A new bucket starts full; `allow()` returns True and consumes one token while tokens remain.
R2: When there are not enough tokens, `allow()` returns False and consumes nothing.
R3: Tokens refill continuously at `refill_per_second` and never exceed `capacity`; `tokens` exposes the current level.
R4: `capacity` must be >= 1 and `refill_per_second` > 0, otherwise raise ValueError.
R5: `allow(cost)` takes a token cost (default 1); a request costing more than the available tokens is rejected.
