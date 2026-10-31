"""Minimal unauthenticated MQTT CONNECT/CONNACK inspection for one private host."""
from __future__ import annotations
import ipaddress, secrets, socket, ssl, struct
from typing import Any

MAX_TIMEOUT=3.0

def _target(value: str) -> str:
    address=ipaddress.ip_address(str(value).strip())
    if not isinstance(address,ipaddress.IPv4Address) or not address.is_private or address.is_loopback or address.is_link_local or address.is_multicast:
        raise ValueError("MQTT probe aceita somente IPv4 privado RFC1918, exceto loopback/link-local.")
    if address not in tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8","172.16.0.0/12","192.168.0.0/16")):
        raise ValueError("Destino fora do escopo RFC1918.")
    return str(address)

def _encode_remaining(length: int) -> bytes:
    out=bytearray()
    while True:
        digit=length%128; length//=128
        if length: digit|=0x80
        out.append(digit)
        if not length: return bytes(out)

def _read_packet(sock: socket.socket, timeout: float) -> tuple[int,bytes]:
    sock.settimeout(timeout)
    first=sock.recv(1)
    if len(first)!=1: raise ConnectionError("Broker encerrou antes do CONNACK.")
    multiplier=1; remaining=0
    for _ in range(4):
        raw=sock.recv(1)
        if len(raw)!=1: raise ConnectionError("Remaining Length MQTT truncado.")
        digit=raw[0]; remaining+=(digit&127)*multiplier
        if not digit&128: break
        multiplier*=128
    else: raise ValueError("Remaining Length MQTT inválido.")
    if remaining>4096: raise ValueError("Resposta MQTT excede 4096 bytes.")
    body=bytearray()
    while len(body)<remaining:
        chunk=sock.recv(remaining-len(body))
        if not chunk: raise ConnectionError("Pacote MQTT truncado.")
        body.extend(chunk)
    return first[0],bytes(body)

def probe_mqtt(host: str, *, port: int=1883, timeout: float=1.0, use_tls: bool|None=None) -> dict[str,Any]:
    """Open one temporary clean-session MQTT 3.1.1 connection; never auth/publish/subscribe."""
    address=_target(host)
    if isinstance(port,bool) or not isinstance(port,int) or port not in (1883,8883): raise ValueError("Porta MQTT deve ser 1883 ou 8883.")
    bounded=max(0.2,min(float(timeout),MAX_TIMEOUT)); tls=(port==8883) if use_tls is None else bool(use_tls)
    client_id="jv-probe-"+secrets.token_hex(6)
    cid=client_id.encode("ascii")
    variable=struct.pack("!H",4)+b"MQTT"+bytes((4,2))+struct.pack("!H",10)
    payload=struct.pack("!H",len(cid))+cid
    packet=bytes((0x10,))+_encode_remaining(len(variable)+len(payload))+variable+payload
    raw=None
    try:
        raw=socket.create_connection((address,port),timeout=bounded)
        conn=ssl.create_default_context().wrap_socket(raw,server_hostname=address) if tls else raw
        conn.settimeout(bounded); conn.sendall(packet)
        header,body=_read_packet(conn,bounded)
        if header>>4!=2 or len(body)!=2: return {"success":False,"confirmed":False,"protocol":"mqtt","error":"invalid_connack"}
        session_present=bool(body[0]&1); code=body[1]
        if code==0: conn.sendall(b"\xe0\x00")
        return {"success":code==0,"confirmed":True,"protocol":"mqtt","mqtt_version":"3.1.1","tls":tls,"connack_code":code,"session_present":session_present,"authenticated":False,"published":False,"subscribed":False,"client_id":client_id}
    except (OSError,ssl.SSLError,TimeoutError,ConnectionError,ValueError) as exc:
        return {"success":False,"confirmed":False,"protocol":"mqtt","tls":tls,"error":type(exc).__name__}
    finally:
        if raw is not None:
            try:
                # MQTT DISCONNECT only if broker connection still open; closing is also safe.
                raw.close()
            except OSError: pass
