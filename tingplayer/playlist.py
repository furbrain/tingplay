import tingbot_gui as gui
from functools import partial
from layout import MAIN_PANEL

class PlaylistPanel(gui.ScrollArea):
    def __init__(self,current_panel):
        super(PlaylistPanel,self).__init__(MAIN_PANEL.topleft,MAIN_PANEL.size,align="topleft",canvas_size=(10,10))
        self.current_panel = current_panel
        self.playlist = [] # a list of upnp items
        self.current_track = 0
        self.current_panel.set_playlist(self)
        
    def play_tracks(self,tracks):
        self.current_track = 0
        self.playlist[:] = tracks
        self.click_track(0)
        self.refresh_list()
        
    def click_track(self,index):
        self.current_track = index
        print "Playing " + self.playlist[index].find('title').text
        self.current_panel.play(self.playlist[index])
        self.refresh_list()
        
    def delete_track(self,index):
        if self.current_track==index:
            self.current_panel.stop()
        del self.playlist[index]
        self.refresh_list()
        
    def delete_all_tracks(self):
        self.current_panel.stop()
        self.playlist[:] = []
        self.refresh_list()
    
    def long_click_track(self,track):
        gui.PopupMenu(xy = (100,60), menu_items = [
            ("Delete",lambda: self.delete_track(track)),
            ("Delete All",self.delete_all_tracks)])
        
    def enqueue_tracks(self,tracks):
        self.playlist.extend(tracks)
        self.refresh_list()
        
    def refresh_list(self):
        height = 30*len(self.playlist)
        self.scrolled_area.remove_all()
        self.resize_canvas((300,height or 1))
        current_playing_style = self.style.copy()
        current_playing_style.popup_bg_color = self.style.button_pressed_color
        for i,track in enumerate(self.playlist):
            but = gui.PopupButton((0,30*i), (300,30), align="topleft",
                                    parent=self.scrolled_area,
                                    style=self.style,
                                    label=track.find('title').text,
                                    callback = partial(self.click_track,i),
                                    long_click_callback = partial(self.long_click_track,i))
            if i==self.current_track:
                but.style = current_playing_style
        self.update(downwards=True)
        
    def next_track(self):
        self.current_track += 1
        if self.current_track>=len(self.playlist):
            self.current_track = 0
        else:
            self.click_track(self.current_track)
    
    def previous_track(self):
        self.current_track -= 1
        if self.current_track<0:
            self.current_track = 0
        else:
            self.click_track(self.current_track)
    
