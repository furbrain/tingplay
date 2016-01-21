import tingbot_gui as gui
from functools import partial
from layout import MAIN_PANEL

class PlaylistPanel(gui.ScrollArea):
    def __init__(self):
        super(PlaylistPanel,self).__init__(MAIN_PANEL.topleft,MAIN_PANEL.size,align="topleft",canvas_size=(10,10))
        self.playlist = [] # a list of upnp items
        self.current_track = 0
        
    def play_tracks(self,tracks):
        self.current_track = 0
        self.playlist[:] = tracks
        self.click_track(0)
        self.refresh_list()
        
    def click_track(self,index):
        self.current_track = index
        print "Playing " + self.playlist[index].find('title').text
        self.refresh_list()
        
    def enqueue_tracks(self,tracks):
        self.playlist.extend(tracks)
        self.refresh_list()
        
    def refresh_list(self):
        height = 30*len(self.playlist)
        self.scrolled_area.remove_all()
        self.resize_canvas((300,height))
        current_playing_style = self.style.copy()
        current_playing_style.popup_bg_color = self.style.button_pressed_color
        for i,track in enumerate(self.playlist):
            but = gui.PopupButton((0,30*i), (300,30), align="topleft",
                                    parent=self.scrolled_area,
                                    style=self.style,
                                    label=track.find('title').text,
                                    callback = partial(self.click_track,track))
            if i==self.current_track:
                but.style = current_playing_style
        self.update(downwards=True)
        
