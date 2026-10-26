"""Trusted, bounded HTTPS CONNECT proxy over a private Unix-domain socket.

No TCP listening socket. Only the approved public endpoint and TLS SNI are
accepted. TLS remains end-to-end; no credentials, CA keys or host mounts.
"""
import ipaddress
import os
import select
import socket
import socketserver
import threading
import time

HOST = 'en.wikibooks.org'
MAX_BYTES = 16*1024*1024


def permitted_authority(authority):
    return authority.lower() == HOST+':443'


def public_address(value):
    address = ipaddress.ip_address(value.split('%')[0])
    return address.is_global and not (address.is_multicast or address.is_reserved or address.is_loopback or address.is_link_local)


def receive_exact(connection, count):
    chunks = bytearray()
    while len(chunks)<count:
        part = connection.recv(count-len(chunks))
        if not part:
            raise ValueError('Incomplete TLS hello')
        chunks.extend(part)
    return bytes(chunks)


def tls_server_name(record):
    if len(record)<9 or record[0]!=22:
        raise ValueError('TLS handshake required')
    length = int.from_bytes(record[3:5],'big')
    if length>16384 or len(record)!=length+5 or record[5]!=1:
        raise ValueError('Invalid TLS ClientHello')
    body = record[9:9+int.from_bytes(record[6:9],'big')]
    if len(body)<35:
        raise ValueError('Incomplete ClientHello')
    offset = 34
    def take(count):
        nonlocal offset
        if offset+count>len(body):
            raise ValueError('Invalid ClientHello lengths')
        value=body[offset:offset+count]
        offset+=count
        return value
    take(take(1)[0])
    take(int.from_bytes(take(2),'big'))
    take(take(1)[0])
    extensions = take(int.from_bytes(take(2),'big'))
    position = 0
    while position+4<=len(extensions):
        kind=int.from_bytes(extensions[position:position+2],'big')
        size=int.from_bytes(extensions[position+2:position+4],'big')
        value=extensions[position+4:position+4+size]
        if len(value)!=size:
            raise ValueError('Invalid extension length')
        position+=4+size
        if kind==0:
            if len(value)<5 or value[2]!=0:
                raise ValueError('SNI host required')
            host_length=int.from_bytes(value[3:5],'big')
            host=value[5:5+host_length]
            if len(host)!=host_length:
                raise ValueError('Incomplete SNI')
            return host.decode('ascii').lower()
    raise ValueError('TLS SNI required')


def relay(left,right,limit=MAX_BYTES,seconds=60):
    transferred=0
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        ready,_,_=select.select([left,right],[],[],min(1,max(0,deadline-time.monotonic())))
        for source in ready:
            data=source.recv(65536)
            if not data:
                return
            transferred+=len(data)
            if transferred>limit:
                return
            (right if source is left else left).sendall(data)


def upstream_connection():
    deadline=time.monotonic()+15
    addresses=socket.getaddrinfo(HOST,443,type=socket.SOCK_STREAM)
    addresses.sort(key=lambda item:item[0]!=socket.AF_INET)
    for family,kind,protocol,_,address in addresses:
        if not public_address(address[0]):
            continue
        connection=socket.socket(family,kind,protocol)
        try:
            connection.settimeout(max(.1,min(5,deadline-time.monotonic())))
            connection.connect(address)
            return connection
        except OSError:
            connection.close()
            if time.monotonic()>=deadline:
                break
    raise OSError('Approved public endpoint unavailable')


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        client=self.request
        client.settimeout(15)
        try:
            header=bytearray()
            while not header.endswith(b'\r\n\r\n') and len(header)<8192:
                byte=client.recv(1)
                if not byte:
                    return
                header.extend(byte)
            line=bytes(header).split(b'\r\n',1)[0].decode('ascii').split()
            if not header.endswith(b'\r\n\r\n') or len(line)!=3 or line[0]!='CONNECT' or not permitted_authority(line[1]):
                client.sendall(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                return
            client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            head=receive_exact(client,5)
            size=int.from_bytes(head[3:5],'big')
            if size>16384:
                return
            hello=head+receive_exact(client,size)
            if tls_server_name(hello)!=HOST:
                return
            with upstream_connection() as remote:
                remote.sendall(hello)
                relay(client,remote)
        except (OSError,ValueError,UnicodeError):
            return  # No request bodies, headers or secrets are logged.


class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(16)
        super().__init__(*args,**kwargs)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request,address)
        except Exception:
            self.slots.release()
            raise
    def process_request_thread(self,request,address):
        try:
            super().process_request_thread(request,address)
        finally:
            self.slots.release()


if __name__=='__main__':
    path='/egress/proxy.sock'
    with Server(path,Handler) as server:
        os.chmod(path,0o600)
        print('Restricted Wikibooks HTTPS proxy ready',flush=True)
        server.serve_forever()
