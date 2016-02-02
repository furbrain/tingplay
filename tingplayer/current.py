import xml.etree.ElementTree as ET

import tingbot_gui as gui
from layout import MAIN_PANEL


class CurrentPanel(gui.Panel):
    def __init__(self):
        super(CurrentPanel,self).__init__(MAIN_PANEL.topleft,MAIN_PANEL.size,align="topleft")
        self.renderer_dropdown = gui.DropDown((MAIN_PANEL.width,0),(MAIN_PANEL.width-60,30),align="topright",
                                              parent=self,
                                              values=[(" -- ",None)],
                                              callback=self.set_renderer)
        library_label = gui.StaticText((0,0),(60,30),align="topleft",parent=self, label = "Player:",text_align="right")
        self.volume_slider = gui.Slider((MAIN_PANEL.width,32),(20,MAIN_PANEL.height-72),align="topright",parent=self)
        self.volume_label = gui.StaticText(self.volume_slider.rect.bottomright,(50,20),align="topright",label="Vol: 23",parent=self)
        self.position_slider = gui.Slider(MAIN_PANEL.size,(MAIN_PANEL.width-50,20),align="bottomright",parent=self)
        self.position_label = gui.StaticText((0,MAIN_PANEL.height),(50,20),align="bottomleft",label="01:34",parent=self)
        track_style = gui.Style(statictext_font_size=24)
        self.title = gui.StaticText((3,32),(MAIN_PANEL.width-22,30),align="topleft",parent=self,
                                    label="Track Title",style=track_style,text_align='left')
        self.album = gui.StaticText((3,64),(MAIN_PANEL.width-102,30),align="topleft",parent=self,
                                     label="Album Title",text_align='left')
        self.artist = gui.StaticText((3,96),(MAIN_PANEL.width-102,30),align="topleft",parent=self,
                                     label="Artist",text_align='left')
        self.renderer = None
        
    def set_renderer(self,name,renderer):
        print "Selecting renderer: " + name
        self.renderer = renderer
        
    def play(self,track = None):
        if track is not None:
            self.track = track
            self.title.label = track.find('title').text
            self.artist.label = track.find('artist').text
            self.album.label = track.find('album').text
            if self.renderer:
                InstanceID = 0
                if hasattr(self.renderer.ConnectionManager,'PrepareForConnection'):
                    print "prepare for connection exists. Damn"
                meta_data = ET.tostring(self.track.find('res'),encoding='utf-8')
                track_url = self.track.find('res').text
                self.renderer.AVTransport.SetAVTransportURI(InstanceID=InstanceID,
                                                            CurrentURI=track_url,
                                                            CurrentURIMetaData=meta_data)
                self.renderer.AVTransport.Play(InstanceID=InstanceID)
            
    def add_renderer(self,renderer):
        if self.renderer_dropdown.values == [(" -- ",None)]:
            self.renderer_dropdown.values[:] = []
            self.renderer_dropdown.selected = ("Select Player",None)
        self.renderer_dropdown.values.append((renderer.friendlyName,renderer))
        self.renderer_dropdown.update()
                    
        
