# Template: the compose service fills in __RECEIVER__ and, only when ALERT_WEBHOOK_URL is set, adds the webhook receiver below.
# With no address set, alerts only appear in the Prometheus/Grafana screens.
route:
  receiver: __RECEIVER__
  group_by: [alertname]
  group_wait: 30s
  repeat_interval: 4h
receivers:
  - name: nobody
