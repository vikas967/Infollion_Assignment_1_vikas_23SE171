# Log Reading Assignment – Incident Investigation

## Overview

The issue reported by support was that some users were able to place orders, but those orders did not appear in the system.

I investigated both `web.log` and `worker.log`. The main thing I used to connect the two files was the `request_id`, because the web log contains the original request information while the worker log contains the later asynchronous processing result.

The main finding is that the problem is related to `POST /checkout` requests for odd-numbered `user_id`s. The worker is getting `ECONNRESET` while communicating with `10.0.3.44:8443`.

---

## 1. When did the problem start?

The first relevant worker failure I found was:

```text
2026-07-02 14:32:42.692 ERROR [worker] upstream call failed request_id=16ce72300cf58a32 err=ECONNRESET upstream=10.0.3.44:8443 (retries exhausted)
```

I did not use the first `ERROR` in `worker.log` as the incident start because there are earlier errors from `metrics-worker` related to analytics uploads. Those errors appear to be a separate issue.

I used the `request_id` from the first checkout worker failure:

```text
16ce72300cf58a32
```

The matching entry in `web.log` is:

```text
2026-07-02 14:32:40.073 INFO [request] method=POST path=/checkout status=202 latency_ms=36 user_id=59787 request_id=16ce72300cf58a32
```

This gives me a clear correlation:

- Web request time: `14:32:40.073`
- Worker failure time: `14:32:42.692`
- Request ID: `16ce72300cf58a32`
- Endpoint: `POST /checkout`
- User ID: `59787`
- Worker error: `ECONNRESET`

So I consider **2026-07-02 14:32:42.692** the start of the observed checkout processing failure.

---

## 2. Which endpoint is affected?

The affected endpoint is:

```text
POST /checkout
```

I found **2,385 worker failures** that could be correlated back to requests in `web.log`.

All of those correlated failures were for the same endpoint:

```text
POST /checkout -> 2,385 failures
```

They also all had HTTP status `202` in the web log.

This is important because `202` means the web application accepted the request for processing. It does not necessarily mean that the asynchronous work has completed successfully.

For example, the first correlated request was:

```text
2026-07-02 14:32:40.073 INFO [request] method=POST path=/checkout status=202 latency_ms=36 user_id=59787 request_id=16ce72300cf58a32
```

A few seconds later, the worker reported:

```text
2026-07-02 14:32:42.692 ERROR [worker] upstream call failed request_id=16ce72300cf58a32 err=ECONNRESET upstream=10.0.3.44:8443 (retries exhausted)
```

This matches the support report quite well: from the web application's point of view the request was accepted, but the background processing later failed.

---

## 3. What do the failing requests have in common?

The strongest pattern I found is the `user_id`.

### Odd/even user ID comparison

There were:

| Type | Checkout requests | Failures | Failure rate |
|---|---:|---:|---:|
| Odd `user_id` | 4,843 | 2,385 | 49.25% |
| Even `user_id` | 5,032 | 0 | 0.00% |
| **Total** | **9,875** | **2,385** | **24.15%** |

So every correlated failure was associated with an **odd-numbered user ID**:

```text
Odd user_id failures:  2,385
Even user_id failures: 0
```

This is a strong pattern because there were also more than five thousand even-user checkout requests, but none of those had a correlated worker failure.

For example, the first failed request had:

```text
user_id=59787
```

which is odd.

The worker-side error also has another common pattern:

```text
err=ECONNRESET
upstream=10.0.3.44:8443
(retries exhausted)
```

The same `ECONNRESET` / upstream combination appears across the correlated worker failures.

### What I think this means

The logs strongly suggest that the issue is not a general checkout failure affecting everyone. It is concentrated around one group of users, specifically odd-numbered user IDs.

The odd/even split makes me suspicious of something such as request routing, sharding, partitioning, or another user-ID-based assignment. However, I would treat that as a hypothesis because these logs do not directly show the routing configuration.

---

## 4. How many distinct users were affected?

There were:

```text
2,385 failed requests
```

but:

```text
2,335 distinct users
```

I calculated this using the unique `user_id` values from the correlated failed requests.

This distinction matters because one user can have more than one failed checkout request.

So I would report the customer impact as:

> **2,335 distinct users were affected, based on 2,385 correlated failed checkout requests.**

---

# Bonus: Does anything suggest the root cause?

There are two useful clues.

### 1. The upstream connection is being reset

Every correlated worker failure has:

```text
err=ECONNRESET
upstream=10.0.3.44:8443
(retries exhausted)
```

`ECONNRESET` means the connection was unexpectedly reset while the worker was communicating with the upstream service.

The fact that retries were exhausted suggests the worker could not successfully complete that upstream call after retrying.

### 2. The failures only happen for odd user IDs

The other unusual pattern is:

```text
Odd user IDs:
2,385 failures out of 4,843 checkout requests

Even user IDs:
0 failures out of 5,032 checkout requests
```

Because of this, I would investigate whether odd and even users are routed differently somewhere in the checkout system.

For example, I would check:

- whether user IDs are used as a shard/partition key
- whether odd users are routed to a particular backend instance
- whether `10.0.3.44:8443` is associated with only one routing group
- whether that upstream instance has connection or capacity problems
- whether there is a configuration difference between the two groups

I would **not call this the confirmed root cause** from these logs alone. The logs provide strong evidence for the upstream connection problem and the odd-user pattern, but they do not show the actual routing or infrastructure configuration.

---

# Investigation Process

- I started by reading both log files and checking what information was available in each one.
- I noticed that `web.log` contains `request_id`, and `worker.log` also contains `request_id`, so I used it as the correlation key.
- I stored the web requests by `request_id` so that worker failures could be matched back to their original HTTP requests.
- I looked specifically at worker errors instead of treating every `ERROR` in the file as part of the incident.
- I found earlier `metrics-worker` errors (`AnalyticsUploadTimeout`), but those are related to the analytics pipeline and do not correlate with the checkout failures, so I treated them as unrelated.
- I found the first relevant checkout worker failure at `2026-07-02 14:32:42.692`.
- After correlation, all 2,385 relevant worker failures mapped to `POST /checkout`.
- I compared the `user_id` values and found that all 2,385 failures belonged to odd-numbered users.
- I compared this with all 9,875 checkout requests to calculate the odd/even failure rates.
- Finally, I counted unique `user_id` values to calculate the actual number of distinct affected users: 2,335.

---

# Final Summary

The incident affects asynchronous processing of `POST /checkout` requests.

The first relevant failure was observed at:

```text
2026-07-02 14:32:42.692
```

The worker failed with:

```text
ECONNRESET
```

while connecting to:

```text
10.0.3.44:8443
```

There were:

```text
2,385 failed checkout jobs
2,335 distinct affected users
```

The most noticeable pattern is that **all failed requests belonged to odd-numbered user IDs**, while none of the even-numbered checkout requests failed in the correlated worker data.

Based on the available logs, I would investigate the routing/sharding/partitioning path for odd user IDs and the health/configuration of the upstream service at `10.0.3.44:8443`.
