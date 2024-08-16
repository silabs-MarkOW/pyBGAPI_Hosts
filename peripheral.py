import bgapi
import argparse
import os
from bt import BT
import xml.etree.ElementTree as ET
from machine import State

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
parser.add_argument('--baud',type=int,default=115200,help='baudrate, must match configuration of NCP')
parser.add_argument('--debug',action='store_true',help='show generally uninteresting info')
parser.add_argument('--interval',type=float,default=100e-3,help='Advertising interval')
parser.add_argument('--limited',action='store_true',help='Set limited advertiser flag')
parser.add_argument('--general',action='store_true',help='Set general advertiser flag')
parser.add_argument('--connectable',action='store_true',help='Advertisement is connectable')
parser.add_argument('--scannable',action='store_true',help='Advertisement is scannable')
parser.add_argument('--extended',action='store_true',help='Advertisement is scannable')
parser.add_argument('--name',help='Set Local Name')
args = parser.parse_args()

if args.debug :
    print('args:',args)

if args.extended and args.connectable and args.scannable :
    raise RuntimeError('Extended advertisement may not be both scannable and connectable')

def debug(message) :
    if args.debug :
        print(message)

def on_boot(evt) :
    global cccd, advertising_handle
    cccd = {}
    advertising_handle = None
    state.set('boot')
    start_advertising()

def start_advertising() :
    debug('start_advertising')
    global advertising_handle
    if None == advertising_handle :
        advertising_handle = bt.api.advertiser.create_set().handle
        flags = 4 # BR/EDR not supported
        if args.limited :
            flags |= 1
        if args.general :
            flags |= 2
        flags = bytes([2,1,flags])
        payload = flags
        if None != args.name :
            name = args.name.encode()
            payload += bytes([1+len(name),9])+name
        if args.extended :
            flags = 0
            bt.api.extended_advertiser.set_data(
                advertising_handle,
                payload)
            if args.connectable :
                if args.scannable :
                    mode = bt.api.extended_advertiser.CONNECTION_MODE_CONNECTABLE
                else :
                    mode = bt.api.extended_advertiser.CONNECTION_MODE_NON_SCANNABLE
            else :
                if args.scannable :
                    mode = bt.api.extended_advertiser.CONNECTION_MODE_SCANNABLE
                else :
                    mode = bt.api.extended_advertiser.CONNECTION_MODE_NON_CONNECTABLE
            bt.api.extended_advertiser.start(advertising_handle, mode, flags)
            debug('started extended advertising')
        else :
            bt.api.legacy_advertiser.set_data(
                advertising_handle,
                0,
                payload)
            if args.connectable :
                mode = bt.api.legacy_advertiser.CONNECTION_MODE_CONNECTABLE
            else :
                if args.scannable :
                    mode = bt.api.legacy_advertiser.CONNECTION_MODE_SCANNABLE
                else :
                    mode = bt.api.legacy_advertiser.CONNECTION_MODE_NON_CONNECTABLE
            bt.api.legacy_advertiser.start(advertising_handle, mode)
            debug('started legacy advertising')
    
    state.set('advertising')
    
def ignore_event(evt) :
    pass

bt = BT(args.xapi, args.ip, args.uart, args.baud, debug=debug)
bt.api.system.reset(0)
bt.on_event('system-boot',on_boot)
state = State('Application',debug=debug)

def main_loop(passed=None) :
    print('main')
    global stdscr, send_at, counter, failures
    stdscr = passed
    while True :
        bt.process_event()

if False and args.curses :
    wrapper(main_loop)
else :
    main_loop()
    
bt.api.system.reset(0)
bt.close()
