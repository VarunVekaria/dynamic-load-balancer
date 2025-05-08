import requests
import sys

# Configuration
PROMETHEUS_URL = "http://localhost:9090"

# Define PromQL queries for key metrics
graph_queries = {
    "requests per second per backend": 'sum by (instance)(rate(http_requests_total{job="backend_servers"}[1m]))',
    "load_balancer_total_requests": 'sum(http_requests_total{job="load_balancer"})',
    "backend_total_requests": 'sum(http_requests_total{job="backend_servers"})',
    "load_balancer_avg_latency": 'rate(http_request_duration_seconds_sum{job="load_balancer"}[30s]) / rate(http_request_duration_seconds_count{job="load_balancer"}[1m])',
    "backend_avg_latency": 'sum by (instance)(rate(http_request_duration_seconds_sum{job="backend_servers"}[30s])) / sum by (instance)(rate(http_request_duration_seconds_count{job="backend_servers"}[1m]))',
    "load_balancer_error_rate": 'sum(rate(http_requests_total{job="load_balancer",status!~"2.."}[1m]))',
    "backend_error_rate": 'sum by (instance)(rate(http_requests_total{job="backend_servers",status!~"2.."}[1m]))'
}


def query_prometheus(promql: str):
    """
    Query Prometheus API and return the 'value' for the first result.
    """
    resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": promql})
    if resp.status_code != 200:
        print(f"Error querying Prometheus: {resp.status_code}", file=sys.stderr)
        return None
    data = resp.json()
    results = data.get("data", {}).get("result", [])
    if not results:
        return 0.0
    # Each result has ['value'] = [ timestamp, value_str ]
    return float(results[0]["value"][1])


def main():
    print("Fetching metrics from Prometheus...\n")
    metrics = {}
    for name, promql in graph_queries.items():
        val = query_prometheus(promql)
        metrics[name] = val
    # Pretty-print
    for key, value in metrics.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    main()
