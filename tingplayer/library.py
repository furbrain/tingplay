import threading
import urllib2
from functools import partial

from coherence.upnp.core import DIDLLite
from twisted.internet import defer

import tingbot_gui as gui
import tingbot
from layout import MAIN_PANEL
import utils
import time

def sort_items(v):
    if 'container' in v['upnp_class']:
        return (0, v['title'])
    else:
        return (1, v['id'])

class LibraryPanel(gui.Panel):
    def __init__(self, playlist_panel):
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
        self.init_time = time.time()
        
    def process_result(self, result):
        return DIDLLite.DIDLElement.fromString(result['Result'])
     
    @defer.inlineCallbacks    
    def browse(self,**kwargs):
        result = yield self.library.content_directory.browse(process_result=False, **kwargs)
        results = DIDLLite.DIDLElement.fromString(result['Result'])
        defer.returnValue(results)            
        
    def library_selected(self,name,library):
        if library is None: return
        if library == self.library: return
        tingbot.app.settings['last_server'] = name
        self.library=library
        self.browse_list = ["0"]
        self.show_browse_results()
                
    def click_parent(self):
        from_id = self.browse_list.pop()
        self.show_browse_results(self.browse_list[-1], from_id=from_id)
        
    def click_container(self,container):
        obj_id = container.id
        self.browse_list.append(obj_id)
        self.show_browse_results(obj_id)

    def click_item(self,item):
        gui.PopupMenu(xy = (100,60), menu_items = [
            ("Play",lambda: self.playlist_panel.play_tracks([item])),
            ("Enqueue",lambda: self.playlist_panel.enqueue_tracks([item]))])
              
    @defer.inlineCallbacks          
    def long_click_container(self,container):
        tracks = yield self.browse(object_id=container.id)
        tracks = [{'library':self.library,'track':x} for x in tracks.getItems() if isinstance(x,DIDLLite.Item)]
        if tracks:
            gui.PopupMenu(xy = (100,60), menu_items = [
                ("Play All",lambda: self.playlist_panel.play_tracks(tracks)),
                ("Enqueue All",lambda: self.playlist_panel.enqueue_tracks(tracks))])
        else:
            gui.message_box(message="Warning: no tracks found in this directory")        

    @defer.inlineCallbacks    
    def show_browse_results(self, object_id="0", from_id=None):
        results = yield self.browse(object_id=object_id)
        dir_style = self.style.copy()
        dir_style.button_text_color=(0,255,255)
        items = results.getItems()
        self.entries.scrolled_area.remove_all()
        item_count = len(items)
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
        for i in items:
            if i.id==from_id:
                self.entries.viewport.set_y(index*30)
            if 'container' in i.upnp_class:
                gui.PopupButton((0,30*index), (300,30), align="topleft",
                                parent=self.entries.scrolled_area,
                                style=dir_style,
                                label=i.title,
                                callback = partial(self.click_container,i),
                                long_click_callback = partial(self.long_click_container,i))
            else:
                r = {'library':self.library,'track':i}
                gui.PopupButton((0,30*index), (300,30), align="topleft",
                                parent=self.entries.scrolled_area,
                                label=i.title,
                                callback = partial(self.click_item,r))
            index += 1
        self.entries
        self.entries.update(downwards=True)
        
    def add_library(self, client, udn):
        if self.library_dropdown.values == [(" -- ",None)]:
            self.library_dropdown.values[:] = []
            self.library_dropdown.selected = ("Select Library",None)
        self.library_dropdown.values.append((client.device.friendly_name, client))
        if client.device.friendly_name == tingbot.app.settings['last_server']:
            if time.time()-self.init_time < 5:
                self.library_selected(client.device.friendly_name, client)
                self.library_dropdown.selected = (client.device.friendly_name, client)
        self.library_dropdown.update()
    
    

