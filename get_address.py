import argparse
from machine import Callback, Timer, State
from bt import BT
import os

def debug(message) :
    if args.debug :
        print(message)

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
application = parser.add_mutually_exclusive_group()
application.add_argument('--clear',action='store_true',help='reset to factory address')
application.add_argument('--address',help='set device address')
args = parser.parse_args()

if args.debug :
    print('args:',args)

def debug(message) :
    if args.debug :
        print(message)

bt = BT(args.xapi, args.ip, args.uart, args.baud, debug=debug)

def reset() :
    if 'bt' == bt.flavor :
        bt.api.system.reset(0)
    elif 'gecko' == bt.flavor :
        bt.api.system.reset(0)
    else :
        raise RuntimeError

def get_address() :
    if 'bt' == bt.flavor :
        resp = bt.api.system.get_identity_address()
    elif 'gecko' == bt.flavor :
        resp = bt.api.system.get_bt_address()
    else :
        raise RuntimeError
    return resp.address

def set_address(address) :
    if 'bt' == bt.flavor :
        resp = bt.api.system.set_identity_address(address)
    elif 'gecko' == bt.flavor :
        resp = bt.api.system.set_bt_address(address)
    else :
        raise RuntimeError
    reset()
    
state = State('Application')
    
def on_boot(evt) :
    state.set('boot')
    if args.clear :
        set_address('00:00:00:00:00:00')
    elif None != args.address :
        set_address(args.address)
    else :
        print(get_address())
    state.set('quit')

bt.on_event('system-boot',on_boot)

tm = Timer()
reset()
def main_loop(passed=None) :
    print('main')
    global stdscr, send_at, counter, failures
    stdscr = passed
    while not state.est('quit') :
        bt.process_event()
        tm.process()

if False and args.curses :
    wrapper(main_loop)
else :
    main_loop()
    
bt.api.system.reset(0)
bt.close()
