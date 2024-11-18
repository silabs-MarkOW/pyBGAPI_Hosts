import bgapi
from machine import State, Callback

timer = None
    
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
        self.flavor = None
        for flavor in ['bt','gecko','ble'] :
            if self.bglib.__dict__.get(flavor) :
                self.flavor = flavor
        if 'bt' == self.flavor :
            self.api = self.bglib.bt
        elif 'gecko' == self.flavor :
            self.api = self.bglib.gecko
            print('Warning: this flavor is untested')
        else :
            raise RuntimeError('API flavor "%s" is not currently supported'%(self.flavor))
        self.handlers = {}
        self.connection_handlers = {}
        if None == debug :
            self.debug = ignore
        else :
            self.debug = debug
            debug('BT:debugging enabled')
    def register_timer(self,cls) :
        global timer
        timer = cls
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

class Peripheral :
    class Characteristic :
        def __init__(self, service, evt) :
            self.handle = evt.characteristic
            self.uuid = evt.uuid
            self.properties = evt.properties
    class Service :
        def __init__(self,evt) :
            self.handle = evt.service
            self.uuid = evt.uuid
            self.characteristics = {}
    def __init__(self, bt, evt, interval=100, latency=0, timeout=5, debug=None) :
        '''
timeout is number of connection events which can be missed
'''
        self.bt = bt
        self.address = evt.address
        self.address_type = evt.address_type
        self.connection = None
        self.state = State('peripheral-%s'%(self.address),debug=debug)
        self.state.set('closed')
        self.mtu = 23;
        self.services = {}
        self.interval = interval
        self.latency = latency
        self.timeout = timeout
        self.debug = debug
    def on_open(self,callback,parameter=None) :
        self.callbacks['open'] = Callback(callback,parameter)
    def open(self, connection_timeout) :
        self.debug("Peripheral.open(%d)"%(connection_timeout))
        ticks = int(self.interval/1.25)
        timeout = int((1+self.latency)*self.interval*self.timeout)/10
        self.debug('attempt set_default_parameters(ticks:%d,ticks,latency:%d,timeout:%d,0,0xffff)'%(ticks,self.latency,timeout))
        self.bt.api.connection.set_default_parameters(ticks,ticks,self.latency,timeout,0,0xffff)
        self.connection = self.bt.api.connection.open(self.address,self.address_type,1).connection
        self.bt.on_connection_event(self.connection,'connection-opened',self.callback_opened)
        self.timeout = timer.oneshot(connection_timeout, Callback(self.callback_connection_timeout))
        self.state.set('opening')
    def on_any(self,callback) :
        self.state.on_enter_any(callback)
    def callback_opened(self,evt) :
        self.timeout.cancel()
        self.bt.on_connection_event(self.connection,'connection-closed',self.callback_closed_unexpectedly)
        self.state.set('open')
    def callback_closed_unexpectedly(self,evt) :
        if self.state.est('opening') :
            self.timeout.cancel()
        self.state.set('closed')
    def callback_connection_timeout(self) :
        self.bt.api.connection_close(self.conection)
        on_connection_event(self.connection,self.callback_connection_closed)
        self.state.set('closing-timeout')
        self.state.on_enter('closed',Callback(self.on_error_opening))
    def on_error_opening(self,context) :
        context.cancel()
        self.error_context = context
        self.state.set('error')
    def callback_connection_close(self,evt) :
        self.state.set('closed')
    def add_service(self,evt) :
        self.debug('add_service(%s)'%(evt.uuid.__str__()))
        self.services[evt.uuid] = self.Service(evt)
    def add_characteristic(self,evt) :
        self.current_service.characteristics[evt.uuid] = self.Characteristic(self.current_service,evt)
        #print(self.current_service.characteristics)
    def discover_internal(self, evt) :
        if self.state.est('open') :
            self.state.set('discovering-services')
            self.bt.on_connection_event(self.connection,'gatt-procedure-completed',self.discover_internal)
            self.bt.on_connection_event(self.connection,'gatt-service',self.add_service)
            self.bt.on_connection_event(self.connection,'gatt-characteristic',self.add_characteristic)
            self.bt.api.gatt.discover_primary_services(self.connection)
            return
        if self.state.est('discovering-services') :
            self.state.set('discovering-characteristics')
            self.services_list = [self.services[x] for x in self.services]
            print('Services_list:',self.services_list)
        if self.state.est('discovering-characteristics') :
            if 0 == len(self.services_list) :
                self.state.set('discovery-complete')
                return
            self.current_service = self.services_list.pop(0)
            self.bt.api.gatt.discover_characteristics(self.connection,self.current_service.handle)
            return            
    def discover(self) :
        self.discover_internal(None)
        print(self.state.current)
    def close(self) :
        self.state.set('closing')
        self.bt.api.connection.close(self.connection)
    def run_internal(self,evt) :
        if 'bt_evt_gatt_procedure_completed' == evt :
            if self.state.est('setting-sample-rate') :
                self.state.set('subscribing')
                self.bt.api.gatt.set_characteristic_notification(self.connection,self.sample_data.handle,1)
            elif self.state.est('subscribing') :
                bt.on_connection_event(self.connection,'gatt-characteristic-value',process_data)
                self.state.set('running')
    def run(self,parameter=None) :
        print('Services:',self.services)
        service = self.services.get(uuids['pressure_service'])
        if None == service :
            raise RuntimeError
        sample_rate = service.characteristics.get(uuids['sample_rate'])
        if None == sample_rate :
            print('Characteristics:',service.characteristics)
            raise RuntimeError
        self.sample_data = service.characteristics.get(uuids['sample_data'])
        if None == self.sample_data :
            print('Characteristics:',service.characteristics)
            raise RuntimeError
        self.state.set('setting-sample-rate')
        bt.on_connection_event(self.connection,'gatt-procedure-completed',self.run_internal)
        self.bt.api.gatt.write_characteristic_value(self.connection,sample_rate.handle,int.to_bytes(args.sample_rate,1,'little'))
    def internal_write(self,evt) :
        state = 'writing-characteristics'
        if 'bt_evt_gatt_procedure_completed' == evt :
            pass
        else :
            if None != evt or self.state.est(state) :
                raise RuntimeError(evt)
            self.state.set(state)
        if not self.state.est(state) :
            raise RuntimeError(evt)
        if None != evt and 0 != evt.result :
            self.state.set('error')
            return
        if 0 == len(self.write_settings) :
            self.state.set('writing-complete')
            return
        spair = self.write_settings.popitem()
        cpair = spair[1].popitem()
        if len(spair[1]) :
            self.write_settings[spair[0]] = spair[1]
        handle = self.services[spair[0]].characteristics[cpair[0]].handle
        self.debug('gatt.write_characteristic_value(self.connection:%d,handle:%d,cpair[1]:%s)'%(self.connection,handle,cpair[1]))
        self.bt.api.gatt.write_characteristic_value(self.connection,handle,cpair[1])
    def write_characteristics(self,settings) :
        self.write_settings = settings.copy()
        self.bt.on_connection_event(self.connection,'gatt-procedure-completed',self.internal_write)
        self.internal_write(None);

class Connections :
    def __init__(self,bt,debug=ignore) :
        self.bt = bt
        self.peripherals = []
        self.state = State('Connections',debug=debug)
        self.debug = debug
    def is_known(self,evt) :
        for p in self.peripherals :
            if p.address == evt.address and p.address_type == evt.address_type :
                return True
        return False
    def add(self,evt) :
        p = Peripheral(self.bt,evt,debug=self.debug)
        p.on_any(Callback(self.on_peripheral_state))
        self.peripherals.append(p)
    def all_est(self,state) :
        for p in self.peripherals :
            if not p.state.est(state) :
                return False
        return True
    def on_peripheral_state(self,context) :
        self.debug('Connection:on_peripheral_state(context.transition.enter:%s)'%(context.transition.enter))
        state = context.transition.enter
        if 'open' == state :
            self.i_open()
        if 'error' == state :
            self.on_error(context)
        elif self.all_est(state) :
            self.state.set(state)
    def count(self) :
        return len(self.peripherals)
    def open(self,context) :
        self.state.set('opening')
        self.index = 0
        self.i_open()
    def i_open(self) :
        self.debug("Connections.open()")
        if not self.state.est('opening') :
            raise RuntimeError
        if len(self.peripherals) == self.index :
            return
        p = self.peripherals[self.index]
        self.index += 1
        p.open(self.connection_timeout)
    def discover(self,context=None) :
        self.state.set('discovering')
        for p in self.peripherals :
            p.discover()
    def close(self,previous_state=None,next_state=None) :
        self.state.set('closing')
        for p in self.peripherals :
            p.on_event('closed',self.callback_closed)
            p.close()
    def callback_closed(self) :
        print('Connections.callback_closed')
        for p in self.peripherals :
            print(p.state.name,p.state.current)
            if not p.state.est('closed') :
                return
        self.state.set('closed')
    def callback_error(self) :
        self.process_callbacks('error')
    def run(self,context=None) :
        for p in self.peripherals :
            p.run()
    def write_characteristics(self,settings,context=None) :
        self.debug('write_characteristics(settings:%s)'%(settings))
        for p in self.peripherals :
            p.write_characteristics(settings.copy())
    def set_connection_timeout(self,timeout) :
        self.connection_timeout = timeout
