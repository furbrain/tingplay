import threading
import copy
import urllib2

import tingbot_gui as gui
from layout import MAIN_PANEL
import upnp.search
import upnp.device

class LibraryPanel(gui.Panel):
    def __init__(self):
        super(gui.Panel,self).__init__(MAIN_PANEL.topleft,MAIN_PANEL.size,align="topleft")
        #library selector goes on the top, aligned to top right
        self.entries = gui.ScrollArea((0,30),(320,MAIN_PANEL.height-30),parent=self, align="topleft",canvas_size=(10,10))
        self.library_dropdown = gui.DropDown((320,0),(260,30),align="topright",
                                        parent=self,
                                        values=[(" -- ",None)],
                                        callback=self.library_selected)
        library_label = gui.StaticText((0,0),(60,30),align="topleft",parent=self, label = "Library:",text_align="right")
        thread = threading.Thread(target=self.find_libraries)
        thread.start()
        self.library = None
        
    def browse(self,ObjectID="0"):
        try:
            results = self.library.ContentDirectory.Browse(ObjectID=ObjectID)
        except urllib2.HTTPError:
            if len(self.library.friendlyName)>10:
                name = self.library.friendlyName[:10]+'...'
            else:
                name = self.library.friendlyName
            gui.MessageBox(message=name + " not responding")
            return None
        return results
            
        
    def library_selected(self,name,library):
        self.library=library
        results = self.browse()
        if results:
            self.show_browse_results(results)
        
    def browse_callback(self,container):
        obj_id = container.attrib['id']
        results = self.browse(ObjectID=obj_id)
        if results:
            self.show_browse_results(results)

    def browse_item_callback(self,item):
        print "Play: " + item.find('title').text
        
    def show_browse_results(self,results):
        dir_style = copy.copy(self.style)
        dir_style.button_text_color=(0,255,255)
        results = upnp.device.parseXML(results['Result'])
        containers = results.findall("container")
        items = results.findall("item")
        self.entries.scrolled_area.remove_all()
        self.entries.resize_canvas((300,3+30*(len(containers)+len(items))))
        index = 0
        for c in containers:
            gui.PopupButton((0,30*index), (300,30), align="topleft",
                            parent=self.entries.scrolled_area,
                            style=dir_style,
                            label=c.find('title').text,
                            callback = lambda c=c: self.browse_callback(c))
            index += 1
        for c in items:
            gui.PopupButton((0,30*index), (300,30), align="topleft",
                            parent=self.entries.scrolled_area,
                            label=c.find('title').text,
                            callback = lambda c=c: self.browse_item_callback(c))
            index += 1
        self.entries.update(downwards=True)
        
    def find_libraries(self):
        libs = upnp.search.get_devices('urn:schemas-upnp-org:device:MediaServer:1')
        self.library_dropdown.values = [(d.friendlyName,d) for d in libs]
        self.library_dropdown.selected = ("Select Library",None)
        self.library_dropdown.update()
    
    

