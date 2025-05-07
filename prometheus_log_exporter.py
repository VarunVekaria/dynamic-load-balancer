import requests
import csv
from datetime import datetime

PROMETHEUS_URL = "http://localhost:9090"

# PromQL queries for metrics
PROMQL = {
    "load_balancer_total_requests": 'sum(http_requests_total{job="load_balancer"})',
    "backend_total_requests": 'sum by (instance)(http_requests_total{job="backend_servers"})',
    "avg_latency": 'rate(http_request_duration_seconds_sum[1m]) / rate(http_request_duration_seconds_count[1m])',
    "error_rate": 'sum(rate(http_requests_total{status!~"2.."}[1m]))'
}

def query_prometheus(promql):
    response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": promql})
    result = response.json()
    if result["status"] == "success" and result["data"]["result"]:
        return result["data"]["result"]
    return []

def extract_value(results, label=None):
    if not results:
        return 0
    if label:
        return {item['metric'].get(label, 'unknown'): float(item['value'][1]) for item in results}
    return float(results[0]['value'][1])

def log_to_csv(data):
    filename = "benchmark_results.csv"
    fieldnames = list(data.keys())

    try:
        with open(filename, 'x', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(data)
    except FileExistsError:
        with open(filename, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(data)

def run_benchmark_record():
    data = {
        "timestamp": datetime.now().isoformat(),
        "load_balancer_total_requests": extract_value(query_prometheus(PROMQL["load_balancer_total_requests"])),
        "error_rate": extract_value(query_prometheus(PROMQL["error_rate"])),
        "avg_latency": extract_value(query_prometheus(PROMQL["avg_latency"])),
    }

    backend_counts = extract_value(query_prometheus(PROMQL["backend_total_requests"]), label="instance")
    for instance, count in backend_counts.items():
        data[f"requests_{instance}"] = count

    log_to_csv(data)
    print("✅ Benchmark data logged to CSV.")

if __name__ == "__main__":
    run_benchmark_record()
