import time
import inspect

def ignore(msg) :
    pass

timer = None

def register_timer(use_timer) :
    global timer
    if type(use_timer) != Timer :
        raise RuntimeError
    timer = use_timer
    
class Callback :
    def __init__(self,callback,parameter=None,oneshot=True) :
        self.callback = callback
        self.parameter = parameter
        self.oneshot = oneshot
        self.context = False
        self.owner = None
        self.debug= ignore
    def add(self,context) :
        if State.Transition == type(context) :
            self.transition = context
            self.context = True
        else :
            raise RuntimeError(type(context))
    def run(self) :
        if None != self.parameter :
            if self.context :
                self.debug('calling %s(parameter,self)'%(self.callback.__name__))
                self.callback(self.parameter,context=self)
            else :
                self.debug('calling %s(parameter)'%(self.callback.__name__))
                self.callback(self.parameter)
        else :
            if self.context :
                self.debug('calling %s(self)'%(self.callback.__name__))
                self.callback(context=self)
            else :
                self.debug('calling %s()'%(self.callback.__name__))
                self.callback()
    def cancel(self) :
        if Timer == type(self.owner) :
            self.owner.cancel()
        else :
            self.owner.cancel(self)
    def __str__(self) :
        return inspect.getsource(self.callback).split('\n')[0]
        
class Timer :
    class Timer :
        def __init__(self,parent,when,callback,repeat) :
            self.when = when
            self.callback = callback
            callback.owner = self
            self.parent = parent
            self.repeat = repeat
        def cancel(self) :
            self.parent.cancel(self.when,self)
    def __init__(self,debug=ignore) :
        self.timeouts = []
        self.owners = {}
        self.debug = debug
    def periodic(self,timeout,callback) :
        return self.add(timeout,callback,True)
    def oneshot(self,timeout,callback) :
        return self.add(timeout,callback,False)
    def add(self,timeout,callback,periodic) :
        if Callback != type(callback) :
            raise TypeError('callback is not an instance of Callback (%s)'%(type(callback)))
        if type(timeout) != float and type(timeout) != int :
            raise TypeError('timeout is not number (%s)'%(type(timeout)))
        if periodic and timeout <= 0 :
            raise ValueError('periodic timer with non-positive timeout loops infinitely')
        when = time.time() + timeout
        callback.debug = self.debug
        l = self.owners.get(when)
        if None == l :
            l = []
        if periodic :
            result = self.Timer(self,when,callback,timeout)
        else :
            result = self.Timer(self,when,callback,0)
        l.append(result)
        self.add_internal(when,l)
        self.debug(self.__str__())
        return result
    def add_internal(self,when,owners) :
        self.owners[when] = owners
        self.reindex()
    def reindex(self) :
        self.timeouts = list(self.owners.keys())
        self.timeouts.sort()
    def process(self) :
        while len(self.timeouts) and self.timeouts[0] < time.time() :
            when = self.timeouts.pop(0)
            owners = self.owners.get(when)
            if None == owners :
                raise RuntimeError
            self.owners.pop(when)
            owner = owners.pop(0)
            if len(owners) :
                self.add_internal(when,owners)
            if owner.repeat > 0 :
                owner.when += owner.repeat
                owners = self.owners.get(owner.when)
                if None == owners :
                    owners = []
                self.add_internal(owner.when,owners+[owner])
            owner.callback.run()
    def cancel(self,when,owner) :
        l = self.owners.pop(when) 
        index = l.index(owner)
        l.pop(index)
        if len(l) :
            self.add_internal(when,l)
        else :
            self.reindex()
    def __str_element__(self,e,now) :
        dt = e.when - now
        if e.repeat > 0 :
            return '%.1fs+n(%.1fs)'%(dt,e.repeat)
        return '%.1fs'%(dt)
    def __str__(self) :
        now = time.time()
        return 'Timer: [%s]'%(','.join(['%.1fs(%d)'%(when-now,len(self.owners[when])) for when in self.timeouts]))
        
class State :
    class Transition :
        def __init__(self,parent) :
            self.exit = parent.previous
            self.enter = parent.next
        def __str__(self) :
            return 'Transition: %s -> %s'%(self.exit,self.enter)
    def __init__(self,name,debug=ignore) :
        self.name = name
        self.debug = debug
        self.current = "init"
        self.previous = None
        self.next = None
        self.callback_enter = {}
        self.callback_exit = {}
        self.callback_any = []
        self.lock = False
    def est(self,state) :
        return self.current == state
    def add_callback(self,d,state,callback) :
        if dict != type(d) :
            raise ValueError
        if str != type(state) :
            raise ValueError
        if Callback != type(callback) :
            raise ValueError
        callback.debug = self.debug
        l = d.get(state)
        if None == l :
            l = []
        l.append(callback)
        d[state] = l
        self.debug('add_callback: %s'%(d))
    def on_enter(self,state,callback) :
        self.debug('State[%s].on_enter(%s,%s)'%(self.name,state,callback))
        self.add_callback(self.callback_enter,state,callback)
    def on_exit(self,state,callback) :
        self.debug('State[%s].on_exit(%s,%s)'%(self.name,state,callback))
        self.add_callback(self.callback_exit,state,callback)
    def on_enter_any(self,callback) :
        self.callback_any.append(callback)
    def cancel(self,callback) :
        if Callback != type(callback) :
            raise RuntimeError(type(callback))
        try :
            index = self.callbacks_any.index(callback)
            self.callback_any.pop(index)
            return
        except ValueError :
            pass
        for d in [ self.callback_enter, self.callback_exit ] :
            for key in d :
                l = d[key]
                try :
                    index = l.index(callback)
                    l.pop(index)
                    return
                except ValueError :
                    pass
        raise RuntimeError("can't find self to cancel")
    def get_list(self,d,state) :
        #self.debug('get-list(%s,%s)'%(d,state))
        l = d.get(state)
        if None == l :
            return []
        return l
    def set(self,next,context=None) :
        prefix = 'State[%s].set(%s)'%(self.name,next)
        if self.est(next) :
            #raise RuntimeError('%s: already in state %s'%(prefix,next))
            pass
        if self.lock :
            raise RuntimeError("Exit callback may not modify state")
        self.lock = True
        self.previous = self.current
        self.next = next
        self.current = None
        self.debug("%s: %s -> %s"%(prefix,self.previous,self.next))
        #self.debug('%s: callback_enter: %s'%(prefix,self.callback_enter))
        #self.debug('%s: callback_exit: %s'%(prefix,self.callback_exit))
        exit_callbacks = self.get_list(self.callback_exit,self.previous)
        enter_callbacks = self.get_list(self.callback_enter,self.next)
        #self.debug('%s: enter_callbacks: %s'%(prefix,enter_callbacks))
        #self.debug('%s: exit_callbacks: %s'%(prefix,exit_callbacks))
        for callback in self.callback_any :
            self.debug('%s:callback_any:%s'%(prefix,callback))
            callback.add(self.Transition(self))
            timer.oneshot(0,callback)
        for callback in exit_callbacks :
            self.debug('%s: calling exit callback %s'%(prefix,callback))
            callback.add(self.Transition(self))
            callback.run()
            self.debug('%s: after exit call'%(prefix))
        for callback in enter_callbacks :
            callback.add(self.Transition(self))
            timer.oneshot(0,callback)
            self.debug('%s:queued enter callback %s'%(prefix,callback))
        self.current = next
        self.lock = False

