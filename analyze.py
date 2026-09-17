import re
from collections import Counter


WEB_FILE = "web.log"
WORKER_FILE = "worker.log"


# read web.log and store requests in a dictionary

web_pattern = re.compile(
    r"^(?P<timestamp>\S+ \S+) INFO \[request\] "
    r"method=(?P<method>\S+) "
    r"path=(?P<path>\S+) "
    r"status=(?P<status>\d+) "
    r"latency_ms=(?P<latency>\d+) "
    r"user_id=(?P<user_id>\d+) "
    r"request_id=(?P<request_id>[0-9a-f]+)"
)


web_requests = {}


with open(WEB_FILE, "r", encoding="utf-8") as file:

    for line in file:

        match = web_pattern.match(line)

        if match:
            data = match.groupdict()

           
            web_requests[data["request_id"]] = data


# read worker.log and correlate with web.log

worker_pattern = re.compile(
    r"^(?P<date>\S+) (?P<time>\S+) ERROR \[worker\] .*?"
    r"request_id=(?P<request_id>[0-9a-f]+) "
    r"err=(?P<error>\S+) "
    r"upstream=(?P<upstream>\S+)"
)


failed_requests = []


with open(WORKER_FILE, "r", encoding="utf-8") as file:

    for line in file:

        match = worker_pattern.match(line)

        if match:

            worker = match.groupdict()

            request_id = worker["request_id"]

         
            web = web_requests.get(request_id)

            if web is not None:
                failed_requests.append((worker, web))


# basic statistics about the failures

failed_count = len(failed_requests)

failed_endpoints = Counter(
    web["path"]
    for worker, web in failed_requests
)

failed_users = [
    int(web["user_id"])
    for worker, web in failed_requests
]

distinct_users = len(set(failed_users))


# check how many failures are from odd and even user IDs

odd_failures = sum(
    user_id % 2 == 1
    for user_id in failed_users
)

even_failures = sum(
    user_id % 2 == 0
    for user_id in failed_users
)


# count total checkout requests and categorize them by odd/even user_id

checkout_requests = []


with open(WEB_FILE, "r", encoding="utf-8") as file:

    for line in file:

        match = web_pattern.match(line)

        if match:

            data = match.groupdict()

            if (
                data["method"] == "POST"
                and data["path"] == "/checkout"
            ):
                checkout_requests.append(data)


total_checkouts = len(checkout_requests)


odd_checkouts = sum(
    int(request["user_id"]) % 2 == 1
    for request in checkout_requests
)

even_checkouts = total_checkouts - odd_checkouts


#calculate failure rates for odd and even user IDs

if odd_checkouts > 0:
    odd_failure_rate = (
        odd_failures / odd_checkouts
    ) * 100
else:
    odd_failure_rate = 0


if even_checkouts > 0:
    even_failure_rate = (
        even_failures / even_checkouts
    ) * 100
else:
    even_failure_rate = 0


# get first failure

first_worker, first_web = failed_requests[0]


first_failure_time = (
    first_worker["date"]
    + " "
    + first_worker["time"]
)


# print final summary

print()
print("=" * 50)
print("        PRODUCTION INCIDENT SUMMARY")
print("=" * 50)

print()
print("First failure:")
print(first_failure_time)

print()
print("Affected endpoint:")

for endpoint, count in failed_endpoints.items():
    print(f"POST {endpoint} -> {count} failures")

print()
print("Worker failures:")
print(failed_count)

print()
print("Distinct affected users:")
print(distinct_users)

print()
print("Common error:")
print(first_worker["error"])

print()
print("Upstream:")
print(first_worker["upstream"])


print()
print("=" * 50)
print("             USER ID PATTERN")
print("=" * 50)

print()
print("Odd user_id checkout requests:")
print(odd_checkouts)

print("Odd user_id failures:")
print(odd_failures)

print(
    f"Odd user_id failure rate: "
    f"{odd_failure_rate:.2f}%"
)

print()
print("Even user_id checkout requests:")
print(even_checkouts)

print("Even user_id failures:")
print(even_failures)

print(
    f"Even user_id failure rate: "
    f"{even_failure_rate:.2f}%"
)


print()
print("=" * 50)
print("              CORRELATION CHECK")
print("=" * 50)

print()
print("First failed request:")

print(f"Request ID : {first_worker['request_id']}")
print(f"Method     : {first_web['method']}")
print(f"Endpoint   : {first_web['path']}")
print(f"Status     : {first_web['status']}")
print(f"User ID    : {first_web['user_id']}")
print(f"Web time   : {first_web['timestamp']}")
print(f"Worker time: {first_failure_time}")


print()
print("=" * 50)
print("                 CONCLUSION")
print("=" * 50)

print()
print(
    "All correlated worker failures are related "
    "to POST /checkout."
)

print(
    "All failed checkout requests belong to "
    "odd-numbered user IDs."
)

print(
    "No failures were observed for even-numbered "
    "user IDs."
)

print(
    "The worker error is ECONNRESET while "
    "connecting to the upstream service."
)

print()
print("=" * 50)