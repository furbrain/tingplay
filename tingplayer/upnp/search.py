#!/usr/bin/python
import SocketServer
import socket
import time
import struct
import threading
import device

found_devices = {}

class SSDPHandler(SocketServer.BaseRequestHandler):
    """Listens for SSDP responses/notifications, and keeps the devices dict up to date"""
    def handle(self):
        data = self.request[0]
        lines = [x.split(':') for x in data.splitlines()[1:-1]]
        fields = dict((x[0].upper().strip(),':'.join(x[1:]).strip()) for x in lines)
        usn_bits  = fields['USN'].split(':')
        if usn_bits[0]=='uuid':
            uuid = usn_bits[1]
            if uuid not in found_devices:
                found_devices[uuid] = {}
                found_devices[uuid]['services'] = []
            if len(usn_bits)>=6:
                if usn_bits[5]=='device':
                    found_devices[uuid]['device'] = usn_bits[6]
                    found_devices[uuid]['url'] = fields['LOCATION']
                if usn_bits[5]=='service':
                    found_devices[uuid]['services'] += [usn_bits[6]]
                    
class ThreadedUDPServer(SocketServer.ThreadingMixIn, SocketServer.UDPServer):
    pass
        
def init_server(port):
    server = ThreadedUDPServer(("192.168.1.28",port),SSDPHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.dameon = True
    thread.start()
    return server
        
def search(target="ssdp:all"):
    data = """\
M-SEARCH * HTTP/1.1\r
HOST: 239.255.255.250:1900\r
MAN: "ssdp:discover"\r
MX: 3\r
ST: %s\r
\r
""" % target
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack('@i',2))
    sock.sendto(data + "\n", ("239.255.255.250", 1900))
    port = sock.getsockname()[1]
    sock.settimeout(1.0)
    result = ""
    for _ in range(0):
        try:
            while True:
               data = sock.recv(4096) 
               result += data
        except socket.timeout:
            pass
        
    sock.close()
    return port

def get_devices(target="ssdp:all"):
    port = search(target)
    port = search()
    thread = init_server(port)
    time.sleep(5)
    thread.shutdown()
    thread.server_close()
    d = [device.Device(x['url']) for x in found_devices.values() if 'url' in x]
    return d

if __name__=="__main__":
    #port = search("upnp:rootdevice")
    d = get_devices()
    for dev in d:
        print dev.friendlyName
