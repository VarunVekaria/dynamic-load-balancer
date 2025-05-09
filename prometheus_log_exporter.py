import requests
import sys

# Configuration
PROMETHEUS_URL = "http://localhost:9090"

# Define PromQL queries for key metrics
graph_queries = {
    # Request rates
    "lb_requests_per_second":             'sum(rate(http_requests_total{job="load_balancer"}[1m]))',
    "backend_requests_per_second":        'sum(rate(http_requests_total{job="backend_servers"}[1m]))',
    "requests_per_second_per_backend":    'sum by (instance)(rate(http_requests_total{job="backend_servers"}[1m]))',
    # "backend_requests_per_second_by_instance":
    #     'sum by (instance)(rate(http_requests_total{job="backend_servers"}[1m]))',

    # Total counts
    "load_balancer_total_requests":       'sum(http_requests_total{job="load_balancer"})',
    "backend_total_requests":             'sum(http_requests_total{job="backend_servers"})',

    # Average latency
    "load_balancer_avg_latency":          'rate(http_request_duration_seconds_sum{job="load_balancer"}[1m]) / rate(http_request_duration_seconds_count{job="load_balancer"}[1m])',
    "backend_avg_latency":                'sum by (instance)(rate(http_request_duration_seconds_sum{job="backend_servers"}[1m])) / sum by (instance)(rate(http_request_duration_seconds_count{job="backend_servers"}[1m]))',

    # Latency percentiles (95th & 99th)
    "load_balancer_p95_latency":         'histogram_quantile(0.95, sum by (le)(rate(http_request_duration_seconds_bucket{job="load_balancer"}[1m])))',
    "load_balancer_p99_latency":         'histogram_quantile(0.99, sum by (le)(rate(http_request_duration_seconds_bucket{job="load_balancer"}[1m])))',
    "backend_p95_latency":               'histogram_quantile(0.95, sum by (le,instance)(rate(http_request_duration_seconds_bucket{job="backend_servers"}[1m])))',
    "backend_p99_latency":               'histogram_quantile(0.99, sum by (le,instance)(rate(http_request_duration_seconds_bucket{job="backend_servers"}[1m])))',

    # Error rates
    "load_balancer_error_rate":           'sum(rate(http_requests_total{job="load_balancer",status!~"2.."}[1m]))',
    "backend_error_rate":                 'sum by (instance)(rate(http_requests_total{job="backend_servers",status!~"2.."}[1m]))',
    
    # Success rates
    "load_balancer_success_rate":         'sum(rate(http_requests_total{job="load_balancer",status=~"2.."}[1m])) / sum(rate(http_requests_total{job="load_balancer"}[1m]))',
    "backend_success_rate":               'sum(rate(http_requests_total{job="backend_servers",status=~"2.."}[1m])) / sum(rate(http_requests_total{job="backend_servers"}[1m]))',

   "backend_overall_avg_latency":
        'rate(http_request_duration_seconds_sum{job="backend_servers"}[1m]) '
        '/ rate(http_request_duration_seconds_count{job="backend_servers"}[1m])',

    # Approximate average queue time in LB
    "avg_queue_time":
       '('
        'rate(http_request_duration_seconds_sum{job="load_balancer"}[1m]) '
        '/ rate(http_request_duration_seconds_count{job="load_balancer"}[1m])'
        ') - ('
        'rate(http_request_duration_seconds_sum{job="backend_servers"}[1m]) '
        '/ rate(http_request_duration_seconds_count{job="backend_servers"}[1m])'
        ')',

    # 1. Throughput (Requests/sec)
    "lb_requests_per_second":
        'rate(http_requests_total{job="load_balancer"}[1m])',

    # 2. Total Requests Forwarded
    "load_balancer_total_requests":
        'sum(http_requests_total{job="load_balancer"})',

    # 3. Average Latency
    "load_balancer_avg_latency":
        'rate(http_request_duration_seconds_sum{job="load_balancer"}[1m]) '
        '/ rate(http_request_duration_seconds_count{job="load_balancer"}[1m])',

    # 4. Tail Latency (P95 / P99)
    "load_balancer_p95_latency":
        'histogram_quantile(0.95, '
        'sum by (le)(rate(http_request_duration_seconds_bucket{job="load_balancer"}[1m])))',
    "load_balancer_p99_latency":
        'histogram_quantile(0.99, '
        'sum by (le)(rate(http_request_duration_seconds_bucket{job="load_balancer"}[1m])))',

    # 5. Error Rate (non-2xx)
    "load_balancer_error_rate":
        'rate(http_requests_total{job="load_balancer",status!~"2.."}[1m])',

    # 6. Backend Distribution Fairness
    #    (requests/sec per backend instance + stddev across them)
    "backend_rps_by_instance":
        'sum by (instance)(rate(http_requests_total{job="backend_servers"}[1m]))',
    "backend_distribution_stddev":
        'stddev(sum by (instance)(rate(http_requests_total{job="backend_servers"}[1m])))',

    # 7. Resource Utilization (LB CPU & Memory)
    # "load_balancer_cpu_usage":
    #     'rate(process_cpu_seconds_total{job="load_balancer"}[1m])',
    # "load_balancer_memory_bytes":
    #     'process_resident_memory_bytes{job="load_balancer"}',

    # 8. Active Connections (requires you instrument a Gauge called active_connections)
    # "load_balancer_active_connections":
    #     'active_connections{job="load_balancer"}',

    # 9. Queue Time Approximation
    # "avg_queue_time":
    #     '('
    #     'rate(http_request_duration_seconds_sum{job="load_balancer"}[1m]) '
    #     '/ rate(http_request_duration_seconds_count{job="load_balancer"}[1m])'
    #     ') - ('
    #     'rate(http_request_duration_seconds_sum{job="backend_servers"}[1m]) '
    #     '/ rate(http_request_duration_seconds_count{job="backend_servers"}[1m])'
    #     ')',
}

def query_prometheus(promql: str):
    """
    Query Prometheus API and return the 'value' for the first result.
    """
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": promql},
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("data", {}).get("result", [])
        if not results:
            return 0.0
        return float(results[0]["value"][1])
    except Exception as e:
        print(f"Error querying Prometheus ({promql}): {e}", file=sys.stderr)
        return None

def main():
    print("Fetching metrics from Prometheus...\n")
    for name, promql in graph_queries.items():
        val = query_prometheus(promql)
        print(f"{name}: {val}")

if __name__ == "__main__":
    main()
