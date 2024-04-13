import bgapi
import argparse
import os
import time
import sys
import pyBLE

# https://www.silabs.com/documents/public/application-notes/an1086-gecko-bootloader-bluetooth.pdf#page=16
# AN1086 table 3.1
uuid_ezble_service = pyBLE.uuid_to_bytes('DE8A5AAC-A99B-C315-0C80-60D4CBB5BEEF')
uuid_ezble_data    = pyBLE.uuid_to_bytes('5B026510-4088-C297-46D8-BE6C7367BEEF')

# Generic Access
uuid_generic_access = pyBLE.uuid_to_bytes(0x1800)
uuid_device_name    = pyBLE.uuid_to_bytes(0x2a00)
uuid_appearance     = pyBLE.uuid_to_bytes(0x2a01)

def get_default_xapi() :
    GSDK = os.environ.get('GSDK')
    if None == GSDK :
        return None
    return GSDK + '/protocol/bluetooth/api/sl_bt.xapi'

state = 'start'
def set_state(new_state) :
    global state
    if args.debug :
        print('set_state: %s -> %s'%(state,new_state))
    state = new_state
        
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


def generate_gatt() :
    debug('generate_gatt()')
    global handles
    session = l.bt.gattdb.new_session().session
    handle_generic_access = l.bt.gattdb.add_service(session,
                                                    l.bt.gattdb.SERVICE_TYPE_PRIMARY_SERVICE,
                                                    0, # service property flags
                                                    uuid_generic_access).service
    debug('handle_generic_access: 0x%x'%(handle_generic_access))
    handle_ezble_service = l.bt.gattdb.add_service(session,
                                                 l.bt.gattdb.SERVICE_TYPE_PRIMARY_SERVICE,
                                                 0, # service property flags
                                                 uuid_ezble_service).service
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
    handle_ezble_data = l.bt.gattdb.add_uuid128_characteristic(
        session,
        handle_ezble_service,
        l.bt.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_WRITE \
        | l.bt.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_WRITE,
        0, # security
        0, # flag
        uuid_ezble_data,
        l.bt.gattdb.VALUE_TYPE_USER_MANAGED_VALUE,
        0, # maxlen --- ignored for USER MANAGED
        b'' # ignored ""
    ).characteristic
    l.bt.gattdb.start_service(session,handle_generic_access)
    l.bt.gattdb.start_service(session,handle_ezble_service)
    l.bt.gattdb.commit(session)
    handles = {}
    for uuid in [uuid_ezble_data] :
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

def start_service_discovery() :
    l.bt.gatt.discover_primary_services(connection)
    set_state('service-discovery')

def on_boot(evt) :
    advertising_handle = None
    generate_gatt()
    l.bt.connection.open('a4:6d:d4:64:5a:ee',0, l.bt.scanner.SCAN_PHY_SCAN_PHY_1M
)
#    start_advertising()

def on_gatt_ready(evt) :
    start_service_discovery()

services = {} # uuid:handle
characteristics = {} # service_handle:{uuid:handle}

def on_gatt_procedure_completed(evt) :
    global current_service, services_to_discover
    if 'service-discovery' == state :
        print(services)
        print(uuid_ezble_service)
        handle = services.get(int.from_bytes(uuid_ezble_service,'little'))
        if None == handle :
            print('ezBLE Service not found in GATT')
            l.bt.connection.close(connection)
            set_state('closing')
            return
        services_to_discover = [handle]
        set_state('characteristic-discovery')
    if 'characteristic-discovery' == state :
        if 0 == len(services_to_discover) :
            handle = services.get(int.from_bytes(uuid_ezble_service,'little'))
            print(characteristics[handle])
            return
        current_service = services_to_discover.pop()
        characteristics[current_service]= {}
        l.bt.gatt.discover_characteristics(connection,current_service)
        return
    if 'subscribing' == state :
        if not subscribe() :
            set_state('running')
            set_rate()
            
def on_gatt_service(evt) :
    if args.debug :
        print(evt)
    uuid = int.from_bytes(evt.uuid,'little')
    if debug : print('uuid: 0x%x'%(uuid))
    services[uuid] = evt.service

remote = None
def on_gatt_characteristic(evt) :
    global remote
    if args.debug :
        print(evt)
    uuid = int.from_bytes(evt.uuid,'little')
    debug('uuid: 0x%x'%(uuid))
    characteristics[current_service][uuid] = evt.characteristic
    remote = evt.characteristic
    
def on_gatt_characteristic_value(evt) :
    pass

def on_close(evt) :
    global connection, cccd
    debug('connection closed, reason:0x%x'%(evt.reason))
    connection = None
    l.bt.system.reset(0)

def on_open(evt) :
    global connection, cccd
    debug('connection from %s'%(evt.address))
    connection = evt.connection

count = 0
def on_write(evt) :
    global count
    debug('on_write(%s)'%(evt.__str__()[:160]))
    if handles.get(uuid_ezble_data) == evt.characteristic :
        debug('ezBLE Data')
        count += 1
        l.bt.gatt_server.send_user_write_response(connection,evt.characteristic,0)
        print(evt.value.decode(),end='')
        if 0 == (count % 10) :
            l.bt.gatt.write_characteristic_value(connection,remote,'Received %d messages'%(count))

def ignore_event(evt) :
    pass

handlers = {'system_boot':on_boot,
            'connection_closed':on_close,
            'connection_opened':on_open,
            'gatt_server_user_write_request':on_write,
            'connection_parameters':ignore_event,
            'connection_phy_status':ignore_event,
            'connection_remote_used_features':ignore_event,
            'connection_data_length':ignore_event,
            'gatt_procedure_completed':on_gatt_procedure_completed,
            'gatt_service':on_gatt_service,
            'gatt_characteristic':on_gatt_characteristic,
            'gatt_characteristic_value':on_gatt_characteristic_value,
            'gatt_mtu_exchanged':on_gatt_ready,
}

def main_loop(passed=None) :
    print('main')
    global stdscr, send_at, counter, failures
    stdscr = passed
    while True :
        try :
            e = l.get_event()
        except  :
            break
        #tm.process()
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
