# MQTT Home Adapter

The `MqttHomeAdapter` publishes commands and subscribes to state topics through
Paho MQTT. Install the edge dependencies to enable the real broker client:

```powershell
python -m pip install -r requirements/edge.txt
```

If `paho-mqtt` is absent, the adapter retains its legacy dry-run behavior when
TLS is not requested. Dry-run logs commands locally and does not connect to a
broker.

## Local broker

The default remains plaintext MQTT on `localhost:1883` for compatibility with
existing local-only installations:

```python
from app.adapters.infrastructure.mqtt_home_adapter import MqttHomeAdapter

mqtt = MqttHomeAdapter(
    host="localhost",
    port=1883,
)
```

Use plaintext only on a trusted local network with broker ACLs. Do not expose
port 1883 to an untrusted network.

## Remote broker with server-certificate validation

Enable TLS explicitly and use the broker's TLS listener (commonly port 8883):

```python
mqtt = MqttHomeAdapter(
    host="mqtt.example.internal",
    port=8883,
    tls_enabled=True,
    tls_ca_certs="certs/home-broker-ca.pem",
)
```

When `tls_ca_certs` is `None`, Paho uses the operating system's trusted CA
store. In both cases, the broker certificate and hostname are verified. TLS
configuration is applied before the network connection is opened.

## Mutual TLS

For brokers requiring client-certificate authentication, provide both PEM
files:

```python
mqtt = MqttHomeAdapter(
    host="mqtt.example.internal",
    port=8883,
    tls_enabled=True,
    tls_ca_certs="certs/home-broker-ca.pem",
    tls_certfile="certs/jarvis-client.pem",
    tls_keyfile="certs/jarvis-client.key",
)
```

The client certificate and private key must be supplied together. Keep private
keys and broker passwords in the configured secret store; never commit them.

## Failure behavior and limits

- TLS is opt-in so existing local plaintext deployments do not change silently.
- If TLS is requested without Paho, initialization fails instead of falling
  back to plaintext. An explicit `dry_run=True` still performs no network I/O.
- Invalid CA/client-certificate configuration or a Paho TLS setup error aborts
  initialization; the adapter does not downgrade.
- There is no `tls_insecure_set(True)` path. Certificate and hostname
  verification remain mandatory.
- TLS protects transport and broker identity; broker ACLs and topic-level
  authorization must still be configured independently.
- The adapter does not infer or change the port. Select the port exposed by the
  broker's TLS listener.
