import threading
import urllib2
from functools import partial

import tingbot_gui as gui
from layout import MAIN_PANEL
import upnp.search
import upnp.device

class LibraryPanel(gui.Panel):
    def __init__(self,playlist_panel):
        super(LibraryPanel,self).__init__(MAIN_PANEL.topleft,MAIN_PANEL.size,align="topleft")
        #library selector goes on the top, aligned to top right
        self.entries = gui.ScrollArea((0,30),(320,MAIN_PANEL.height-30),parent=self, align="topleft",canvas_size=(10,10))
        self.library_dropdown = gui.DropDown((320,0),(260,30),align="topright",
                                        parent=self,
                                        values=[(" -- ",None)],
                                        callback=self.library_selected)
        library_label = gui.StaticText((0,0),(60,30),align="topleft",parent=self, label = "Library:",text_align="right")
        self.library = None
        self.playlist_panel=playlist_panel
        
    def browse(self,**kwargs):
        try:
            results = self.library.ContentDirectory.Browse(**kwargs)
        except urllib2.HTTPError:
            if len(self.library.friendlyName)>10:
                name = self.library.friendlyName[:10]+'...'
            else:
                name = self.library.friendlyName
            gui.MessageBox(message=name + " not responding")
            return None
        return results
            
        
    def library_selected(self,name,library):
        if library:
            self.library=library
            self.browse_list = ["0"]
            results = self.browse()
            if results:
                self.show_browse_results(results)
                
    def click_parent(self):
        self.browse_list.pop()
        results = self.browse(ObjectID=self.browse_list[-1])
        if results:
            self.show_browse_results(results)
        
    def click_container(self,container):
        obj_id = container.attrib['id']
        self.browse_list.append(obj_id)
        results = self.browse(ObjectID=obj_id)
        if results:
            self.show_browse_results(results)

    def click_item(self,item):
        gui.PopupMenu(xy = (100,60), menu_items = [
            ("Play",lambda: self.playlist_panel.play_tracks([item])),
            ("Enqueue",lambda: self.playlist_panel.enqueue_tracks([item]))])
        
    def get_container_tracks(self,container):
        results = self.browse(ObjectID=container.attrib['id'])
        results = upnp.device.parseXML(results['Result'])
        items = results.findall("item")
        return items
        
    def long_click_container(self,container):
        tracks = self.get_container_tracks(container)
        gui.PopupMenu(xy = (100,60), menu_items = [
            ("Play All",lambda: self.playlist_panel.play_tracks(tracks)),
            ("Enqueue All",lambda: self.playlist_panel.enqueue_tracks(tracks))])
        
    def show_browse_results(self,results):
        dir_style = self.style.copy()
        dir_style.button_text_color=(0,255,255)
        results = upnp.device.parseXML(results['Result'])
        containers = results.findall("container")
        items = results.findall("item")
        self.entries.scrolled_area.remove_all()
        item_count = len(containers)+len(items)
        if len(self.browse_list)>1:
            item_count += 1
        self.entries.resize_canvas((300,3+30*item_count))
        index = 0
        if len(self.browse_list)>1:
            gui.PopupButton((0,30*index), (300,30), align="topleft",
                            parent=self.entries.scrolled_area,
                            style=dir_style,
                            label=u'\u00ab--',
                            callback = self.click_parent)    
            index += 1        
        for c in containers:
            gui.PopupButton((0,30*index), (300,30), align="topleft",
                            parent=self.entries.scrolled_area,
                            style=dir_style,
                            label=c.find('title').text,
                            callback = partial(self.click_container,c),
                            long_click_callback = partial(self.long_click_container,c))
            index += 1
        for c in items:
            gui.PopupButton((0,30*index), (300,30), align="topleft",
                            parent=self.entries.scrolled_area,
                            label=c.find('title').text,
                            callback = partial(self.click_item,c))
            index += 1
        self.entries.update(downwards=True)
        
    def add_library(self,library):
        if self.library_dropdown.values == [(" -- ",None)]:
            self.library_dropdown.values[:] = []
            self.library_dropdown.selected = ("Select Library",None)
        self.library_dropdown.values.append((library.friendlyName,library))
        self.library_dropdown.update()
    
    

