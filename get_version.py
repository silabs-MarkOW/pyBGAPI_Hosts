import argparse
from machine import Callback, Timer, State
from bt import BT
import os

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
args = parser.parse_args()

if args.debug :
    print('args:',args)

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

bt = BT(args.xapi, args.ip, args.uart, args.baud, debug=debug)
bt.api.system.reset(0)

state = State('Application')
    
def on_boot(evt) :
    state.set('boot')
    print(evt)
    state.set('quit')

bt.on_event('system-boot',on_boot)

tm = Timer()

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
