import sys
import inspect

handlers = {}
verbosity = {}

def set_verbose(adType) :
    verbosity[adType] = True
    
class Flags :
    adType = 0x01
    def __init__(self, arg) :
        self.errors = []
        if bytes == type(arg) :
            if 1 != len(arg) :
                self.errors.append('data too long: "%s"'%(arg.__str__()))
            self.value = arg[0]
        if int == type(arg) :
            self.value = arg
        if (self.value >> 5) != 0 :
            errors.append('reserved bits set {:b}xxxxx'.format(self.value))
    def render(self,verbose=False) :
        rc = 'Flags: 0b{:06b}'.format(self.value)
        if verbose :
            names = ['LE Limited Discoverable Mode',
                     'LE General Discoverable Mode',
                     'BR/EDR Not Supported',
                     'Simultaneous LE and BR/EDR to Same Device Capable (Controller)',
                     'Simultaneous LE and BR/EDR to Same Device Capable (Host)']
            for i in range(5) :
                if (1 << i) & self.value :
                    rc += ' ' + names[i]
                flags >>= 1
        return [rc]
    def generate(self) :
        return bytes([2,1,self.value])

class List_Of_Services :
    def __init__(self,complete,bits,arg) :
        self.complete = complete
        self.bits = bits
        octets = bits >> 3
        count = len(arg) // octets
        self.uuids = []
        for i in range(count) :
            self.uuids.append(int.from_bytes(arg[i*octets:][:octets],'little'))
    def render(self,verbose=False) :
        title = '%somplete List of %d-bit Service Class UUIDs:'%(['C','Inc'][self.complete],self.bits)
        fmt = '%%0%dX'%(self.bits >> 2)
        if verbose :
            s = []
            for uuid in self.uuids :
                name = service_uuid.table.get(uuid)
                if None == name :
                    s.append(fmt%(uuid))
                else :
                    s.append(name)
            return [title] + [s]
        else :
            s = ','.join([fmt%(x) for x in self.uuids])
            return ['%s %s'%(title,s)]

class Incomplete_List_Of_16bit_Services(List_Of_Services) :
    adType = 0x02
    def __init__(self,arg) :
        super().__init__(False,16,arg)
        
class Complete_List_Of_16bit_Services(List_Of_Services) :
    adType = 0x03
    def __init__(self,arg) :
        super().__init__(True,16,arg)

class Incomplete_List_Of_128bit_Services(List_Of_Services) :
    adType = 0x06
    def __init__(self,arg) :
        super().__init__(False,128,arg)
        
class Complete_List_Of_128bit_Services(List_Of_Services) :
    adType = 0x07
    def __init__(self,arg) :
        super().__init__(True,128,arg)

class Local_Name :
    def __init__(self,payload,complete) :
        self.complete = complete
        self.value = payload.decode('utf8')
    def render(self,verbose=True) :
        return ['%s Local Name: "%s"'%(['Shortened','Complete'][self.complete],self.value)]
    
class Shortened_Local_Name(Local_Name) :
    adType = 0x08
    def __init__(self,payload) :
        super().__init__(payload,False)
    
class Complete_Local_Name(Local_Name) :
    adType = 0x09
    def __init__(self,payload) :
        super().__init__(payload,True)

class Tx_Power :
    adType = 0x0a
    def __init__(self,payload) :
        self.value = int.from_bytes(payload,'little',signed=True)
    def render(self,verbose=False) :
        return ['TX Power Level: %d dBm'%(self.value)]

class Matter_Ble_Service_Data :
    name = 'Matter BLE Service Data'
    def __init__(self,payload) :
        self.opcode = payload[0]
        self.discriminator = (payload[2] & 0x0f) << 8 | payload[1]
        self.advertisement_version = payload[2] >> 4
        self.vendor_id = int.from_bytes(payload[3:5],'little')
        self.product_id = int.from_bytes(payload[5:7],'little')
        self.additional_data_flag = payload[7] & 1
    def render(self) :
        l = []
        l.append('    Matter BLE OpCode: %d (%s)'%(self.opcode,['Commisionable','RESERVED value'][self.opcode != 0]))
        l.append('        Discriminator: 0x%03x'%(self.discriminator))
        l.append('Advertisement version: %d'%(self.advertisement_version))
        l.append('             VendorID: 0x%04x'%(self.vendor_id))
        l.append('            ProductID: 0x%04x'%(self.product_id))
        l.append(' Additional Data Flag: %d'%(self.additional_data_flag))
        return l

class Eddystone_UID :
    ref = 'https://github.com/google/eddystone/tree/master/eddystone-uid'
    name = 'Eddystone UID'
    def __init__(self,data=None,ranging_data=None,nid=None,bid=None) :
        self.errors = []
        if bytes == type(data) :
            if 18 != len(data) :
                self.name += ' (errors)'
                self.errors.append("payload length is %d, should be 18"%(len(data)))
            self.frame_type = data[0]
            self.ranging_data = data[1]
            self.nid = data[2:12]
            self.bid = data[12:18]
        elif None != ranging_data or None != nid or None != bid :
            errors = []
            if int != type(ranging_data) :
                errors.append('ranging data is not int')
            if str != type(nid) :
                errors.append('nid is not str')
            elif len(nid) != 10 :
                errors.append('nid is not 10 characters long')
            if int != type(bid) :
                errors.append('bid is not int')
            if len(errors) :
                raise RuntimeError('Errors: %s'%(', '.join(errors)))
            self.ranging_data = ranging_data
            self.nid = nid.encode()
            self.bid = int.to_bytes(bid,6,'big')
    def render(self) :
        nid = self.nid.decode()
        bid = int.from_bytes(self.bid,'big')
        print('bid:',bid)
        rc = ['Ranging Data: %d dBm at 0 m'%(self.ranging_data), 'NID: %s'%(nid), 'BID: 0x%012x'%(bid) ] + self.errors
        return rc
    def generate(self) :
        return bytes([0x15,0x16,0xaa,0xfe,0x00, self.ranging_data]) + self.nid + self.bid

class Eddystone_URL :
    ref = 'https://github.com/google/eddystone/tree/master/eddystone-uid'
    name = 'Eddystone URL'
    def __init__(self,data) :
        if bytes == type(data) :
            self.frame_type = data[0]
            self.tx_power = data[1]
            self.url_scheme = data[2]
            self.encoded_url = data[3:]
    def render(self) :
        url = ['http://www.','https://www.','http://','https://'][self.url_scheme]
        for ch in self.encoded_url :
            if ch < 14 :
                url += ['.com','.org','.edu','.net','.info','.biz','.gov',][ch % 7]
                if ch < 7 :
                    url += '/'
            elif ch > 32 and ch < 127 :
                url += chr(ch)
            else :
                url += '<RFU>'
        rc = ['TX Power: %d dBm at 0 m'%(self.tx_power), 'URL: %s'%(url)]
        return rc

class Eddystone :
    def __init__(self,payload) :
        # https://github.com/google/eddystone/blob/master/protocol-specification.md
        frame_type = payload[0]
        if 0x00 == frame_type :
            self.value = Eddystone_UID(payload)
        elif 0x10 == frame_type :
            self.value = Eddystone_URL(payload)
        elif 0x20 == frame_type :
            self.value = Eddystone_TLM(payload)
        elif 0x30 == frame-type :
            self.value = Eddystone_EID(payload)
        else :
            self.frame_type = frame_type
            self.value = None
            self.name = 'Eddystone (invalid)'
            return
        self.name = self.value.name
    def render(self) :
        if None == self.value :
            return ['Reserved frame type: 0x%02x'%(self.frame_type)]
        return self.value.render()
        
class Service_Data_16 :
    adType = 0x16
    def __init__(self,data) :
        self.uuid = int.from_bytes(data[:2],'little')
        self.payload = data[2:]
        if 0xfff6 == self.uuid :
            self.value = Matter_Ble_Service_Data(self.payload)
        elif 0xfeaa == self.uuid :
            self.value = Eddystone(self.payload)
        else :
            self.value = None
    def render(self,verbose=False) :
        if None == self.value :
            name = ''
        else :
            name = ' (%s)'%(self.value.name)
        l = ['Service Data - 16-bit UUID: %04X%s'%(self.uuid,name)]
        if not verbose :
            return l
        if None == self.value :
            s = ' '.join(['%02x'%(x) for x in self.payload])
            l.append(['data: %s'%(s)])
        else :
            l.append(self.value.render())
        return l

class Manufacturer_Data :
    adType = 0xff
    def __init__(self,data) :
        self.uuid = int.from_bytes(data[:2],'little')
        self.data = data[2:]
    def render(self,verbose=False) :
        s = ' '.join(['%02x'%(x) for x in self.data])
        name = cic.table.get(self.uuid)
        if None == name :
            name = ''
        else :
            name = ' (%s)'%(name)
        rc = ['Manufacturer Data: UUID:0x%04x%s'%(self.uuid,name)]
        if verbose :
            rc.append(['Data: %s'%(s)])
        return rc
    
class Default_Handler :
    adType = -1
    def __init__(self,ad_type,data) :
        self.ad_type = ad_type
        self.data = data
    def render(self,verbose=False) :
        return ['Unhandled AdType:0x{:02x}, data:{:s}'.format(self.ad_type,''.join(['{:02x}'.format(x) for x in self.data]))]

def parse_element(ad_type,data) :
    handler = handlers.get(ad_type)
    if None == handler :
        return data
    else :
        return handler(data)

def parse_data(data) :
    rc = {}
    while len(data) :
        length = data[0]
        if length > len(data[1:]) :
            rc[256] = data
            return rc
        else :
            rc[data[1]] = parse_element(data[1],data[2:1+length])
            data = data[1+length:]
    return rc

if __name__ == '__main__' :
    f = Flags(6)
    print(f.render())
    s = Complete_List_Of_16bit_Services(b'\x01\x02\x03\x04')
    print(s.render())
    n = Complete_Local_Name(b'Test')
    print(n.render())
    tp = Tx_Power(b'\x90')
    print(tp.render())

d = sys.modules[__name__].__dict__
keys = list(d.keys())
for key in keys :
    obj = d[key]
    if inspect.isclass(obj) :
        ad_type = obj.__dict__.get('adType')
        if None != ad_type :
#            print(ad_type)
            handlers[ad_type] = obj

#print(handlers)
