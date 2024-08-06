import bgapi
import argparse
import os
import time
import sys

class State:
    def __init__(name,state='created',callback=None) :
        self.name = name
        self.state = state
        self.callback=callback
    def set(self,state) :
        debug('State.set: %s %s -> %s'%(self.name,self.state,state))
        old = self.state
        self.state = state
        if None == self.callback :
            return
        self.callback(old,state)
        
print(sys.argv)
# Locate current script
def get_script_folder(debug=False) :
    if debug : print('__file__:'+__file__)
    cwd = os.path.abspath(os.curdir)
    parts = __file__.split('/')
    if debug : print('parts:'+parts.__str__())
    count = len(parts)
    if 1 == count :
        if debug : print('no slashes, assume CWD')
        return cwd
    if len(parts[0]) > 0 :
        if debug : print('not absolute path, prepend CWD')
        parts = cwd.split('/') + parts
    return '/'.join(parts[:-1])

sys.path.append(get_script_folder()+'/../pyENOSPC')
import pyBLE

# https://www.silabs.com/documents/public/application-notes/an1086-gecko-bootloader-bluetooth.pdf#page=16
# AN1086 table 3.1
uuid_ota_service = pyBLE.uuid_to_bytes('1d14d6ee-fd63-4fa1-bfa4-8f47b42119f0')
uuid_ota_control = pyBLE.uuid_to_bytes('F7BF3564-FB6D-4E53-88A4-5E37E0326063')
uuid_ota_data    = pyBLE.uuid_to_bytes('984227F3-34FC-4045-A5D0-2C581F81A153')

# Generic Access
uuid_generic_access = pyBLE.uuid_to_bytes(0x1800)
uuid_device_name    = pyBLE.uuid_to_bytes(0x2a00)
uuid_appearance     = pyBLE.uuid_to_bytes(0x2a01)

# Heath Thermoeter Service
uuid_health_thermometer       = pyBLE.uuid_to_bytes(0x1809)
uuid_temperature_measurement  = pyBLE.uuid_to_bytes(0x2a1c)
uuid_temperature_type         = pyBLE.uuid_to_bytes(0x2a1d)
uuid_intermediate_temperature = pyBLE.uuid_to_bytes(0x2a1e)
uuid_measurement_interval     = pyBLE.uuid_to_bytes(0x2a21)

def get_default_xapi() :
    GSDK = os.environ.get('GSDK')
    if None == GSDK :
        return None
    return GSDK + '/protocol/bluetooth/api/sl_bt.xapi'

parser = argparse.ArgumentParser()
parser.add_argument('--xapi',default=get_default_xapi(),help='file describing API {GSDK}/protocol/bluetooth/api/sl_bt.xapi')
connector = parser.add_mutually_exclusive_group(required=True)
connector.add_argument('--uart',help='connection by UART to NCP target')
connector.add_argument('--ip',help='connection by TCP/IP to NCP target')
application = parser.add_mutually_exclusive_group()
application.add_argument('--application-ota',action='store_true',help='No AppLoader, application handles OTA')
application.add_argument('--application-invalid',action='store_true',help='Application is invalid (enter AppLoader immediately)')
parser.add_argument('--baud',type=int,default=115200,help='baudrate, must match configuration of NCP')
parser.add_argument('--debug',action='store_true',help='show generally uninteresting info')
parser.add_argument('--length',type=int,default=20,help='notification length')
parser.add_argument('--rate',type=int,default=1000,help='notifications per second')
args = parser.parse_args()

if args.debug :
    print('args:',args)

if None != args.ip :
    connector = bgapi.SocketConnector((args.ip,4901))
else :
    connector = bgapi.SerialConnector(args.uart)
l = bgapi.BGLib(connector,args.xapi)

l.open()
l.bt.system.reset(0)

def debug(message) :
    if args.debug :
        print(message)

cccd = {}
handles = {}

def validate_image(image) :
    fh = open('image.gbl','wb')
    fh.write(image)
    fh.close()
    rc = os.system('commander gbl parse image.gbl --app app.hex --bootloader.hex')
    if 0 == rc :
        print('Transfered image conains valid application and bootloader')
        if args.application_ota :
            return True
        print('However, this is incompatible with AppLoader')
        return False
    rc = os.system('commander gbl parse image.gbl --app app.hex')
    if 0 == rc :
        print('Transfered image conains valid application')
        return True
    rc = os.system('commander gbl parse image.gbl --bootloader bootloader.hex')
    if 0 == rc :
        print('Transfered image conains valid bootloader but no application.')
        if args.application_ota :
            print('This is incompatible with Application OTA since bootloader instalation')
            print('will corrupt application and no replacement in slot')
        return False
    return False
    
def callback_close(data) :
    debug('callback_close()')
    l.bt.connection.close(connection)

class Histo :
    def __init__(self) :
        self.dict = {}
    def add(self,value) :
        count = self.dict.get(value)
        if None == count :
            count = 0
        self.dict[value] = count + 1
    def render(self) :
        keys = list(self.dict.keys())
        keys.sort()
        lines = []
        for key in keys :
            lines.append('%d: %d'%(key,self.dict[key]))
        return '\n'.join(lines)
    
class Global() :
    def __init__(self) :
        self.apploader_present = not args.application_ota 
        self.application_valid = args.application_ota or not args.application_invalid
        self.state = 'start'
        self.active = None
        self.apploader_flag = False
        self.image = None
    def set_state(self,state) :
        debug('Global state: %s -> %s'%(self.state,state))
        old = self.state
        self.state = state
        if old != state:
            self.on_change(state)
    def on_change(self,state) :
        if 'reset' == state :
            if not self.application_valid and self.image != None :
                self.application_valid = validate_image(self.image)
            self.active = ["apploader","application"][self.application_valid and not self.apploader_flag]
            self.apploader_flag = False
            self.ota_started = False
        debug('active: %s'%(self.active))
        debug('show_thermometer(): %s'%(self.show_thermometer()))
    def invalidate_application(self) :
        self.application_valid = False
    def show_ota_data(self) :
        return 'apploader' == self.active or args.application_ota
    def show_thermometer(self) :
        return 'application' == self.active
    def write_control(self,data) :
        debug('global.write_control(%s)'%(data.__str__()))
        if ('application' == self.active and args.application_ota) or 'apploader' == self.active :
            if not self.ota_started :
                self.ota_started = True
                self.ota_done = False
                self.image = b''
                self.histo = Histo()
                if data != b'\x00' :
                    print('Warning: OTA started with %s'%(data.__str__()))
            else :
                self.ota_done = True
                debug('Histogram:\n%s"'%(self.histo.render()))
                if data != b'\x03' :
                    print('Warning: OTA stoped with %s'%(data.__str__()))
        else :
            tm.create_oneshot(10e-3,callback_close)
            self.apploader_flag = True
    def write_data(self,data) :
        if not self.ota_started :
            print('Warning write to OTA Data before OTA started')
            return
        if self.ota_done :
            print('Warning write to OTA Data after OTA stopped')
            return
        else :
            if len(data) % 4 :
                print('Invalid data length (%d)'%(len(data)))
            self.histo.add(len(data))
            self.image += data
            if self.application_valid :
                self.invalidate_application()
            
app = Global()

def generate_gatt() :
    debug('generayr_gatt()')
    global handles
    session = l.bt.gattdb.new_session().session
    handle_generic_access = l.bt.gattdb.add_service(session,
                                                    l.bt.gattdb.SERVICE_TYPE_PRIMARY_SERVICE,
                                                    0, # service property flags
                                                    uuid_generic_access).service
    debug('handle_generic_access: 0x%x'%(handle_generic_access))
    if app.show_thermometer() :
        handle_health_thermometer = l.bt.gattdb.add_service(session,
                                                            l.bt.gattdb.SERVICE_TYPE_PRIMARY_SERVICE,
                                                            l.bt.gattdb.SERVICE_PROPERTY_FLAGS_ADVERTISED_SERVICE,
                                                            uuid_health_thermometer).service
    handle_ota_service = l.bt.gattdb.add_service(session,
                                                 l.bt.gattdb.SERVICE_TYPE_PRIMARY_SERVICE,
                                                 0, # service property flags
                                                 uuid_ota_service).service
    handle_device_name = l.bt.gattdb.add_uuid16_characteristic(
        session,
        handle_generic_access,
        l.bt.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_READ \
        | l.bt.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_WRITE,
        0, # security
        0, # flag
        uuid_device_name,
        l.bt.gattdb.VALUE_TYPE_VARIABLE_LENGTH_VALUE,
        20, # maxlen
        b'AppLoader Simulator' # value
    ).characteristic
    handle_appearance = l.bt.gattdb.add_uuid16_characteristic(
        session,
        handle_generic_access,
        l.bt.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_READ,
        0, # security
        0, # flag
        uuid_appearance,
        l.bt.gattdb.VALUE_TYPE_FIXED_LENGTH_VALUE,
        2, # maxlen
        b'\x00\x00' # value
    ).characteristic
    if app.show_thermometer() :
        handle_temperature_measurement = l.bt.gattdb.add_uuid16_characteristic(
            session,
            handle_health_thermometer,
            l.bt.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_INDICATE,
            0, # security
            0, # flag
            uuid_temperature_measurement,
            l.bt.gattdb.VALUE_TYPE_USER_MANAGED_VALUE,
            0, # maxlen --- ignored for USER MANAGED
            b'' # ignored ""
        ).characteristic
        handle_temperature_type = l.bt.gattdb.add_uuid16_characteristic(
            session,
            handle_health_thermometer,
            l.bt.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_READ,
            0, # security
            0, # flag
            uuid_temperature_measurement,
            l.bt.gattdb.VALUE_TYPE_USER_MANAGED_VALUE,
            0, # maxlen --- ignored for USER MANAGED
            b'' # ignored ""
        ).characteristic
    handle_ota_control = l.bt.gattdb.add_uuid128_characteristic(
        session,
        handle_ota_service,
        l.bt.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_WRITE,
        0, # security
        0, # flag
        uuid_ota_control,
        l.bt.gattdb.VALUE_TYPE_USER_MANAGED_VALUE,
        0, # maxlen --- ignored for USER MANAGED
        b'' # ignored ""
    ).characteristic
    if app.show_ota_data() :
        handle_ota_data = l.bt.gattdb.add_uuid128_characteristic(
            session,
            handle_ota_service,
            l.bt.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_WRITE_NO_RESPONSE \
            | l.bt.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_WRITE,
            0, # security
            0, # flag
            uuid_ota_data,
            l.bt.gattdb.VALUE_TYPE_USER_MANAGED_VALUE,
            0, # maxlen --- ignored for USER MANAGED
            b'' # ignored ""
        ).characteristic
    l.bt.gattdb.start_service(session,handle_generic_access)
    if app.show_thermometer() :
        l.bt.gattdb.start_service(session,handle_health_thermometer)
    l.bt.gattdb.start_service(session,handle_ota_service)
    l.bt.gattdb.commit(session)
    handles = {}
    for uuid in [uuid_ota_control, uuid_ota_data,uuid_temperature_measurement] :
        try :
            resp = l.bt.gatt_server.find_attribute(1,uuid)
            if 0 == resp.result :
                handles[uuid] = resp.attribute
        except bgapi.bglib.CommandFailedError :
            pass
    debug('handles: %s'%(handles.__str__()))
            
advertising_handle = None
connection = None
send = False
send_rate = args.rate

def start_advertising() :
    debug('start_advertising')
    global advertising_handle
    if None == advertising_handle :
        advertising_handle = l.bt.advertiser.create_set().handle
    l.bt.legacy_advertiser.generate_data(advertising_handle,
                                         l.bt.advertiser.DISCOVERY_MODE_GENERAL_DISCOVERABLE)
    l.bt.legacy_advertiser.start(advertising_handle,
                                 l.bt.legacy_advertiser.CONNECTION_MODE_CONNECTABLE)
    debug('started legacy advertising')
    
def on_boot(evt) :
    global cccd, advertising_handle
    cccd = {}
    advertising_handle = None
    app.set_state('reset')
    generate_gatt()
    start_advertising()

def on_close(evt) :
    global connection, cccd
    debug('connection closed, reason:0x%x'%(evt.reason))
    connection = None
    app.set_state('close')
    l.bt.system.reset(0)

def on_open(evt) :
    global connection, cccd
    debug('connection from %s'%(evt.address))
    connection = evt.connection
    app.set_state('open')

def on_characteristic_status(evt) :
    if 2 == evt.status_flags :
        return # just confirmation
    if 1 != evt.status_flags :
        raise RuntimeError('not handled evt.status_flags:%d'%(evt.status_flags))
    cccd[evt.characteristic] = evt.client_config_flags

def on_write(evt) :
    debug('on_write(%s)'%(evt.__str__()[:160]))
    if handles.get(uuid_ota_control) == evt.characteristic :
        debug('OTA Control')
        l.bt.gatt_server.send_user_write_response(connection,evt.characteristic,0)
        app.write_control(evt.value)
    if handles.get(uuid_ota_data) == evt.characteristic :
        debug('OTA Data')
        if 18 == evt.att_opcode :
            l.bt.gatt_server.send_user_write_response(connection,evt.characteristic,0)
        app.write_data(evt.value)

def ignore_event(evt) :
    pass

handlers = {'system_boot':on_boot,
            'connection_closed':on_close,
            'connection_opened':on_open,
            'gatt_server_characteristic_status':on_characteristic_status,
            'gatt_server_user_write_request':on_write,
            'connection_parameters':ignore_event,
            'connection_phy_status':ignore_event,
            'connection_remote_used_features':ignore_event,
            'connection_data_length':ignore_event,
            'gatt_mtu_exchanged':ignore_event,
}

def process_measurement(data) :
    handle = handles.get(uuid_temperature_measurement)
    if None == handle :
        return
    if 2 == cccd.get(handle) :
        l.bt.gatt_server.send_indication(connection,handle,b'\x00\xc7\x81\x00\xfd')
        
class Timeout_Manager :
    class Timeout :
        def __init__(self,target,callback,data,periodic=None) :
            self.target = target
            self.periodic = periodic
            self.callback = callback
            self.data = data
    def __init__(self) :
        self.timeouts = []
    def process(self) :
        #print('Timeout_Manager.process',self.timeouts)
        if len(self.timeouts) == 0 :
            return
        if self.timeouts[0].target > time.time() :
            return
        timeout = self.timeouts.pop(0)
        if None != timeout.periodic :
            timeout.target += timeout.periodic
            self.insert(timeout)
        timeout.callback(timeout.data)
        return
    def insert(self,timeout) :
        for i in range(len(self.timeouts)) :
            print('i:',i)
            if self.timeouts[i].target > timeout.target :
                self.timeouts = self.timeouts[:i] + [timeout] + self.timeouts[i+1:]
                print(self.timeouts)
                return
        self.timeouts.append(timeout)
    def create_periodic(self,duration,callback,data=None) :
        print('create_periodic(%f)'%(duration))
        timeout = self.Timeout(time.time()+duration,callback,data,periodic=duration)
        self.insert(timeout)
        return timeout
    def create_oneshot(self,duration,callback,data=None) :
        print('create_oneshot(%f)'%(duration))
        timeout = self.Timeout(time.time()+duration,callback,data)
        self.insert(timeout)
        return timeout

tm = Timeout_Manager()
#tm.create_periodic(10,process_measurement,None)

def main_loop(passed=None) :
    print('main')
    global stdscr, send_at, counter, failures
    stdscr = passed
    while True :
        try :
            e = l.get_event()
        except  :
            break
        tm.process()
        if None == e :
            continue
        event_name = e.__str__().split('_evt_')[1].split('(')[0] #simplify event name
        debug('main_loop: event_name %s'%(event_name))
        handler = handlers.get(event_name)
        if None == handler :
            print('Not handled event: %s'%(e.__str__()))
            continue
        handler(e)

if False and args.curses :
    wrapper(main_loop)
else :
    main_loop()
    
l.bt.system.reset(0)
l.close()
