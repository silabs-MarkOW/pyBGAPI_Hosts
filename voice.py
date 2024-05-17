import bgapi
import argparse
import os
import time
import sys
import advertiser
import pyBLE
from machine import Timer, Callback, State, register_timer
from bt import BT, Peripheral, Connections

uuids = {
  "voble_service"  : pyBLE.uuid_to_bytes("b7ef1193-dc2e-4362-93d3-df429eb3ad10"),
  "audio_data"     : pyBLE.uuid_to_bytes("00ce7a72-ec08-473d-943e-81ec27fdc5f2"),
  "sample_rate"    : pyBLE.uuid_to_bytes("00ce7a72-ec08-473d-943e-81ec27fdc601"),
  "filter_enable"  : pyBLE.uuid_to_bytes("00ce7a72-ec08-473d-943e-81ec27fdc602"),
  "encoding_enable": pyBLE.uuid_to_bytes("00ce7a72-ec08-473d-943e-81ec27fdc603"),
  "transfer_status": pyBLE.uuid_to_bytes("00ce7a72-ec08-473d-943e-81ec27fdc604"),
  "audio_channels" : pyBLE.uuid_to_bytes("00ce7a72-ec08-473d-943e-81ec27fdc605"),
  "stream_enable"  : pyBLE.uuid_to_bytes("a5a31dd4-77a4-4c9a-a4b1-639f5e42714d"),
  "resend_req"     : pyBLE.uuid_to_bytes("2be6654d-be90-4cf6-8d4c-4e95e1993d6a")
}
        
def get_default_xapi() :
    if None != os.environ.get('DARWIN') :
        XAPI = os.environ.get('DARWINAPI')
        if None != XAPI :
            return XAPI
    GSDK = os.environ.get('GSDK')
    if None == GSDK :
        return None
    return GSDK + '/protocol/bluetooth/api/sl_bt.xapi'

parser = argparse.ArgumentParser()
parser.add_argument('--xapi',default=get_default_xapi())
parser.add_argument('-t','--timeout',type=float,default=0)
parser.add_argument('--debug',type=int,default=0)
parser.add_argument('--interval',type=float,default=10)
parser.add_argument('--adpcm',action='store_true')
parser.add_argument('--filter',action='store_true')
parser.add_argument('--bits',type=int,default=16,help='sample bits (8,16)')
parser.add_argument('--connection-timeout',type=float,default=5,help='timeout on attempt to connect')
parser.add_argument('--sample-rate',type=int,default=16000)
conn = parser.add_mutually_exclusive_group(required=True)
conn_uart = conn.add_argument_group()
conn.add_argument('--uart')
conn_uart.add_argument('--baudrate',type=int,default=115200)
conn.add_argument('--ip',help='IP address of WSTK with NCP target')
phy = parser.add_mutually_exclusive_group()
phy.add_argument('--coded-phy',action='store_true')
phy.add_argument('--1m-phy',action='store_true')
phy.add_argument('--2m-phy',action='store_true')

#how = parser.add_mutually_exclusive_group(required=True)
#how.add_argument('--address')
#how.add_argument('--name')
#parser.add_argument('--ip')
args = parser.parse_args()
        
if args.debug :
    print('args:',args)

def debug(message) :
    if args.debug :
        print(message)


connection = None
send = False
scanner_active = False

def start_scanner(context=None) :
    global scanner_active
    if args.debug :
        print('start_scanner()')
    if False and args.active :
        scan_mode = bt.api.scanner.SCAN_MODE_SCAN_MODE_ACTIVE
    else :
        scan_mode = bt.api.scanner.SCAN_MODE_SCAN_MODE_PASSIVE    
    phy = bt.api.scanner.SCAN_PHY_SCAN_PHY_1M
    if args.coded_phy :
        phy = bt.api.scanner.SCAN_PHY_SCAN_PHY_CODED
    discover_mode = bt.api.scanner.DISCOVER_MODE_DISCOVER_OBSERVATION
#    if args.discover_generic :
#        discover_mode = bt.api.scanner.DISCOVER_MODE_DISCOVER_GENERIC
#    if args.discover_limited :
#        discover_mode = bt.api.scanner.DISCOVER_MODE_DISCOVER_LIMITED
    bt.api.scanner.set_parameters(scan_mode,0x10,0x10)
    bt.api.scanner.start(phy,discover_mode)
    scanner_active = True

def stop_scanner(context=None) :
    global scanner_active
    if args.debug :
        print('stop_scanner()')
    bt.api.scanner.stop()
    scanner_active = False    

def on_boot(evt) :
    bt.on_event('scanner-legacy-advertisement-report',on_advertising_report)
    state.set('scan')

def local_quit() :
    quit()
    
bt = BT(args.xapi,ip=args.ip,uart=args.uart,baudrate=args.baudrate)
bt.api.system.reset(0)
bt.on_event('system-boot',on_boot)
timer = Timer(debug=debug)
bt.register_timer(timer)
register_timer(timer)
state = State('Global',debug=debug)
connections = Connections(bt,debug=debug)
connections.set_connection_timeout(args.connection_timeout)
connections.state.on_enter('open',Callback(state.set,"discovery"))
connections.state.on_enter('discovery-complete',Callback(state.set,"write-settings"))
connections.state.on_enter('error',Callback(state.set,"exit"))
connections.state.on_enter('closed',Callback(state.set,"exit"))
state.on_enter("scan",Callback(start_scanner))
state.on_exit("scan",Callback(stop_scanner))
state.on_enter("connect",Callback(connections.open))
state.on_enter("discovery",Callback(connections.discover))
state.on_enter('run',Callback(connections.run))
state.on_enter("disconnect",Callback(connections.close))
state.on_enter("exit",Callback(local_quit))
settings = {
    uuids['voble_service']:{
        uuids['sample_rate']:int.to_bytes(args.sample_rate,2,'little'),
        #uuids['sample_bits']:int.to_bytes(args.bits,1,'little'),
        uuids['filter_enable']:int.to_bytes(args.filter,1,'little'),
        uuids['encoding_enable']:int.to_bytes(args.adpcm,1,'little'),
        uuids['audio_channels']:b'\x01'
    }
}
print(settings)
state.on_enter('write-settings',Callback(connections.write_characteristics,settings))

def open_connections() :
    Connections.open()
    
def on_add_server() :
    print(voble_servers)
    stop_scanner()
    open_connections()
    
def on_advertising_report(evt) :
    if not scanner_active :
        return
    if connections.is_known(evt) :
        return
    d = advertiser.parse_data(evt.data)
    for adtype in [7,8] :
        obj = d.get(adtype)
        if None == obj :
            continue
        for uuid in obj.uuids :
            if uuid == int.from_bytes(uuids['voble_service'],'little') :
                connections.add(evt)
                if connections.count() == 1 :
                    state.set("connect")
                return
            
def ignore_event(evt) :
    pass

def main_loop(passed=None) :
    debug('main_loop()')
    global stdscr, send_at, counter, failures
    stdscr = passed
    while True :
        bt.process_event()
        timer.process()

if False and args.curses :
    wrapper(main_loop)
else :
    main_loop()
    
bt.api.system.reset(0)
bt.close()
