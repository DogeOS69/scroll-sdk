# Dogecoin ZMQ Configuration

This document explains the ZMQ (ZeroMQ) configuration added to the Dogecoin Helm chart for real-time blockchain data streaming.

## What is ZMQ?

ZMQ (ZeroMQ) is a high-performance asynchronous messaging library that enables real-time data streaming from blockchain nodes. Instead of polling for new data, applications can subscribe to ZMQ endpoints to receive instant notifications.

## ZMQ Endpoints

The Dogecoin chart now includes four ZMQ endpoints:

| Endpoint | Port | Description |
|----------|------|-------------|
| `zmqpubrawblock` | 28332 | Raw block data as they are mined |
| `zmqpubrawtx` | 28333 | Raw transaction data as they are received |
| `zmqpubhashtx` | 28334 | Transaction hashes as they are received |
| `zmqpubhashblock` | 28335 | Block hashes as they are mined |

## Configuration

### Dogecoin Node Configuration

The ZMQ settings are automatically added to the `dogecoin.conf` file:

```conf
zmqpubrawblock=tcp://0.0.0.0:28332
zmqpubrawtx=tcp://0.0.0.0:28333
zmqpubhashtx=tcp://0.0.0.0:28334
zmqpubhashblock=tcp://0.0.0.0:28335
```

### Service Ports

The Kubernetes service exposes these ports:

```yaml
service:
  zmqRawBlockPort: 28332
  zmqRawTxPort: 28333
  zmqHashTxPort: 28334
  zmqHashBlockPort: 28335
```

## Usage with Blockbook

To use ZMQ with Blockbook, configure the `messageQueueBinding` in your blockbook values:

```yaml
blockbook:
  messageQueueBinding: "tcp://dogecoin-testnet:28332"
```

## Benefits

1. **Real-time Updates**: Instant notifications when new blocks or transactions arrive
2. **Reduced Latency**: No polling delays
3. **Better Performance**: Lower CPU and network overhead
4. **Scalability**: Multiple applications can subscribe to the same ZMQ endpoints

## Testing ZMQ Connection

You can test the ZMQ connection using a simple Python script:

```python
import zmq
import json

# Connect to ZMQ endpoint
context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.connect("tcp://dogecoin-testnet:28332")
socket.setsockopt(zmq.SUBSCRIBE, b"rawblock")

# Listen for messages
while True:
    message = socket.recv()
    print(f"Received block: {message.hex()}")
```

## Security Considerations

- ZMQ endpoints are only accessible within the Kubernetes cluster
- No authentication is required for ZMQ (by design)
- Consider network policies if you need additional security

## Troubleshooting

1. **Check if ZMQ is enabled**: Look for ZMQ configuration in the dogecoin pod logs
2. **Verify port exposure**: Ensure the service is exposing the ZMQ ports
3. **Test connectivity**: Use the Python script above to test the connection
4. **Check firewall rules**: Ensure no network policies are blocking the ports
