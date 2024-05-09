import bgapi
import argparse
import os
import time
import sys
import pyBLE
from machine import Callback, Timer, State
from bt import BT

uuids = {
    "time_service" : int.to_bytes(0x1805,2,'little'),
    "current_time" : int.to_bytes(0x2a2b,2,'little'),
    "local_time"   : int.to_bytes(0x2a0f,2,'little')
}

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
parser.add_argument('--baud',type=int,default=115200,help='baudrate, must match configuration of NCP')
parser.add_argument('--debug',action='store_true',help='show generally uninteresting info')
parser.add_argument('--interval',type=float,default=1,help='interval between notifications')
args = parser.parse_args()

if args.debug :
    print('args:',args)

def debug(message) :
    if args.debug :
        print(message)

def current_time() :
    tnow = time.time() - time.altzone
    fraction = tnow - int(tnow)
    s256 = int(256*fraction)
    now = time.gmtime(int(tnow))
    date_time = int.to_bytes(now.tm_year,2,'little')
    date_time += bytes(
        [now.tm_mon,
         now.tm_mday,
         now.tm_hour,
         now.tm_min,
         now.tm_sec,
         now.tm_wday+1,
         s256,0])
    return date_time
    
def local_time() :
    timezone = time.timezone // (15*60)
    dstoffset = (time.timezone - time.altzone ) // (15*60)
    return bytes([timezone,dstoffset])

bt = BT(args.xapi, args.ip, args.uart, args.baud, debug=debug)
bt.api.system.reset(0)

handles = {}

'''
,
            'connection_closed':on_close,
            'connection_opened':on_open,
            'gatt_server_characteristic_status':on_characteristic_status,
            :on_read,
            'connection_parameters':ignore_event,
            'connection_phy_status':ignore_event,
            'connection_remote_used_features':ignore_event,
            'connection_data_length':ignore_event,
            'gatt_mtu_exchanged':on_mtu,
}
'''
class Client :
    def __init__(self,evt) :
        self.name = 'Client-'+evt.address
        self.state = State(self.name,'open')
        self.connection = evt.connection
        self.notify_timer = None
        bt.on_connection_event(
            self.connection,
            'connection-closed',
            self.on_close)
        bt.on_connection_event(
            self.connection,
            'gatt-server-user-read-request',
            self.on_read)
        bt.on_connection_event(
            self.connection,
            'gatt-mtu-exchanged',
            self.on_mtu)
        bt.on_connection_event(
            self.connection,
            'gatt-server-characteristic-status',
            self.on_characteristic_status)
    def on_read(self, evt) :
        if evt.characteristic == handles['current_time'] :
            bt.api.gatt_server.send_user_read_response(
                evt.connection,
                evt.characteristic,
                0,current_time())
        elif evt.characteristic == handles['local_time'] :
            bt.api.gatt_server.send_user_read_response(
                evt.connection,
                evt.characteristic,
                0,local_time())
    def on_mtu(self, evt) :
        self.mtu = evt.mtu
    def on_close(self, evt) :
        if None != self.notify_timer :
            self.notify_timer.cancel()
        on_close(evt)
    def on_characteristic_status(self, evt) :
        if 2 == evt.status_flags :
            return # just confirmation
        if 1 != evt.status_flags :
            raise RuntimeError('not handled evt.status_flags:%d'%(evt.status_flags))
        if 1 == evt.client_config_flags :
            self.notify_timer = tm.periodic(args.interval,Callback(self.send_notification))
        elif 2 == evt.client_config_flags :
            pass
        else :
            notify_timer.cancel()
    def send_notification(self) :
        bt.api.gatt_server.send_notification(
            self.connection,
            handles['current_time'],current_time())
    
state = State('Application')

handles = {}

def generate_gatt() :
    session = bt.api.gattdb.new_session().session
    
    handle_service = bt.api.gattdb.add_service(session,
                                             bt.api.gattdb.SERVICE_TYPE_PRIMARY_SERVICE,
                                             0, # service property flags
                                             uuids['time_service']).service
    bt.api.gattdb.add_uuid16_characteristic(
        session,
        handle_service,
        bt.api.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_READ
        | bt.api.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_NOTIFY,
        0, # security
        0, # flag
        uuids['current_time'],
        bt.api.gattdb.VALUE_TYPE_USER_MANAGED_VALUE,
        0, # maxlen --- ignored for USER MANAGED
        b'' # ignored ""
    ).characteristic
    bt.api.gattdb.add_uuid16_characteristic(
        session,
        handle_service,
        bt.api.gattdb.CHARACTERISTIC_PROPERTIES_CHARACTERISTIC_READ,
        0, # security
        0, # flag
        uuids['local_time'],
        bt.api.gattdb.VALUE_TYPE_USER_MANAGED_VALUE,
        0, # maxlen --- ignored for USER MANAGED
        b'' # ignored ""
    ).characteristic
    bt.api.gattdb.start_service(session,handle_service)
    bt.api.gattdb.commit(session)
    for name in uuids :
        try :
            resp = bt.api.gatt_server.find_attribute(1,uuids[name])
            if 0 == resp.result :
                handles[name] = resp.attribute
        except :
            pass
    print(handles)
    
advertising_handle = None

def start_advertising() :
    debug('start_advertising')
    global advertising_handle
    if None == advertising_handle :
        advertising_handle = bt.api.advertiser.create_set().handle
        flags = bytes([2,1,6])
        uuids16 = bytes([3,3])+uuids['time_service']
        name = 'Time Server'.encode()
        adname = bytes([1+len(name),9])+name
        bt.api.legacy_advertiser.set_data(
            advertising_handle,
            0,
            flags + uuids16 + adname)
    bt.api.legacy_advertiser.start(
        advertising_handle,
        bt.api.legacy_advertiser.CONNECTION_MODE_CONNECTABLE)
    debug('started legacy advertising')
    state.set('advertising')
    
def on_boot(evt) :
    global cccd, advertising_handle
    cccd = {}
    advertising_handle = None
    state.set('boot')
    generate_gatt()
    start_advertising()

def on_close(evt) :
    global connection
    debug('connection closed, reason:0x%x'%(evt.reason))
    connections.pop(evt.connection)
    state.set('close')
    quit()

connections = {}

def on_open(evt) :
    debug('connection from %s'%(evt.address))
    connections[evt.connection] = Client(evt)
    if len(connections) < 4 :
        start_advertising()

def ignore_event(evt) :
    pass

bt.on_event('system-boot',on_boot)
bt.on_event('connection-opened',on_open)

tm = Timer()

def main_loop(passed=None) :
    print('main')
    global stdscr, send_at, counter, failures
    stdscr = passed
    while True :
        bt.process_event()
        tm.process()

if False and args.curses :
    wrapper(main_loop)
else :
    main_loop()
    
bt.api.system.reset(0)
bt.close()
