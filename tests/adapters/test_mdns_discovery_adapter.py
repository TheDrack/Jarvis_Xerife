import struct
from app.adapters.edge.mdns_discovery_adapter import parse_mdns_response, _read_name

def _name(value): return b"".join(bytes([len(x)])+x.encode() for x in value.split("."))+b"\0"

def test_parse_mdns_ptr_response():
    qname=_name("_services._dns-sd._udp.local")
    target=_name("_http._tcp.local")
    question=qname+struct.pack("!HH",12,1)
    answer=b"\xc0\x0c"+struct.pack("!HHIH",12,1,120,len(target))+target
    packet=struct.pack("!HHHHHH",0,0x8400,1,1,0,0)+question+answer
    records=parse_mdns_response(packet,"192.168.1.20")
    assert len(records)==1 and records[0]["instance"]=="_http._tcp.local"

def test_reject_dns_compression_pointer_out_of_bounds():
    packet=struct.pack("!HHHHHH",0,0x8400,0,1,0,0)+b"\xc0\xff"+struct.pack("!HHIH",12,1,1,1)+b"x"
    assert parse_mdns_response(packet,"192.168.1.20")==[]

def test_reject_truncated_dns_packet():
    assert parse_mdns_response(b"\0"*10,"192.168.1.20")==[]
