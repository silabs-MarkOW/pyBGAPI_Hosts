import bgapi
import argparse
import os
import time
import numpy
from curses import wrapper
import advertiser

def get_default_xapi() :
    if None != os.environ.get('DARWIN') :
        XAPI = os.environ.get('DARWINAPI')
        if None != XAPI :
            return XAPI
    GSDK = os.environ.get('GSDK')
    if None == GSDK :
        return None
    return GSDK + '/protocol/bluetooth/api/sl_bt.xapi'

def get_default_uart() :
    return os.environ.get('DARWIN')

parser = argparse.ArgumentParser()
parser.add_argument('--xapi',default=get_default_xapi())
parser.add_argument('-t','--timeout',type=float,default=0)
parser.add_argument('--debug',type=int,default=0)
parser.add_argument('--min-rssi',type=int,default=-128)
parser.add_argument('--interval',type=float,default=10)
parser.add_argument('--uart',default=get_default_uart())
parser.add_argument('--coded-phy',action='store_true')
parser.add_argument('-a','--active',action='store_true')
parser.add_argument('--discover-limited',action='store_true')
parser.add_argument('--discover-generic',action='store_true')
parser.add_argument('--ignore-legacy',action='store_true')
how = parser.add_mutually_exclusive_group(required=True)
how.add_argument('--address')
how.add_argument('--name')
parser.add_argument('--ip')
args = parser.parse_args()

if args.debug :
    print('args:',args)

if None != args.ip :
    connector = bgapi.SocketConnector((args.ip,4901))
else :
    connector = bgapi.SerialConnector(args.uart)
l = bgapi.BGLib(connector,args.xapi)
l.open()

api = None
for i in ['bt','gecko','ble'] :
    if l.__dict__.get(i) :
        api = i

fifo = []

def get_event() :
    if len(fifo) :
        return fifo.pop(0)
    else :
        return l.get_event(timeout=.2)

def clear_events() :
    while True :
        e = l.get_event(timeout=0)
        if None == e :
            if args.debug :
                print('clear-events() %d events in FIFO'%(len(fifo)))
            return
        fifo.append(e)

def reset(dfu) :
    if args.debug :
        print('reset()')
    if 'gecko' == api :
        l.gecko.system.reset(dfu)
    elif 'bt' == api :
        l.bt.system.reset(dfu)

def start_scanner(active) :
    global scanner_active
    if args.debug :
        print('start_scanner()')
    if 'gecko' == api :
        phy = l.gecko.le_gap.PHY_TYPE_PHY_1M
        if args.coded_phy :
            phy = l.gecko.le_gap.PHY_TYPE_PHY_CODED
        discover_mode = l.gecko.le_gap.DISCOVER_MODE_DISCOVER_OBSERVATION
        if args.discover_limited :
            discover_mode = l.gecko.le_gap.DISCOVER_MODE_DISCOVER_LIMITED
        l.gecko.le_gap.set_discovery_extended_scan_response(True)
        l.gecko.le_gap.set_discovery_type(phy,active)
        l.gecko.le_gap.start_discovery(phy,discover_mode)
    elif 'bt' == api :
        if active :
            scan_mode = l.bt.scanner.SCAN_MODE_SCAN_MODE_ACTIVE
        else :
            scan_mode = l.bt.scanner.SCAN_MODE_SCAN_MODE_PASSIVE    
        phy = l.bt.scanner.SCAN_PHY_SCAN_PHY_1M
        if args.coded_phy :
            phy = l.bt.scanner.SCAN_PHY_SCAN_PHY_CODED
        discover_mode = l.bt.scanner.DISCOVER_MODE_DISCOVER_OBSERVATION
        if args.discover_generic :
            discover_mode = l.bt.scanner.DISCOVER_MODE_DISCOVER_GENERIC
        if args.discover_limited :
            discover_mode = l.bt.scanner.DISCOVER_MODE_DISCOVER_LIMITED
        l.bt.scanner.set_parameters(scan_mode,0x10,0x10)
        l.bt.scanner.start(phy,discover_mode)
    else :
        raise RuntimeError()
    scanner_active = True

def stop_scanner() :
    global scanner_active
    if args.debug :
        print('stop_scanner()')
    if 'gecko' == api :
        l.gecko.le_gap.end_procedure()
    elif 'bt' == api :
        l.bt.scanner.stop()
    else :
        raise RuntimeError()
    scanner_active = False    

def connect(address,address_type) :
    if args.debug :
        print('connect(%s,%d)'%(address,address_type))
    interval = int(0.5 + args.interval / 1.25)
    timeout = int((.5 + 2*args.interval)/10) + 10
    print('interval: %.1f ms, timeout: %d ms'%(1.25*interval,10*timeout))
    if 'gecko' == api :
        phy = l.gecko.le_gap.PHY_TYPE_PHY_1M
        if args.coded_phy :
            phy = l.gecko.le_gap.PHY_TYPE_PHY_CODED
        l.gecko.le_gap.set_conn_parameters(interval,interval,0,timeout)
        l.gecko.le_gap.connect(address,address_type,phy)
    elif 'bt' == api :
        phy = l.bt.scanner.SCAN_PHY_SCAN_PHY_1M
        if args.coded_phy :
            phy = l.bt.scanner.SCAN_PHY_SCAN_PHY_CODED
        l.bt.connection.open(address,address_type,phy)
    else :
        raise RuntimeError()

syncs_active = {}
sync_data = {}

def start_sync(adv_sid, address, address_type) :
    if args.debug :
        print('start_sync()')
    tuplet = (adv_sid, address, address_type,)
    if None != syncs_active.get(tuplet) : return
    if 'gecko' == api :
        if None ==  l.gecko.__dict__.get('sync') : return
    restart = False
    sucess = True
    if scanner_active :
        restart = True
        stop_scanner()
        clear_events()
    if 'gecko' == api :
        l.gecko.sync.open(adv_sid, 0, 100, address, address_type)
    elif 'bt' == api :
        try :
            l.bt.sync.open(address, address_type, adv_sid)
        except :
            sucess = False
            pass
    else :
        raise RuntimeError
    if success :
        syncs_active[tuplet] = True
    if restart :
        start_scanner(args.active)
    
observed = {}
advertisements = {}


stdscr = None
lines = 0

def process_report(data,address,address_type) :
    global scanner_active
    if not scanner_active : return
    ad_data = advertiser.parse_data(data)
    #print(ad_data)
    if None != args.name :
        name = ad_data.get(9)
        if None == name :
            return
        #print('"%s"\n"%s" %d'%(name.value.__str__(),args.name.__str__(),name.value == args.name))
        if name.value.find(args.name) < 0 :
            return
    if None != args.address :
        if address.lower() != args.address.lower() :
            return
    stop_scanner()
    connect(address,address_type)
    
print(api)
reset(0)
if args.timeout > 0 :
    timeout = time.time() + args.timeout
else :
    timeout = None

connected = False

def main_loop(passed=None) :
    global stdscr, scanner_active, connected
    scanner_active = False
    stdscr = passed
    while connected or None == timeout or time.time() < timeout :
        try :
            e = get_event()
        except :
            break
        if None == e :
            continue
        if api+'_evt_system_boot' == e :
            start_scanner(args.active)
            scanner_active = True
        elif 'gecko_evt_le_gap_scan_response' == e :
            process_report(e.data,e.address,e.address_type)
        elif 'gecko_evt_le_gap_extended_scan_response' == e :
            process_report(e.data,e.address,e.address_type)
        elif 'bt_evt_scanner_legacy_advertisement_report' == e :
            process_report(e.data,e.address,e.address_type)
        elif 'gecko_evt_le_connection_opened' == e :
            connected = True
            connection = e.connection
        elif'gecko_evt_le_connection_closed' == e :
            connected = False
        else :
            print(e)
    if scanner_active :
        if 'gecko' == api :
            l.gecko.system.reset(0)
            
if False :
    wrapper(main_loop)
    for tuple in observed :
        obj = advertisements[tuple]
        display_final(obj.render(),observed[tuple])
else :
    main_loop()
    
l.close()


print(advertiser.verbosity)
#for metadata in observed :
#    print(observed[metadata])
quit()

if args.timing :
    for metadata in observed :
        print('%s (%s) %s'%(t[0],decode_address_type(t[1]),decode_packet_type(t[2])))
        dump_data(t[3])
        when = numpy.array(observed[t])
        deltas = 1e3*(when[1:]-when[:-1])
        print('  Interval: %d - %d'%(deltas.min(),deltas.max()))
