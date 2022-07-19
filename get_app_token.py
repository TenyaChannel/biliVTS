import asyncio
import websockets
import json
import uuid
import traceback
import time
import math

# plugin_token = '435c61fde0b28635ae5abdd34be53ba3ca1ed35da5a25bf5425a0ff082f9e55a'



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

async def send_msg(ws, msg_dict):
    msg = json.dumps(msg_dict)
    await ws.send(msg)
    response = await ws.recv()
    response_dict = None
    try:
        response_dict = json.loads(response)
    except Exception as e:
        traceback.print_exc()
    return response_dict

async def get_auth_token(ws):
    auth_data = {
        'pluginName': 'playmodel',
        'pluginDeveloper': 'Tenya_Channel',
        'pluginIcone': 'iVBORw0.........KGgoA=',
    }
    auth_req = msg_wrapper('AuthenticationTokenRequest', auth_data)

    response = await send_msg(ws, auth_req)
    # response = json.loads(response)
    data = response['data']
    if 'authenticationToken' in data:
        print('''your auth key is: {}'''.format(data['authenticationToken']))
    elif 'errorID' in data:
        print('''error from vts No.{} : {}'''.format(data['errorID'], data['message']))
    else:
        print('unknown error')

async def get_app_token(port):
    url = '''ws://localhost:{}'''.format(port)
    async with websockets.connect(url) as ws:
        await get_auth_token(ws)

if __name__ == '__main__':
    port = input('enter port of your vts api:')
    asyncio.run(get_app_token(port))
    exit(0)