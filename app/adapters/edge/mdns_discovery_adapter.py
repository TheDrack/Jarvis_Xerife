"""Bounded mDNS DNS-SD service discovery on the local IPv4 link."""
from __future__ import annotations
import ipaddress, socket, struct, time
from typing import Any
_GROUP="224.0.0.251"; _PORT=5353; _MAX_PACKET=9000

def _read_name(packet: bytes, offset: int, *, depth: int=0) -> tuple[str,int]:
    if depth>16 or offset>=len(packet): raise ValueError("DNS name pointer inválido.")
    labels=[]; cursor=offset; consumed=None; steps=0
    while True:
        if cursor>=len(packet) or steps>128: raise ValueError("DNS name truncado.")
        length=packet[cursor]; steps+=1
        if length==0:
            cursor+=1
            if consumed is None: consumed=cursor
            break
        if length&0xC0==0xC0:
            if cursor+1>=len(packet): raise ValueError("DNS compression pointer truncado.")
            pointer=((length&0x3F)<<8)|packet[cursor+1]
            if pointer>=len(packet) or pointer>=cursor: raise ValueError("DNS compression pointer fora do limite.")
            suffix,_=_read_name(packet,pointer,depth=depth+1)
            labels.extend(suffix.split(".") if suffix else [])
            cursor+=2
            if consumed is None: consumed=cursor
            break
        if length&0xC0 or length>63 or cursor+1+length>len(packet): raise ValueError("DNS label inválido.")
        raw=packet[cursor+1:cursor+1+length]
        labels.append(raw.decode("ascii",errors="replace"))
        cursor+=1+length
    name=".".join(labels).rstrip(".").lower()
    if len(name)>255: raise ValueError("DNS name excede 255 bytes.")
    return name, consumed if consumed is not None else cursor

def parse_mdns_response(packet: bytes, source_ip: str) -> list[dict[str,Any]]:
    if len(packet)<12 or len(packet)>_MAX_PACKET: return []
    ident,flags,qd,an,ns,ar=struct.unpack_from("!HHHHHH",packet)
    if ident!=0 or not flags&0x8000 or an+ns+ar>256 or qd>32: return []
    offset=12
    try:
        for _ in range(qd):
            _,offset=_read_name(packet,offset)
            if offset+4>len(packet): return []
            offset+=4
        records=[]
        for _ in range(an+ns+ar):
            name,offset=_read_name(packet,offset)
            if offset+10>len(packet): return []
            rtype,rclass,ttl,rdlen=struct.unpack_from("!HHIH",packet,offset); offset+=10
            end=offset+rdlen
            if end>len(packet): return []
            if rtype==12 and rdlen:
                target,_=_read_name(packet,offset)
                if name=="_services._dns-sd._udp.local" or name.endswith("._tcp.local") or name.endswith("._udp.local"):
                    records.append({"protocol":"mdns","source_ip":source_ip,"record_type":"PTR","service":name,"instance":target,"ttl":ttl})
            offset=end
        return records
    except (ValueError,struct.error):
        return []

def discover_mdns(*, timeout: float=2.0, service: str="_services._dns-sd._udp.local") -> dict[str,Any]:
    """Send one PTR query and collect bounded DNS-SD responses; never resolves/fetches endpoints."""
    parsed=ipaddress.ip_address("224.0.0.251")
    if not isinstance(parsed,ipaddress.IPv4Address): raise ValueError("Multicast IPv4 inválido.")
    bounded=max(0.2,min(float(timeout),5.0))
    labels=service.rstrip(".").split(".")
    if not service.endswith(".local") or any(not x or len(x)>63 for x in labels): raise ValueError("Nome de serviço mDNS inválido.")
    qname=b"".join(bytes((len(x.encode("ascii")),))+x.encode("ascii") for x in labels)+b"\0"
    query=struct.pack("!HHHHHH",0,0,1,0,0,0)+qname+struct.pack("!HH",12,1)
    found={}; sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_TTL,255); sock.bind(("",0)); sock.sendto(query,(_GROUP,_PORT))
        deadline=time.monotonic()+bounded
        while time.monotonic()<deadline:
            sock.settimeout(max(.05,min(.25,deadline-time.monotonic())))
            try: data,peer=sock.recvfrom(_MAX_PACKET)
            except socket.timeout: continue
            except OSError: break
            for record in parse_mdns_response(data,peer[0]): found[(record["service"],record["instance"])]=record
    finally: sock.close()
    return {"success":True,"protocol":"mdns_dns_sd","multicast":f"{_GROUP}:{_PORT}","records":list(found.values()),"count":len(found),"active_probes_sent":1,"note":"Somente PTR; nenhum endpoint anunciado foi acessado."}
