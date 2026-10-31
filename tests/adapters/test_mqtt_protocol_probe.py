import socket, threading
import pytest
from unittest.mock import patch
from app.adapters.edge.mqtt_protocol_probe import probe_mqtt

def _read_exact(sock,n):
    data=b""
    while len(data)<n:
        chunk=sock.recv(n-len(data))
        if not chunk: raise ConnectionError
        data+=chunk
    return data

def test_mqtt_connect_connack_against_local_artificial_broker():
    server=socket.socket(); server.bind(("127.0.0.1",0)); server.listen(1)
    port=server.getsockname()[1]; observed={}
    def broker():
        conn,_=server.accept()
        with conn:
            fixed=_read_exact(conn,1)[0]; rem=_read_exact(conn,1)[0]
            packet=_read_exact(conn,rem); observed.update(fixed=fixed,packet=packet)
            conn.sendall(b"\x20\x02\x00\x00")
    t=threading.Thread(target=broker,daemon=True); t.start()
    real_connect=socket.create_connection
    with patch("app.adapters.edge.mqtt_protocol_probe._target",return_value="127.0.0.1"), patch("app.adapters.edge.mqtt_protocol_probe.socket.create_connection",side_effect=lambda addr,timeout: real_connect(("127.0.0.1",port),timeout=timeout)):
        result=probe_mqtt("192.168.1.20",port=1883,timeout=1)
    t.join(1); server.close()
    assert result["success"] and result["confirmed"] and result["connack_code"]==0
    assert observed["fixed"]==0x10 and observed["packet"].startswith(b"\x00\x04MQTT\x04\x02")
    assert result["published"] is False and result["subscribed"] is False

def test_mqtt_probe_rejects_non_private_targets():
    with pytest.raises(ValueError): probe_mqtt("8.8.8.8")

def test_mqtt_probe_rejects_unsupported_port():
    with pytest.raises(ValueError): probe_mqtt("192.168.1.2",port=1884)


def test_mqtt_probe_accepts_rfc1918_address():
    from app.adapters.edge.mqtt_protocol_probe import _target
    assert _target('10.0.0.21') == '10.0.0.21'
