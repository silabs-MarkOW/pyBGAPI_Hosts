import bgapi

def ignore(msg) :
    pass

class BT :
    def __init__(self, xapi, ip=None, uart=None, baudrate=None, debug=None) :
        if None != ip :
            connector = bgapi.SocketConnector((ip,4901))
        else :
            if None != baudrate :
                connector = bgapi.SerialConnector(uart,baudrate)
            else :
                connector = bgapi.SerialConnector(uart)
        self.bglib = bgapi.BGLib(connector,xapi)
        self.bglib.open()
        self.api = self.bglib.bt
        self.handlers = {}
        self.connection_handlers = {}
        if None == debug :
            self.debug = ignore
        else :
            self.debug = debug
            debug('BT:debugging enabled')
    def close(self) :
        self.bglib.close()
    def process_event(self) :
        evt = self.bglib.get_event()
        if None == evt :
            return
        self.debug('BT.process_event(%s)'%(evt.__str__()[:60]))
        name = evt.__str__().split('_evt_')[1].split('(')[0].replace('_','-')
        connection = evt.__dict__.get('connection')
        handlers = None
        if None != connection :
            handlers = self.connection_handlers.get(connection)
        if None == handlers :
            handlers = self.handlers
        handler = handlers.get(name)
        if None == handler :
            self.debug('Unhandled event %s'%(name))
            return
        handler(evt)
    def on_event(self,name,handler) :
        self.handlers[name] = handler
    def on_connection_event(self,connection,name,handler) :
        handlers = self.connection_handlers.get(connection)
        if None == handlers :
            handlers = {}
        handlers[name] = handler
        self.connection_handlers[connection] = handlers
