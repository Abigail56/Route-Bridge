# Template: the compose service fills in __INTERNAL_API_KEY__ when it starts. Do not put real keys in this file.
global:
  scrape_interval: 15s
  evaluation_interval: 15s
rule_files:
  - /etc/prometheus/alerts.yml
alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]
scrape_configs:
  - job_name: routebridge-api
    metrics_path: /metrics
    http_headers:
      X-API-Key:
        values: ["__INTERNAL_API_KEY__"]
    static_configs:
      - targets: ["api:8000"]
