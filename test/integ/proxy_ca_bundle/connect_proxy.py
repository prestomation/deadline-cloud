# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""MITM HTTP CONNECT proxy listening on a Unix domain socket.

Generates an ephemeral CA at startup and issues per-host certificates on the fly.
Clients MUST trust the generated CA (via AWS_CA_BUNDLE) or TLS verification fails,
proving that all code respects the CA bundle configuration.
"""

import datetime
import json
import os
import select
import socket
import ssl
import sys
import threading
from typing import Dict, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


class _CertAuthority:
    """Ephemeral CA that generates per-host TLS certificates on the fly."""

    def __init__(self, ca_cert_path: str):
        self._lock = threading.Lock()
        self._cache: Dict[str, Tuple[str, str]] = {}  # host -> (cert_path, key_path)
        self._ca_cert_path = ca_cert_path
        self._cert_dir = os.path.dirname(ca_cert_path)

        # Generate CA key + cert
        self._ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Deadline Proxy Test CA")])
        self._ca_cert = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(self._ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(days=1))
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True, key_cert_sign=True, crl_sign=True,
                    content_commitment=False, key_encipherment=False,
                    data_encipherment=False, key_agreement=False,
                    encipher_only=False, decipher_only=False,
                ),
                critical=True,
            )
            .sign(self._ca_key, hashes.SHA256())
        )

        # Write CA cert (this is what AWS_CA_BUNDLE points to)
        # Append system CAs so credential endpoints etc. also work
        with open(ca_cert_path, "wb") as f:
            f.write(self._ca_cert.public_bytes(serialization.Encoding.PEM))
            # Append system CA bundle so non-MITM connections (cred endpoint) still verify
            for sys_ca in [
                "/etc/ssl/certs/ca-certificates.crt",
                "/etc/pki/tls/certs/ca-bundle.crt",
            ]:
                if os.path.exists(sys_ca):
                    with open(sys_ca, "rb") as sc:
                        f.write(b"\n")
                        f.write(sc.read())
                    break

        print(f"CA cert written to {ca_cert_path}", flush=True)

    def get_cert_for_host(self, hostname: str) -> Tuple[str, str]:
        """Return (cert_path, key_path) for a hostname, generating if needed."""
        with self._lock:
            if hostname in self._cache:
                return self._cache[hostname]

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
            .issuer_name(self._ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow() - datetime.timedelta(hours=1))
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(hours=1))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(hostname)]),
                critical=False,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
            .sign(self._ca_key, hashes.SHA256())
        )

        safe = hostname.replace(".", "_").replace(":", "_")
        cert_path = os.path.join(self._cert_dir, f"{safe}.crt")
        key_path = os.path.join(self._cert_dir, f"{safe}.key")

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            ))

        with self._lock:
            self._cache[hostname] = (cert_path, key_path)
        return cert_path, key_path


class MitmProxy:
    """MITM HTTP CONNECT proxy on a Unix domain socket."""

    def __init__(self, sock_path: str, ca_cert_path: str):
        self.sock_path = sock_path
        self.ca = _CertAuthority(ca_cert_path)
        self.connection_count = 0
        self.bytes_relayed = 0
        self.hosts: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._server: Optional[socket.socket] = None
        self._stats_server: Optional[socket.socket] = None
        self._stop = False

    def start(self):
        for path in [self.sock_path, self.sock_path.replace(".sock", "_stats.sock")]:
            if isinstance(path, str) and os.path.exists(path):
                os.unlink(path)

        if self.sock_path.startswith("tcp:"):
            # TCP mode: tcp:host:port
            parts = self.sock_path.split(":", 2)
            host, port = parts[1], int(parts[2])
            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server.bind((host, port))
        else:
            # Unix socket mode
            if os.path.exists(self.sock_path):
                os.unlink(self.sock_path)
            self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server.bind(self.sock_path)

        self._server.listen(64)
        self._server.settimeout(1.0)
        threading.Thread(target=self._accept_loop, daemon=True).start()

        # Stats socket (always Unix)
        stats_path = self._stats_path()
        if os.path.exists(stats_path):
            os.unlink(stats_path)
        self._stats_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._stats_server.bind(stats_path)
        self._stats_server.listen(4)
        self._stats_server.settimeout(1.0)
        threading.Thread(target=self._stats_loop, daemon=True).start()

    def _stats_path(self):
        if self.sock_path.startswith("tcp:"):
            return "/tmp/deadline_proxy_stats.sock"
        return self.sock_path.replace(".sock", "_stats.sock")

    def stop(self):
        self._stop = True
        if self._server:
            self._server.close()
        if self._stats_server:
            self._stats_server.close()

    def _stats_loop(self):
        while not self._stop:
            try:
                client, _ = self._stats_server.accept()
            except (socket.timeout, OSError):
                continue
            with self._lock:
                stats = {
                    "connection_count": self.connection_count,
                    "bytes_relayed": self.bytes_relayed,
                    "hosts": dict(self.hosts),
                }
            client.sendall(json.dumps(stats).encode())
            client.close()

    def _accept_loop(self):
        while not self._stop:
            try:
                client, _ = self._server.accept()
            except (socket.timeout, OSError):
                continue
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _handle(self, client):
        remote_ssl = None
        client_ssl = None
        target = "?"
        try:
            data = client.recv(4096)
            if not data:
                return
            line = data.split(b"\r\n")[0].decode()
            parts = line.split()
            if len(parts) < 2 or parts[0] != "CONNECT":
                client.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return

            target = parts[1]
            host, port_str = target.rsplit(":", 1)
            port = int(port_str)

            # Connect to real server with TLS
            raw_remote = socket.create_connection((host, port), timeout=30)
            remote_ctx = ssl.create_default_context()
            remote_ssl = remote_ctx.wrap_socket(raw_remote, server_hostname=host)

            # Tell client the tunnel is established
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

            # Wrap client side with our MITM cert
            cert_path, key_path = self.ca.get_cert_for_host(host)
            client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            client_ctx.load_cert_chain(cert_path, key_path)
            client_ssl = client_ctx.wrap_socket(client, server_side=True)

            with self._lock:
                self.connection_count += 1
                self.hosts[target] = self.hosts.get(target, 0) + 1

            relayed = self._relay(client_ssl, remote_ssl)
            with self._lock:
                self.bytes_relayed += relayed

        except Exception as e:
            import traceback
            print(f"MITM proxy error for {target}: {e}", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
        finally:
            for s in [client_ssl, client, remote_ssl]:
                if s:
                    try:
                        s.close()
                    except Exception:
                        pass

    @staticmethod
    def _relay(a, b) -> int:
        total = 0
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
                    # CRITICAL: Do not remove. Non-blocking SSL sockets raise
                    # SSLWantReadError when the SSL layer needs more wire data
                    # before it can return application data — this is NOT an
                    # error. Previously this was caught by the broad
                    # `except ssl.SSLError` below (SSLWantReadError is a
                    # subclass), which killed the relay with 0 bytes transferred.
                    # The symptom was baffling: the proxy logged successful TLS
                    # handshakes but clients got "RemoteDisconnected". It only
                    # affected certain endpoints (Deadline, not STS) depending
                    # on TLS negotiation timing.
                    continue
                except (OSError, ConnectionError, ssl.SSLError):
                    return total
                if not data:
                    return total
                dest = b if s is a else a
                try:
                    dest.setblocking(True)
                    dest.sendall(data)
                    dest.setblocking(False)
                    total += len(data)
                except (OSError, ConnectionError, ssl.SSLError):
                    return total
        return total


if __name__ == "__main__":
    sock_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/deadline_proxy.sock"
    ca_cert_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/deadline_proxy_ca.crt"

    os.makedirs(os.path.dirname(ca_cert_path) or ".", exist_ok=True)

    proxy = MitmProxy(sock_path, ca_cert_path)
    proxy.start()
    print(f"MITM proxy listening on {sock_path}", flush=True)
    print(f"CA cert: {ca_cert_path}", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        proxy.stop()
