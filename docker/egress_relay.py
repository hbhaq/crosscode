"""Loopback-to-Unix relay inside the evaluator's network=none namespace."""
import select
import socket
import socketserver
import threading
import time

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self.request.settimeout(15)
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as remote:
                remote.settimeout(15)
                remote.connect('/egress/proxy.sock')
                total=0
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    ready,_,_=select.select([self.request,remote],[],[],1)
                    for source in ready:
                        data=source.recv(65536)
                        if not data:
                            return
                        total+=len(data)
                        if total>16*1024*1024:
                            return
                        (remote if source is self.request else self.request).sendall(data)
        except OSError:
            return

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True

def start():
    server=Server(('127.0.0.1',3128),Handler)
    threading.Thread(target=server.serve_forever,name='restricted-egress-relay',daemon=True).start()
    return server
