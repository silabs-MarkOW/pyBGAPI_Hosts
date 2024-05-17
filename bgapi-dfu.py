import serial
import argparse
import time

def ignore(msg) :
    pass

def debug(msg) :
    print(msg)
    
parser = argparse.ArgumentParser()
connector = parser.add_mutually_exclusive_group(required=True)
connector.add_argument('--uart',help='connection by UART to NCP target')
connector.add_argument('--ip',help='connection by TCP/IP to NCP target')
parser.add_argument('--baudrate',type=int,default=115200,help='baudrate, must match configuration of NCP')
parser.add_argument('--debug',action='store_true',help='show generally uninteresting info')
parser.add_argument('--no-dfu',action='store_true',help='Only report')
parser.add_argument('--length',type=int,default=0x30,help='DFU payload size')
parser.add_argument('--address',type=int,default=0x0,help='Address, does it really matter?')
parser.add_argument('--gbl',required=True,help='DFU GBL image file')
parser.add_argument('--timeout',type=float,default=1.0,help='Duration to wait for response or event')
args = parser.parse_args()

with open(args.gbl,'rb') as fh :
    image = fh.read()
if len(image) & 3 :
    raise RuntimeError('length of %s in not a multipe of 4 (%d)'%(args.gbl, len(image)))

if None != args.ip :
    raise RuntimeError('IP is not currently supported')

class State :
    def __init__(self, name, debug=ignore) :
        self.name = name
        self.debugcb = debug
        self.debug('initialized')
        self.state = 'initialized'
    def debug(self, msg) :
        self.debugcb('%s.State.%s'%(self.name, msg))
    def set(self, state) :
        self.debug('set: %s -> %s'%(self.state,state))
        self.state =  state
    def es(self,state) : # sadly 'is' is a reserved for Python usage, fortunately Spanish and French have 'es'
        return self.state == state

fh = serial.Serial(args.uart, baudrate=args.baudrate)

class Input :
    def __init__(self, fh) :
        self.fh = fh
        self.state = State('Input',debug=ignore)
        self.state.set('start')
        self.buffer = b''
    def get_bgapi(self,) :
        if self.fh.in_waiting > 0 :
            self.buffer += self.fh.read()
        l = len(self.buffer)
        while len(self.buffer) > 0 :
            #debug('buffer: %s'%(dump_packet(self.buffer)))
            if self.state.es('start') or self.state.es('error') :
                if l < 1 : return None
                if 0xa0 == self.buffer[0] or 0x20 == self.buffer[0] :
                    self.state.set('length')
                else :
                    self.state.set('error')
                    self.buffer = self.buffer[1:] # discard until match 0x20/0xa0
                    continue
            if self.state.es('length') :
                if l < 2 : return None
                self.length = 4+self.buffer[1]
                self.state.set('classId')
            if self.state.es('classId') :
                if l < 3 : return None
                self.state.set('messageId')
            if self.state.es('messageId') :
                if l < 4 : return None
                self.state.set('data')
            if self.state.es('data') :
                if l < self.length :
                    return None
                packet = self.buffer[:self.length]
                self.buffer = self.buffer[self.length:]
                self.state.set('start')
                return packet
            break
        return None
    
def dump_packet(packet) :
    labels = {1:'length',2:'classId',3:'messageId'}
    hex = ['%02x'%(x) for x in list(packet)]
    return '[ '+', '.join(hex)+' ]'

def send_command(name,parameters=None) :
    global timeout,command,command_packet
    command = name
    timeout = time.time() + args.timeout
    if 'dfu-reset-dfu' == name :
        packet = bytes([0x20,1,0,0,1])
    elif 'system-reset-dfu' == name :
        packet = bytes([0x20,1,1,1,1])
    elif 'user-reset-dfu' == name :
        packet = bytes([0x20, 0, 0xff, 2])
    elif 'upload-finish' == name :
        packet = bytes([0x20,0,0,3])
    elif 'flash-set-address' == name :
        address = parameters[0]
        packet = bytes([0x20,4,0,1]) + int.to_bytes(address,4,'little')
    elif 'flash-upload' == name :
        dfu_payload = parameters[0]
        length = len(dfu_payload)
        packet = bytes([0x20,length+1,0,2,length])+dfu_payload
    else :
        raise RuntimeError('command "%s" not handled'%(name))
    command_packet = packet
    fh.write(command_packet)
    state.set('wait-response')

upload_finish_returns = 'unknown'
supported = {}
upload_complete = False
timeout = None
i = Input(fh)
state = State('Global',debug=debug)
state.set('setup-reset-to-dfu')
next_timeout = 'quit'
next_event = None
while True :
    if None != timeout and time.time() > timeout :
        timeout = None
        debug('command %s timed out'%(command))
        if 'upload-finish' == command :
            upload_finish_returns = False
        state.set(next_timeout)
    packet = i.get_bgapi()
    if None != packet :
        if 0x20 == packet[0] : # command response
            if state.es('wait-response') :
                timeout = None
                if 2 != packet[1] or packet[2] != command_packet[2] or packet[3] != command_packet[3] :
                    raise RuntimeError('%s mismatch %s'%(dump_packet(command_packet),dump_packet(packet)))
                result = int.from_bytes(packet[4:6],'little')
                if 0 == result :
                    state.set(next_state)
                else :
                    print('command %s failed: 0x%04x'%(command,result))
                    state.set(next_error)
                if 'upload-finish' == command :
                    upload_finish_returns = True
        if 0xa0 == packet[0] :
            debug('event: %s'%(dump_packet(packet)))
            if 0x00 == packet[2] :
                event = 'dfu'
            elif 0x01 == packet[2] :
                event = 'system'
            else :
                raise RuntimeError('class 0x%02x not handled'%(packet[2]))
            if event == 'dfu' :
                if 0x00 == packet[3] :
                    event += '-boot'
                    bl_version = '%d.%d.%d'%(packet[7],packet[6],packet[4])
                elif 0x01 == packet[3] :
                    event += '-boot-failure'
                    reason = int.from_bytes(packet[4:6],'little')
                else :
                    raise RuntimeError('%s messageId 0x%02x not handled'%(event,packet[3]))
            elif event == 'system' and 0x00 == packet[3] :
                event += '-boot'
            else :
                raise RuntimeError('%s messageId 0x%02x not handled'%(event,packet[3]))
            print('event: %s'%(event))
            if state.es('wait-response') :
                print('command (%s) generates event (%s)'%(command,event))
                if command == 'system-reset-dfu' or command == 'dfu-reset-dfu' or command == 'user-reset-dfu' :
                    if event == 'system-boot' :
                        timeout = None
                        state.set(next_error)
                    if 'dfu-boot' == event :
                        timeout = None
                        state.set(next_state)
            if state.es('wait-response') and 'upload-finish' == command :
                timeout = None
                upload_finish_returns = False
            if None != next_event :
                state.set(next_event)
                next_event = None
                
    if state.es('setup-reset-to-dfu') :
        reset_dfu_methods = ['system-reset-dfu','dfu-reset-dfu','user-reset-dfu']
        test_reset_dfu_methods = ['system-reset-dfu','dfu-reset-dfu']
        next_state = 'reset-to-dfu'
        next_error = 'reset-to-dfu'
        next_timeout = 'reset-to-dfu'
        next_event = 'test-supported-reset-dfu'
        testing_reset_dfu = False
        state.set('reset-to-dfu')
    if state.es('reset-to-dfu') :
        if 0 == len(reset_dfu_methods) :
            print('Unable to reset to DFU')
            state.set('quit')
        else :
            send_command(reset_dfu_methods.pop(0))
    if state.es('test-supported-reset-dfu') :
        if testing_reset_dfu :
            supported[command] = event
        next_state = 'test-supported-reset-dfu'
        next_error = 'test-supported-reset-dfu'
        next_timeout = 'test-supported-reset-dfu'
        if 0 == len(test_reset_dfu_methods) :
            if args.no_dfu :
                state.set('report')
            else :
                state.set('send-flash-set-address')
            testing_reset_dfu = False
        else :
            send_command(test_reset_dfu_methods.pop(0))
            event = None
            testing_reset_dfu = True
    if state.es('send-flash-set-address') :
        next_state = 'upload-dfu'
        next_error = 'quit'
        next_timeout = 'quit'
        offset = 0
        send_command('flash-set-address',(args.address,))
    if state.es('upload-dfu') :
        to_send = image[offset:]
        if len(to_send) > args.length :
            to_send = to_send[:args.length]
        length = len(to_send)
        if 0 == length :
            state.set('upload-finish')
            upload_complete = True
        else :
            send_command('flash-upload',(to_send,))
            offset += length
    if state.es('upload-finish') :
        next_state = 'report'
        next_event = 'report'
        next_timeout = 'report'
        send_command('upload-finish')
    if state.es('report') :
        print('Bootloader version: %s'%(bl_version))
        print('upload-finish returns: %s'%(upload_finish_returns.__str__()))
        print('Reset to DFU commands:')
        for command in supported :
            if None == supported[command] :
              print('  %s: unsupported'%(command))
            else :
              print('  %s: -> %s'%(command,supported[command]))
        state.set('quit')
    if state.es('quit') :
        break

