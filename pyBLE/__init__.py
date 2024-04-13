def uuid_to_bytes(uuid) :
    """
Convert ASCII representation of UUID into bytes.

uuid_to_bytes(uuid)

example format of uuidstr:
  'F7BF3564-FB6D-4E53-88A4-5E37E0326063'
  'F7BF3564FB6D4E5388A45E37E0326063'

returns byte string as used in pyBGAPI
"""
    if type(uuid) == str :
        parts = uuid.split('-')
        pc = len(parts)
        if pc > 1 :
            if pc != 5 :
                raise RuntimeError('expecting 5 blocks separated by "-", got %d (%s)'%(pc,uuid))
            for i in range(5) :
                expect = [8,4,4,4,12]
                if len(parts[i]) != expect[i] :
                    raise RuntimeError('expecting length %d, (%s)'%(expect[i],'-'.join(parts[:i])+'-->'+parts[i]+'<--'+'-'.join(parts[i+1:])))
            uuid = ''.join(parts)
        if 32 != len(uuid) :
            raise RuntimeError('length of uuid string should be 32')
        uuid = int(uuid,16)
        return int.to_bytes(uuid,16,'little')
    elif int == type(uuid) :
        if uuid < 0x10000 :
            return int.to_bytes(uuid,2,'little')
    raise RuntimeError('type or length of uuid not handled')


                                       
