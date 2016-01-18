#!/usr/bin/python
import urllib2
import urlparse
import xml.etree.ElementTree as ET
from StringIO import StringIO
import re

def parseXMLURL(url):
    """given a url downloads it and parses it, discarding namespace shenanigans"""
    """returns an ElementTree root node"""
    data = urllib2.urlopen(url).read()
    data = re.sub(u'<(/?)[a-zA-Z_-]*?:',u'<\\1',data)
    return parseXML(data)

def parseXML(data):
    """given data, parses as XML, discarding namespace shenanigans"""
    """returns an ElementTree root node"""
    if isinstance(data,unicode):
        data = data.encode('utf-8')
    it = ET.iterparse(StringIO(data))
    for _, el in it:
        if u'}' in el.tag:
            el.tag = el.tag.split(u'}', 1)[1]  # strip all namespaces
    return it.root
    
def xml_make_dict(node):
    """from a node make a dict of all first children containing only text"""
    dct = {}
    for i in node:
        if i.text and i.text.strip():
            if i.text[0]=='_': continue # skip anything starting with an underscore - could be naughty
            dct[i.tag] = i.text.strip()
    return dct
    
    
class ServiceBase(object):
    def __init__(self,controlURL,eventURL,service_desc):
        self._controlURL = controlURL
        self._eventURL = eventURL
        self._service_desc = service_desc
        
    def _call_action(self,name,**kwargs):
        request = ET.Element('s:Envelope',
                             {'xmlns:s':"http://schemas.xmlsoap.org/soap/envelope/",
                              's:encodingStyle':"http://schemas.xmlsoap.org/soap/encoding/"})
        body = ET.SubElement(request,'s:Body')
        actionName = ET.SubElement(body,'u:%s' % name,{'xmlns:u':self._service_desc['serviceType']})
        for arg,value in kwargs.items():
            ET.SubElement(actionName,arg).text = unicode(value)
        data = ET.tostring(request,encoding="UTF-8")
        req = urllib2.Request(self._controlURL,data,
                              {'SOAPACTION':self._service_desc['serviceType']+"#"+name,
                               'CONTENT-TYPE': 'text/xml; charset="UTF-8"'})
        response = urllib2.urlopen(req)
        return response.read()

def get_action(action,state_vars,defaults):
    in_vars = []
    out_vars = []
    var_types = {}
    default_vars = {}
    name = action.find('name').text.strip()
    arg_list = action.find('argumentList')
    #create lists of variables
    if arg_list is not None:
        for arg in arg_list:
            fields = xml_make_dict(arg)
            arg_name = fields['name']
            field_name = fields['relatedStateVariable']
            var_types[arg_name] = state_vars[field_name]
            if fields['direction']=='in':
                in_vars += [arg_name]
                key = field_name.replace('A_ARG_TYPE_','')
                if key in defaults:
                    default_vars[arg_name] = defaults[key]
            else:
                out_vars += [arg_name]
    def f(self,**kwargs):
        temp_kwargs = default_vars.copy()
        temp_kwargs.update(kwargs)
        assert set(temp_kwargs.keys())==set(in_vars)
        results = parseXML(self._call_action(name,**temp_kwargs))
        result_dct = {}
        for x in results.find('.//BrowseResponse'):
            result_dct[x.tag] = x.text
        return result_dct
        

    in_var_texts = []
    for var in in_vars:
        if var in default_vars:
            in_var_texts += [var+'='+str(default_vars[var])]
        else:
            in_var_texts += [var]
    f.__doc__ = "{name} ({in_vars}) -> ({out_vars})".format(
        name = name, 
        in_vars = ', '.join(in_var_texts), 
        out_vars = ', '.join(out_vars))
    f.__name__ = name
    return f
    
    
def get_service(url,service_desc):
    default_args = {
        'ContentDirectory':{'ObjectID':'0','SearchCriteria':'*','BrowseFlag':'BrowseDirectChildren',
                             'Filter':'*','SortCriteria':'','Index':0,'Count':0},
        'RenderingControl':{'InstanceID':0,'Channel':'Master'},
        'AVTransport':     {'InstanceID':0,'TransportPlaySpeed':"1",'CurrentPlayMode':'Normal'},
    }
    url = urlparse.urljoin(url,service_desc['SCPDURL'])
    try:
        root = parseXMLURL(url)
    except urllib2.HTTPError:
        return None
    #find all state Variables
    state_vars = {}
    for var in root.find('serviceStateTable'):
        name = var.find('name').text.strip()
        data_type = var.find('dataType').text.strip()
        state_vars[var.find('name').text.strip()] = data_type
    service_name = service_desc['serviceId'].split(':')[3] 
    klaus = type(service_name,(ServiceBase,),{'__doc__':'tests'})
    for action in root.find('actionList'):
        func = get_action(action,state_vars,default_args.get(service_name,{}))
        setattr(klaus,func.__name__,func)
    return klaus(urlparse.urljoin(url,service_desc['controlURL']),
                 urlparse.urljoin(url,service_desc['eventSubURL']),
                 service_desc)

        
class Device:
    def __init__(self,url):
        root = parseXMLURL(url)
        for i in root.find('device'):
            if i.text and i.text.strip():
                if i.text[0]=='_': continue # skip anything starting with an underscore - could be naughty
                setattr(self,i.tag,i.text.strip())
            if i.tag.endswith('List'):
                setattr(self,i.tag,[dict((k.tag,k.text) for k in j) for j in i])
        if hasattr(self,'serviceList'):
            for s in self.serviceList:
                service_name = s['serviceId'].split(':')[3]
                setattr(self,service_name,get_service(url,s))
                
if __name__ == "__main__":
    d = Device('file:description.xml')
    print d.__dict__
