from twisted.internet import defer
import pygame.transform

import tingbot_gui as gui
from tingbot import Image

from layout import MAIN_PANEL
import utils

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
    
def get_url_metadata(track):
    resources = track['resources']
    for prefix in ['http','ftp','rtsp','']:
        for x,y in resources.items():
            if x.startswith(prefix):
                return x, y
    
class AlbumButton(gui.Button):
    def __init__(self, xy, size, align="center", parent=None, art_url = None):
        super(AlbumButton, self).__init__(xy, size, align, parent)
        self.set_art(art_url)
        
    def set_art(self,art_url):
        if art_url:
            self.art  = Image.load_url(art_url)
            self.thumb = Image(pygame.transform.scale(self.art.surface,self.size))
        else:
            self.art = None
        
    def draw(self):
        if self.art:
            self.image(self.thumb)
        else:
            self.fill(self.style.bg_color)
            
    def on_click(self):
        if self.art:
            AlbumArtViewer(self.art).run()

class AlbumArtViewer(gui.Dialog):
    def __init__(self,art):
        super(AlbumArtViewer,self).__init__((160,120),art.size)
        self.art = art
        self.image(art)
        
    def draw(self):
        self.image(self.art)            
        
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
                                        parent=self,callback=self.volume_cb, release_callback = self.final_volume_cb)
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
        self.album_art = AlbumButton(self.volume_slider.rect.topleft,(80,80),align="topright",parent=self,art_url=None  )
        self.renderer = None
        self.last_action_time = 0
        self.playlist = None
        self.transport_state = None
        self.play_timer = None
                
    def set_renderer(self,name,renderer):
        print "Selecting renderer: " + name
        if renderer==self.renderer: return
        self.stop_timer()
        if renderer is None: return
        if self.renderer:
            #unsubscribe previous subs
            utils.disconnect_variable(self.renderer.av_transport, 'RelativeTimePosition', self.set_track_pos)
            utils.disconnect_variable(self.renderer.av_transport, 'CurrentTrackDuration', self.set_duration)
            utils.disconnect_variable(self.renderer.av_transport, 'TransportState', self.transport_state_changed)
            utils.disconnect_variable(self.renderer.rendering_control, 'Volume', self.set_volume)

        self.renderer = renderer
        utils.connect_variable(self.renderer.av_transport, 'RelativeTimePosition', self.set_track_pos)
        utils.connect_variable(self.renderer.av_transport, 'CurrentTrackDuration', self.set_duration)
        utils.connect_variable(self.renderer.av_transport, 'TransportState', self.transport_state_changed)
        utils.connect_variable(self.renderer.rendering_control, 'Volume', self.set_volume)
        volume_variable = self.renderer.rendering_control.service.get_state_variable('Volume')
        self.volume_slider.max_val = int(volume_variable.allowed_value_range['maximum'])
        self.volume_slider.update()
        
    def set_playlist(self,playlist):
        self.playlist = playlist
        self.prev_button.callback = self.playlist.previous_track
        self.next_button.callback = self.playlist.next_track
        
    def set_volume(self,variable):
        value = variable.value
        self.volume_slider.value = int(value)
        self.volume_label.label = "Vol: %s" % value
        self.volume_slider.update()
        self.volume_label.update()
    
    def set_duration(self,variable):
        value = variable.value
        secs = hms_to_seconds(value)
        if secs:
            self.position_slider.max_val = secs
            self.duration_label.label = seconds_to_ms(secs)
            self.duration_label.update()

    def set_track_pos(self,variable):
        value = variable.value
        try:
            secs = hms_to_seconds(value)
        except ValueError:
            return
        self.position_slider.value = secs
        self.position_slider.update()
        self.position_label.label = seconds_to_ms(secs)
        self.position_label.update()
        
    def volume_cb(self,value):
        self.volume_label.label = "Vol: %d" % int(value)
        self.volume_label.update()
            
    def final_volume_cb(self,value):
        self.renderer.rendering_control.set_volume(desired_volume=int(value))
        
    def start_position_timer(self):
        if not self.play_timer:
            self.play_timer = self.create_timer(self.renderer.av_transport.get_position_info,1)
    
    def stop_timer(self):
        if self.play_timer:
            self.play_timer.stop()
            self.play_timer = None

    @defer.inlineCallbacks
    def play(self,track = None):
        if track is not None:
            self.track = track
            self.title.label = track['title']
            self.artist.label = track['artist']
            self.album.label = track['album']
            if 'albumArtURI' in track is not None:
                self.album_art.set_art(track['albumArtURI'])
            else:
                self.album_art.set_art(None)
            if self.renderer:
                InstanceID = 0
                if self.renderer.connection_manager.service.get_action('PrepareForConnection'):
                    print "prepare for connection exists. Damn"
                track_url, meta_data = (get_url_metadata(track))
                try:
                    if self.transport_state=="PLAYING":
                        yield self.renderer.av_transport.stop()
                    yield self.renderer.av_transport.set_av_transport_uri(
                                        instance_id=InstanceID,
                                        current_uri=track_url,
                                        current_uri_metadata=meta_data)
                    yield self.renderer.av_transport.play(instance_id=InstanceID)
                except Exception as err:
                    gui.message_box(message=err)
                self.start_position_timer()
            self.update(downwards=True)
    
    def stop(self):
        self.stop_timer()
        if self.transport_state=="PLAYING":
            self.renderer.av_transport.stop()
        
           
    def add_renderer(self,client, udn):
        if self.renderer_dropdown.values == [(" -- ",None)]:
            self.renderer_dropdown.values[:] = []
            self.renderer_dropdown.selected = ("Select Player",None)
        self.renderer_dropdown.values.append((client.device.friendly_name,client))
        self.renderer_dropdown.update()
                    
    def transport_state_changed(self, variable):
        self.transport_state = variable.value
        if variable.value=="STOPPED":
            rt = self.renderer.av_transport.service.get_state_variable('RelativeTimePosition')
            td = self.renderer.av_transport.service.get_state_variable('CurrentTrackDuration')
            if rt and td and rt.value and td.value:
                rt = hms_to_seconds(rt.value)
                td = hms_to_seconds(td.value)
                if abs(td-rt)<3:
                    print "next track"
                    self.playlist.next_track()                   
        
