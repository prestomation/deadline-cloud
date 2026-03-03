#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Runs inside a network namespace created by: sudo unshare --net bash <this script>
# The namespace has no internet routes — only loopback. A TCP-to-Unix bridge
# forwards proxy traffic to the MITM proxy's Unix socket on the shared filesystem.
set -euo pipefail

ip link set lo up

# TCP-to-Unix bridge: tests connect to 127.0.0.1:8888, bridge relays to proxy's Unix socket
python3 -c "
import socket, threading, select, ssl

def relay(a, b):
    a.setblocking(False)
    b.setblocking(False)
    while True:
        r, _, _ = select.select([a, b], [], [], 60)
        if not r:
            break
        for s in r:
            try:
                data = s.recv(65536)
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                # CRITICAL: Do not remove. See connect_proxy.py _relay for details.
                # Without this, the broad `except ssl.SSLError` below kills the
                # connection with 0 bytes relayed, causing RemoteDisconnected.
                continue
            except (OSError, ConnectionError, ssl.SSLError):
                return
            if not data:
                return
            dest = b if s is a else a
            try:
                dest.setblocking(True)
                dest.sendall(data)
                dest.setblocking(False)
            except (OSError, ConnectionError, ssl.SSLError):
                return

def handle(client):
    try:
        remote = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        remote.connect('/tmp/deadline_proxy.sock')
        relay(client, remote)
    except Exception:
        pass
    finally:
        client.close()

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('127.0.0.1', 8888))
srv.listen(64)
print('Bridge listening on 127.0.0.1:8888', flush=True)
while True:
    client, _ = srv.accept()
    threading.Thread(target=handle, args=(client,), daemon=True).start()
" &
BRIDGE_PID=$!

# Bridge credential endpoint if using container credentials
if [ -n "${AWS_CONTAINER_CREDENTIALS_FULL_URI:-}" ]; then
  CRED_PORT=$(echo "$AWS_CONTAINER_CREDENTIALS_FULL_URI" | \
              sed -n 's|.*://[^:]*:\([0-9]*\).*|\1|p')
  if [ -n "$CRED_PORT" ]; then
    socat "TCP-LISTEN:${CRED_PORT},fork,reuseaddr,bind=127.0.0.1" \
          UNIX-CONNECT:/tmp/deadline_cred_bridge.sock &
  fi
fi

sleep 0.5

export HTTPS_PROXY=http://127.0.0.1:8888
export HTTP_PROXY=http://127.0.0.1:8888
export AWS_CA_BUNDLE=/tmp/deadline_proxy_ca.crt
export SSL_CERT_FILE=/tmp/deadline_proxy_ca.crt
export REQUESTS_CA_BUNDLE=/tmp/deadline_proxy_ca.crt

[ -f "$AWS_CA_BUNDLE" ] || { echo "ERROR: CA cert not found"; exit 1; }
echo "OK: Using MITM CA bundle at $AWS_CA_BUNDLE"

# Verify namespace isolation
python3 -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect(('1.1.1.1', 443))
    print('ERROR: Direct internet access possible — namespace isolation broken!')
    sys.exit(1)
except OSError:
    print('OK: Direct internet access blocked')
finally:
    s.close()
"

# Verify proxy reachable
python3 -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect(('127.0.0.1', 8888))
    print('OK: Proxy reachable on 127.0.0.1:8888')
except OSError as e:
    print(f'ERROR: Cannot reach proxy: {e}')
    sys.exit(1)
finally:
    s.close()
"

exec python3 -m pytest --no-cov -vvv -s --numprocesses=1 -m proxy test/integ/ --tb=long
