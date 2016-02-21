#!/usr/bin/env python
import urllib2
import urlparse
import SocketServer
import socket
import BaseHTTPServer
import threading

subscriptions = {}

class ThreadedUPnPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    pass


class UPnPHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    
    def do_NOTIFY(self):
        global subscriptions
        sid = self.headers['sid']
        if "content-length" in self.headers:
            data = self.rfile.read(int(self.headers.getheader('Content-Length')))
        else:
            data = self.rfile.read()
        if sid in subscriptions:
            subscriptions[sid][0](data)
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


class SubscribeRequest(urllib2.Request):
    def get_method(self):
        return "SUBSCRIBE"
        
class UnsubscribeRequest(urllib2.Request):
    def get_method(sel):
        return "UNSUBSCRIBE"


def get_ip(target):
    event_ip = urlparse.urlsplit(target).hostname
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((event_ip,80))
    result = s.getsockname()[0]
    s.close()
    return result


def subscribe(service,callback):
    global subscriptions
    """subscribe to unicast eventing for variable on service. callback will be called with the xml response"""
    ip = get_ip(service._eventURL)
    #get url
    req = SubscribeRequest(service._eventURL,'',
                          {'CALLBACK':'<http://'+ip+':8123/>',
                           'NT':'upnp:event',
                           'TIMEOUT':'Second-60'})
    response = urllib2.urlopen(req)
    sid = response.info()['SID']
    subscriptions[sid] = (callback,service)

def unsubscribe(callback):
    global subscriptions
    for sid,cb in subscriptions.items():
        if cb[0]==callback:
            req = UnsubscribeRequest(cb[1]._eventURL,'',
                                     {'SID':sid})
            response = urllib2.urlopen(req)
            del subscriptions[sid]
            
def init_events():
    """initialise http server to receive events"""
    server = ThreadedUPnPServer(('',8123),UPnPHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server
    
if __name__=="__main__":
    from search import get_devices
    import time
    import xml.etree.ElementTree as ET
    import device
    
    def cb(data):
        response = device.parseXML(data)
        changes = device.parseXML(response.find('.//LastChange').text)
        print ET.tostring(changes)
    server = init_events()
    devs = get_devices()
    amp = [x for x in devs if x.friendlyName=="Amplifier"][0]
    subscribe(amp.RenderingControl,cb)
    time.sleep(20)
    server.shutdown()
