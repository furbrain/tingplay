import xml.etree.ElementTree as ET

import pygame.time

import tingbot_gui as gui
from layout import MAIN_PANEL
import upnp.events
import upnp.device
from tingbot import every, main_run_loop

def hms_to_seconds(value):
    secs = 0
    for val in value.split(':'):
        secs = secs*60 +float(val)
    return secs
    
def seconds_to_hms(value):
    value = int(value)
    return ("%d:%02d:%02d" % (value/3600,) + divmod(value%3600,60))
    
def seconds_to_ms(value):
    """convert seconds to minutes:seconds"""
    value = int(value)
    return ("%d:%02d" % divmod(value,60))
    

class ChangeMonitor(object):
    """This class represents the state of the renderer"""
    
    def __init__(self,renderer,**kwargs):
        """pass a keyword and a callback - the callback will be called if the keyword value changes"""
        self.renderer = renderer
        self._callbacks = {}
        self._callbacks.update(kwargs)
        upnp.events.subscribe(renderer.AVTransport,self.notify)
        upnp.events.subscribe(renderer.RenderingControl,self.notify)
        every(seconds=1)(self.get_play_position)
        
        
    def set_attribute(self,attribute,value):    
        setattr(self,attribute,value)
        if attribute in self._callbacks:
            self._callbacks[attribute](value)
        
    def notify(self,changes):
        changes = upnp.device.parseXML(changes)
        changes = upnp.device.parseXML(changes.find('.//LastChange').text)
        instance = changes.find('InstanceID')
        for elem in instance:
            self.set_attribute(elem.tag,elem.get('val'))
        
    def get_play_position(self):
        pos = self.renderer.AVTransport.GetPositionInfo()
        for key,value in pos.items():
            self.set_attribute(key,value)
        
    def unsubscribe(self):
        upnp.events.unsubscribe(self.notify)
        main_run_loop.remove_timer(self.get_play_position)
        
class CurrentPanel(gui.Panel):
    def __init__(self):
        right,bottom = MAIN_PANEL.size
        super(CurrentPanel,self).__init__(MAIN_PANEL.topleft,MAIN_PANEL.size,align="topleft")
        self.renderer_dropdown = gui.DropDown((MAIN_PANEL.width,0),(MAIN_PANEL.width-60,30),align="topright",
                                              parent=self,
                                              values=[(" -- ",None)],
                                              callback=self.set_renderer)
        
        library_label = gui.StaticText((0,0),(60,30),align="topleft",parent=self, label = "Player:",text_align="right")
        self.volume_slider = gui.Slider((right,32),(20,bottom-72),align="topright",
                                        parent=self,callback=self.volume_cb)
        self.volume_label = gui.StaticText(self.volume_slider.rect.bottomright,(50,20),align="topright",label="Vol: --",parent=self)
        self.position_label = gui.StaticText((0,MAIN_PANEL.height),(50,20),align="bottomleft",label="--:--",parent=self)
        self.position_slider = gui.Slider(self.position_label.rect.topright,(right-100,20),align="topleft",parent=self)
        self.duration_label = gui.StaticText((MAIN_PANEL.width,MAIN_PANEL.height),(50,20),align="bottomright",label="--:--",parent=self)
        self.play_button = gui.Button((right/2,self.position_label.rect.top),(50,30),align="bottom",
                                      label="image:images/play.png",parent=self)
        self.prev_button = gui.Button(self.play_button.rect.bottomleft,(50,30),align="bottomright",
                                      label="image:images/start.png",parent=self)
                                      
        self.next_button = gui.Button(self.play_button.rect.bottomright,(50,30),align="bottomleft",
                                      label="image:images/end.png",parent=self)
        track_style = gui.Style(statictext_font_size=24)
        self.title = gui.StaticText((3,32),(MAIN_PANEL.width-22,30),align="topleft",parent=self,
                                    label="Track Title",style=track_style,text_align='left')
        self.album = gui.StaticText((3,64),(MAIN_PANEL.width-102,30),align="topleft",parent=self,
                                     label="Album Title",text_align='left')
        self.artist = gui.StaticText((3,96),(MAIN_PANEL.width-102,30),align="topleft",parent=self,
                                     label="Artist",text_align='left')
        self.renderer = None
        self.change_monitor = None
        self.last_action_time = 0
        self.playlist = None
        
    def set_renderer(self,name,renderer):
        print "Selecting renderer: " + name
        self.renderer = renderer
        if self.change_monitor:
            self.change_monitor.unsubscribe()
        self.volume_slider.max_val = int(self.renderer.RenderingControl.vars['Volume']['range']['maximum'])
        self.change_monitor = ChangeMonitor(self.renderer,
                                            Volume=self.set_volume,
                                            TrackDuration=self.set_duration,
                                            RelTime=self.set_track_pos,
                                            TransportState=self.transport_state_changed)
        self.volume_slider.update()
        
    def set_playlist(self,playlist):
        self.playlist = playlist
        self.prev_button.callback = self.playlist.previous_track
        self.next_button.callback = self.playlist.next_track
        
    def set_volume(self,value):
        print "volume response: " + value    
        self.volume_slider.value = int(value)
        self.volume_label.label = "Vol: %s" % value
        self.volume_slider.update()
        self.volume_label.update()
    
    def set_duration(self,value):
        secs = hms_to_seconds(value)
        if secs:
            self.position_slider.max_val = secs
            self.duration_label.label = seconds_to_ms(secs)
            self.duration_label.update()

    def set_track_pos(self,value):        
        secs = hms_to_seconds(value)
        self.position_slider.value = secs
        self.position_slider.update()
        self.position_label.label = seconds_to_ms(secs)
        self.position_label.update()
        
    def volume_cb(self,value):
        tm = pygame.time.get_ticks()
        if tm>self.last_action_time+200:
            self.last_action_time = tm
            print "changing volume: ",value
            self.volume_label.label = "Vol: %s" % value
            self.renderer.RenderingControl.SetVolume(DesiredVolume=int(value))
        
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
            self.update(downwards=True)
            
    def add_renderer(self,renderer):
        if self.renderer_dropdown.values == [(" -- ",None)]:
            self.renderer_dropdown.values[:] = []
            self.renderer_dropdown.selected = ("Select Player",None)
        self.renderer_dropdown.values.append((renderer.friendlyName,renderer))
        self.renderer_dropdown.update()
                    
    def transport_state_changed(self,value):
        if value=="STOPPED":
            if self.change_monitor:
                rt = hms_to_seconds(self.change_monitor.RelTime)
                td = hms_to_seconds(self.change_monitor.TrackDuration)
                if abs(rt-td)<3:
                    print "next track"
                    self.playlist.next_track()                   
        
