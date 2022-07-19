import asyncio
import websockets
import json
import uuid
import traceback
import websocket
import zlib
import time
import math
import _thread as thread
import asyncio
import copy

url = 'ws://broadcastlv.chat.bilibili.com:2244/sub'
danmaku_id = ""
room_id = 23921483
# room_id = 7734200
port = 8001
config = {}

tracking_params = {}

danmaku_cmd2param = {}
authenticationToken = ""


class VTSParameter:

    def __init__(self, name, scalar=1, delta=0.1, value=0, vrange=(-1, 1), added_by='N/A', param_type='ModelParam'):
        self.name = name
        self.scalar = scalar
        self.delta = delta
        self.value = value
        self.vrange = vrange
        self.vchange = False
        self.target = value
        self.param_type = param_type
        self.added_by = added_by
        self.changed = True
        self.checking_content = None
    def print_to_str(self):
        return '''{}: [{},{}]'''.format(
            self.name, int(self.vrange[0]), int(self.vrange[1])
        )

    def register_checking_content(self, content):
        self.checking_content = content

    def teardown(self):
        self.changed = False

    def astype(self, value):
        return float(value)

    def clip_value(self):
        if self.vrange is None:
            return

        if self.value < self.vrange[0]:
            self.value = self.vrange[0]
        elif self.value > self.vrange[1]:
            self.value = self.vrange[1]

    def clip_target(self):
        if self.vrange is None:
            return

        if self.target < self.vrange[0]:
            self.target = self.vrange[0]
        elif self.target > self.vrange[1]:
            self.target = self.vrange[1]

    def increase(self):
        self.target = self.target + self.delta * self.scalar
        self.clip_target()
        self.vchange = True

    def decrease(self):
        self.target = self.target - self.delta * self.scalar
        self.clip_target()
        self.vchange = True

    def reset_vchange(self):
        self.vchange = False

    def check_reach_target(self):
        return abs(self.value - self.target) < 1e-2

    def check_before_update_true(self, target):
        if self.checking_content is None or target != self.checking_content['set_to']:
            return True
        for param_name, param_value in self.checking_content['on_condition'].items():
            if param_name in tracking_params.keys() and (tracking_params[param_name].target != param_value or tracking_params[param_name].value != param_value):
                return False
        return True

    def update(self, T):
        if not self.check_reach_target():
            self.changed = True
            self.value = self.target
        else:
            self.changed = False

    def set_target(self, value):
        print('''set {} to {}'''.format(self.name, value))
        if not self.check_before_update_true(value):
            return
        self.target = value
        print('''set {} to {} done'''.format(self.name, value))

    def set_vinit_p(self):
        pass

    def set_vinit_n(self):
        pass

class ExpressionParam(VTSParameter):
    def __init__(self, name, value, file):
        super(ExpressionParam, self).__init__(name, value=value, param_type='ExpressionParam')
        self.file = file

    def check_reach_target(self):
        return self.value == self.target

    def astype(self, value):
        # return bool(value)
        return value == 'True' or value == '1'

    def print_to_str(self):
        return '''{}: 0/1'''.format(self.name)

class VTSEyeOpenParameter(VTSParameter):
    def __init__(self, name, scalar, delta, value, vrange):
        super(VTSEyeOpenParameter, self).__init__(name, scalar, delta, value, vrange)
        self.steps = [0, 0.7, 0.8, 0.83, 0.87, 0.9, 1]
        self.v_index = len(self.steps) - 1


    def increase(self):
        self.v_index = self.v_index + 1
        if self.v_index >= len(self.steps):
            self.v_index = len(self.steps) - 1
        self.value = self.steps[self.v_index]


    def decrease(self):
        self.v_index = self.v_index - 1
        if self.v_index < 0:
            self.v_index = 0
        self.value = self.steps[self.v_index]

    def update(self, T):
        pass

class VTSSpringParameter(VTSParameter):
    def __init__(self, name, scalar, delta, value, vrange, m, mu, k, vdelta, vorange):
        # super(name, scalar, delta, value, vrange)
        super(VTSSpringParameter, self).__init__(name, scalar, delta, value, vrange)
        self.m = m
        self.mu = mu
        self.v = 0
        self.k = k
        self.vdelta = vdelta
        self.vorange = vorange

    # def update(self, T):
    #     EPS = 1e-3
    #     F = (self.target - self.value) * self.k
    #     # a = F / self.m
    #     f = -self.v * self.mu
    #
    #     a = (f + F) / self.m
    #     self.v = self.v + a * T
    #     self.value = self.value + T * self.v
    #
    #     if self.vrange is not None:
    #         if self.value < self.vrange[0]:
    #             self.value = self.vrange[0]
    #             self.v = -self.v
    #         elif self.value > self.vrange[1]:
    #             self.value = self.vrange[1]
    #             self.v = -self.v

    def set_vinit_p(self):
        self.v = self.v + self.vdelta

    def set_vinit_n(self):
        self.v = self.v - self.vdelta


class VTSTailParameter(VTSSpringParameter):
    def update(self, T):
        EPS = 1e-3
        F = (self.target - self.value) * self.k
        # a = F / self.m
        f = -self.v * self.mu

        a = (f + F) / self.m
        self.v = self.v + a * T
        self.value = self.value + T * self.v

        if self.v < self.vorange[0]:
            self.v = self.vorange[0]
        if self.v > self.vorange[1]:
            self.v = self.vorangen[1]

        if self.value < self.vrange[0]:
            self.value = self.vrange[0]
            self.v = -self.v
        elif self.value > self.vrange[1]:
            self.value = self.vrange[1]
            self.v = -self.v

class VTSMovementParameters(VTSSpringParameter):

    def __init__(self, name, scalar, delta, value, vrange, m, mu, k, vdelta, vorange):
        # super(name, scalar, delta, value, vrange)
        super(VTSMovementParameters, self).__init__(name, scalar, delta, value, vrange, m, mu, k, vdelta, vorange)
        self.param_type = 'PositionParam'

class VTSRotationParameters(VTSMovementParameters):

    # pass
    def update(self, T):
        super(VTSRotationParameters, self).update(T)
        self.value = self.value % 360


# class VTSTailParameter(VTSParameter):


def clip_params(value, vrange):
    if value < vrange[0]:
        value = vrange[0]
    elif value > vrange[1]:
        value = vrange[1]
    return value

class Message:

    def __init__(self, pkg_length=0, header_length=16, proto_version=0, operation=2, seq_id=1, body=None):
        self.pkg_length = pkg_length
        self.header_length = header_length
        self.proto_version = proto_version
        self.operation = operation
        self.seq_id = seq_id
        self.body = body

    def encode(self):
        header = bytearray(16)
        header[4:6] = int(16).to_bytes(2, 'big')
        header[6:8] = int(self.proto_version).to_bytes(2, 'big')
        header[8:12] = int(self.operation).to_bytes(4, 'big')
        header[12:16] = int(1).to_bytes(4, 'big')

        b_body = b''

        if self.operation == 2:
            b_body = b''
        elif self.proto_version == 0 and self.operation == 7:
            s_body = json.dumps(self.body)
            b_body = s_body.encode('utf-8')

        pkg = header + b_body
        pkg[0:4] = int(len(pkg)).to_bytes(4, 'big')
        return pkg


def bili_decode_compressed(pkg):
    # header_length = int.from_bytes(pkg[4:6], 'big')
    # proto_version = int.from_bytes(pkg[6:8], 'big')
    # operation = int.from_bytes(pkg[8:12], 'big')
    # seq_id = int.from_bytes(pkg[12:16], 'big')
    # body = pkg[16:]
    pkgs = []
    offset = 0
    L = len(pkg)
    while(offset < L):
        pkg_length = int.from_bytes(pkg[offset: offset+4], 'big')
        pkgs.append(bili_decode(pkg[offset: offset+pkg_length]))
        offset = offset + pkg_length
    return pkgs

def bili_decode(pkg: bytearray):
    pkg_length = int.from_bytes(pkg[0:4], 'big')
    header_length = int.from_bytes(pkg[4:6], 'big')
    proto_version = int.from_bytes(pkg[6:8], 'big')
    operation = int.from_bytes(pkg[8:12], 'big')
    seq_id = int.from_bytes(pkg[12:16], 'big')
    body = pkg[16:]

    # print('operation: ', operation, 'proto: ', proto_version)
    if operation == 3:
        body = int.from_bytes(body[0: 4], 'big')
        print('room: ', body)

    if proto_version == 0:
        body = json.loads(body.decode('utf-8'))
    elif proto_version == 1:
        body = int.from_bytes(body[16: 20], 'big')
    # else:
    #     raise Exception('protocal not supported')
    elif proto_version == 2:
        body = zlib.decompress(body)
        # return bili_decode(body)
        return bili_decode_compressed(body)
    elif proto_version == 4:
        raise Exception('protocal not supported')

    return Message(pkg_length, header_length, proto_version, operation, seq_id, body)

def bili_heart():
    msg = Message()
    msg_send = msg.encode()
    return msg_send

def bili_enter_room():
    msg = Message(
        proto_version=0,
        operation=7,
        body={
            'roomid': room_id,
        }
    )
    msg_send = msg.encode()
    return msg_send



def msg_wrapper(messageType, data=None, apiName='VTubeStudioPublicAPI', apiVersion='1.0', requestID=None):
    req = {
        'apiName':  apiName,
        'apiVersion': apiVersion,
        'requestID': requestID if requestID is not None else str(uuid.uuid4()),
        'messageType': messageType,
    }
    if data is not None:
        req['data'] = data
    return req

async def get_auth_session(ws):
    auth_message = msg_wrapper(
        'AuthenticationRequest',
        {
            'pluginName': 'playmodel',
            'pluginDeveloper': 'Tenya_Channel',
            'authenticationToken': authenticationToken
        }
    )

    await ws.send(json.dumps(auth_message))
    data = await ws.recv()
    data = json.loads(data)
    print(data)

# __init__(self, name, scalar, delta, value, vrange, added_by='N/A', param_type='ModelParam'):
def hook_default_tracking_params(data):
    global tracking_params
    params = data['data']['defaultParameters']
    extended_params = {
            param['name']: VTSParameter(
                name=param['name'],
                value=param['defaultValue'],
                # target=param['value'],
                added_by=getattr(param, 'addedBy', 'N/A'),
                vrange=(param['min'], param['max'])
            )
            for param in params
        }

    tracking_params = extended_params
    pass

def hook_expression_tracking_params(data):
    global tracking_params
    params = data['data']['expressions']
    for expression in params:
        tracking_params[expression['name']] = ExpressionParam(
            name=expression['name'],
            file=expression['file'],
            value=expression['active'],
        )



def hook_movement_tracking_params():
    global tracking_params

    tracking_params['positionX'] = VTSMovementParameters(
        'positionX', 1, 15, -0.8, (-1, 1), m = 1, mu = 0.3,
        k = 1, vdelta = 0.5, vorange=(-5, 5)
    )

    tracking_params['positionY'] = VTSMovementParameters(
        'positionY', 1, 15, -0.8, (-1, 1), m=1, mu=0.3,
        k=1, vdelta=0.5, vorange=(-5, 5)
    )

    tracking_params['rotation'] = VTSRotationParameters(
        'rotation', 1, 15, 0, (0, 360), m = 1, mu = 0.1, k = 0.7,
        vdelta = 60, vorange=(-180, 180)
    )

    tracking_params['size'] = VTSMovementParameters(
        'size', 1, 15, -0.8, (-100, 100), m=1, mu=0.3,
        k=1, vdelta=0.5, vorange=(-5, 5)
    )



async def get_all_tracking_param(__ws__):
    # global tracking_params

    msg = msg_wrapper(
        'InputParameterListRequest'
    )

    await __ws__.send(json.dumps(msg))
    data = await __ws__.recv()
    data = json.loads(data)
    print('get all tracking param: ', data)
    return data

async def get_all_expression_param(__ws__):
    msg = msg_wrapper(
        'ExpressionStateRequest'
    )
    await __ws__.send(json.dumps(msg))
    data = await __ws__.recv()
    data = json.loads(data)
    print('get all expression param: ', data)
    return data

def setup_parameters(config):
    global tracking_params
#     banned:
    banned_param_names = config['banned_params']
    for banned_name in banned_param_names:
        if banned_name in tracking_params.keys():
            tracking_params.pop(banned_name)

#     check_before_apply:
    for checked_key, content in config['check_before_apply'].items():
        if checked_key in tracking_params.keys():
            tracking_params[checked_key].register_checking_content(content)

    for param_name, alternative_name in config['alternative'].items():
        if param_name in tracking_params.keys():
            tracking_params[alternative_name] = copy.deepcopy(tracking_params[param_name])
            tracking_params.pop(param_name)

async def run_pre():
    global __ws__
    url = '''ws://localhost:{}'''.format(port)

    __ws__ = await websockets.connect(url)
    say_hello_req = msg_wrapper('APIStateRequest')
    await __ws__.send(json.dumps(say_hello_req))
    data = await __ws__.recv()
    data = json.loads(data)
    print(data)

    await get_auth_session(__ws__)
    await asyncio.sleep(5)

    data = await get_all_tracking_param(__ws__)
    hook_default_tracking_params(data)
    data = await get_all_expression_param(__ws__)
    hook_expression_tracking_params(data)
    hook_movement_tracking_params()

    # special blocked
    # tracking_params['miyan'] = copy.deepcopy(tracking_params['mimiyan'])

    # setup_parameters
    setup_parameters(config)

    # print_all_paramters
    ss = [x.print_to_str() for _, x in tracking_params.items()]
    s = ''
    cnt = 3
    for x in ss:
        s = s + x
        if not cnt:
            cnt = 3
            s = s + '\n'
        else:
            s = s + ' '
            cnt = cnt - 1
    print(s)
    with open('readme.txt', 'w') as fout:
        fout.write(s)

    pass

async def run_main_vts():
    # url = 'ws://localhost:8001'
    global tracking_params
    global __cnt__

    await run_pre()

    MAX_L = 10

    cnt = 0

    T = 0.05

    while True:

        for _, param in tracking_params.items():
            param.update(T)
        # print(tracking_params['FaceAngleX'].value, tracking_params['FaceAngleX'].target)
        # print(tracking_params['danmaku_tail'].value, tracking_params['danmaku_tail'].v, tracking_params['danmaku_tail'].target)
        # print(tracking_params['rotation'].value, tracking_params['rotation'].v)
        express_change_msg = msg_wrapper(
            'InjectParameterDataRequest',
            {
                'parameterValues': [{
                    'id': param_name,
                    'value': param_value.value
                } for param_name, param_value in tracking_params.items()
                    if param_value.param_type == 'ModelParam' # and param_value.changed == True
                ]
            }
        )

        await __ws__.send(json.dumps(express_change_msg))
        data = await __ws__.recv()

        move_params = {
            param_name: param_value.value
            for param_name, param_value in tracking_params.items()
            if param_value.param_type == 'PositionParam' and param_value.changed == True
        }
        move_params['timeInSeconds'] = T
        move_params['valuesAreRelativeToModel'] = False
        move_msg = msg_wrapper(
            'MoveModelRequest',
            move_params,
        )

        # print(move_msg)
        # move_params['rotation'] = move_params['rotation'] % 360
        await __ws__.send(json.dumps(move_msg))
        await __ws__.recv()

        for param_name, param_value in tracking_params.items():
            if param_value.param_type == 'ExpressionParam' and param_value.changed == True:
                expression_msg = msg_wrapper(
                    'ExpressionActivationRequest',
                    {
                        'expressionFile':  param_value.file,
                        'active': param_value.value
                    }
                )

                await __ws__.send(json.dumps(expression_msg))
                response = await __ws__.recv()
                print(response)
            param_value.teardown()
        # print(json.loads(data))
        # cnt = cnt + 1
        # if cnt == MAX_L:
        #     cnt = 0

        await asyncio.sleep(T)


__cnt__ = 20

def on_message(ws: websocket.WebSocketApp, msg):
    global tracking_params
    global danmaku_id
    # global tracking_params_range
    # print('on message: ', msg)
    msg_decoded = bili_decode(msg)
    cmd_prefix = ''
    # print(msg_decoded.body)



    def process_danmaku(cmd: str):
        print(cmd)
        cmds = cmd.split(' ')

        if cmds[0] != danmaku_id:
            return

        cmds = cmds[1:]

        def check_in_param(cmds):

            return len(cmds) == 2 and cmds[0] in tracking_params.keys()

        if not check_in_param(cmds):
            return

        # check valid command
        # cmds = cmd.split(' ')
        # print('processing: ', cmds)
        print('before check:', cmds)
        if check_in_param(cmds):
            param_name, value = cmds[0], cmds[1]
            print('''trying to set {} to {}'''.format(param_name, value))
            # param = tracking_params[param_name]
            # param.value = float(value)
            param = tracking_params[param_name]
            param.set_target(param.astype(value))
        def check_cmd(cmd):
            return len(cmd) == 2 and cmd[0] in '0123456789A' and cmd[1] in 'adws'



        # for cmd in cmds:
            # # if not check_cmd(cmd):
            # #     continue
            #
            #
            # param_name = danmaku_cmd2param[cmd[0]]
            # param = tracking_params[param_name]
            #
            # if cmd[1] == 'd':
            #     param.increase()
            # elif cmd[1] == 'a':
            #     param.decrease()
            # elif cmd[1] == 'w':
            #     param.set_vinit_p()
            # elif cmd[1] == 's':
            #     param.set_vinit_n()

        # print('******************processing: ', cmds)

    if isinstance(msg_decoded, list):

        # process_danmaku('6d 6d 6d')

        for x in msg_decoded:
            # print(x.body)
            info = x.body
            if x.operation == 3:
                print('heartbeat: ', msg_decoded.body)
            if info['cmd'] == 'DANMU_MSG':
                # print('get danmaku')
                # danmaku_conttent = info['info']
                danmaku_content = json.loads(info['info'][0][15]['extra'])['content']
                print(danmaku_content)
                if danmaku_content.startswith(cmd_prefix):
                    process_danmaku(danmaku_content[len(cmd_prefix):])

                # if danmaku_content == '[ix]':
                #     tracking_params['FaceAngleX'] = clip_params(tracking_params['FaceAngleX'] + 5, tracking_params_range['FaceAngleX'])
                #     print('tracking params increased')
                # if danmaku_content == '[dx]':
                #     tracking_params['FaceAngleX'] = clip_params(tracking_params['FaceAngleX'] - 5,
                #                                                 tracking_params_range['FaceAngleX'])
                #     print('tracking params decreased')

                # __cnt__ = __cnt__ + 1
                # raise Exception
    else:
        pass
        # print(msg_decoded.proto_version, msg_decoded.operation, msg_decoded.body)
    # cnt = cnt - 1
    # if cnt == 0:
    #     cnt = 20
    # ws.send(bili_heart())

def on_error(ws, err):
    print('on error: ', err)

def on_close(ws):
    print('closed')

def on_open(ws: websocket.WebSocketApp):
    print('opened')

    # print(msg_send)
    msg_send = bili_enter_room()
    print('send message: ', msg_send)
    ws.send(msg_send)

    def run_heartbeat():
        heart_beat = bili_heart()
        while True:
            time.sleep(30)
            ws.send(heart_beat)

    def run_vts_plugin():
        print('run vts plugin')
        asyncio.run(run_main_vts())

    thread.start_new_thread(run_heartbeat, ())
    thread.start_new_thread(run_vts_plugin, ())

def main_2():
    ws = websocket.WebSocketApp(
        url,
        on_open = on_open,
        on_message = on_message,
    )

    heartbit = bili_heart()

    ws.run_forever(
    )


def register_tracking_param(cmd_name, parameter):
    danmaku_cmd2param[cmd_name] = parameter.name
    tracking_params[parameter.name] = parameter

if __name__ == '__main__':
    # global port
    # global config
    # print(bili_heart())
    # print(bili_into_room())
    # register_tracking_param('0', VTSParameter('FaceAngleX', 30, 0.2, 0, (-30, 30)))
    # register_tracking_param('1', VTSParameter('FaceAngleY', 30, 0.2, 0, (-30, 30)))
    # register_tracking_param('2', VTSParameter('FaceAngleZ', 20, 0.2, 0, (-20, 20)))
    # register_tracking_param('3', VTSParameter('MouthSmile', 1, 0.2, 0, (0, 1)))
    # register_tracking_param('4', VTSParameter('MouthOpen', 2, 0.2, 0, (0, 2)))
    # register_tracking_param('5', VTSEyeOpenParameter('EyeOpenLeft', 1, 0.2, 1, (0, 1.5)))
    # register_tracking_param('6', VTSEyeOpenParameter('EyeOpenRight', 1, 0.2, 1, (0, 1.5)))
    # # register_tracking_param('7', VTSTailParameter('danmaku_tail', 1, 0.2, 0, (-1, 1), m = 1, mu = 0.1, k = 0.2, vdelta = 1, vorange=(-10, 10)))
    # register_tracking_param('8', VTSRotationParameters('rotation', 1, 15, 0, None, m = 1, mu = 0.1, k = 0.7, vdelta = 60, vorange=(-1800, 1800)))
    # register_tracking_param('9', VTSMovementParameters('positionX', 1, 15, -0.8, (-1, 1), m = 1, mu = 0.3, k = 1, vdelta = 0.5, vorange=(-5, 5)))
    # register_tracking_param('A', VTSMovementParameters('positionY', 1, 15, -0.8, (-1, 1), m = 1, mu = 0.3, k = 1, vdelta = 0.5, vorange=(-5, 5)))
    # port = input('enter port listened by VTS: ')
    # port = int(port)
    config_path = input('enter config file path: ')
    with open(config_path, 'r') as config_fin:
        config = json.load(config_fin)
    port = config['port']
    danmaku_id = config['danmaku_id']
    authenticationToken = config['authenticationToken']
    main_2()
    # asyncio.run(run_main())
    exit(0)