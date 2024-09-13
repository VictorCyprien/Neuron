import asyncio
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCDataChannel
import json
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

SIGNALING_SERVER = "ws://188.166.4.120:8765"  # Your signaling server address

local_connection = None
remote_connection = None
send_channel = None
receive_channel = None

async def signaling_loop(websocket):
    async for message in websocket:
        # Process incoming messages (SDP offers/answers or ICE candidates)
        message = json.loads(message)
        logging.info(f"Received signaling message: {message}")
        if 'sdp' in message:
            desc = RTCSessionDescription(sdp=message['sdp'], type=message['type'])
            if message['type'] == 'offer':
                await remote_connection.setRemoteDescription(desc)
                answer = await remote_connection.createAnswer()
                await remote_connection.setLocalDescription(answer)
                await websocket.send(json.dumps({'sdp': answer.sdp, 'type': answer.type}))
            else:
                await local_connection.setRemoteDescription(desc)
        elif 'candidate' in message:
            candidate = message['candidate']
            pc = remote_connection if local_connection.sctp.transport == message['to'] else local_connection
            await pc.addIceCandidate(candidate)
            logging.info(f"Added ICE candidate: {candidate}")

async def send_signaling_message(websocket, message):
    await websocket.send(json.dumps(message))
    logging.info(f"Sent signaling message: {message}")

async def create_connection():
    global local_connection, remote_connection, send_channel

    # Create local and remote peer connections
    local_connection = RTCPeerConnection()
    remote_connection = RTCPeerConnection()

    logging.info("Local and Remote peer connections created 🛠️")

    # Set up data channels
    send_channel = local_connection.createDataChannel('sendDataChannel')
    send_channel.on('open', on_send_channel_state_change)
    send_channel.on('close', on_send_channel_state_change)

    remote_connection.on('datachannel', receive_channel_callback)

    # Exchange ICE candidates
    local_connection.on('icecandidate', lambda e: on_ice_candidate(local_connection, e))
    remote_connection.on('icecandidate', lambda e: on_ice_candidate(remote_connection, e))

    # Connect to the signaling server
    try:
        async with websockets.connect(SIGNALING_SERVER) as websocket:
            # Create offer and send it via the signaling server
            offer = await local_connection.createOffer()
            await local_connection.setLocalDescription(offer)
            await send_signaling_message(websocket, {'sdp': offer.sdp, 'type': offer.type})

            # Start listening for incoming signaling messages
            await signaling_loop(websocket)
    except ConnectionRefusedError:
        logging.error(f"Failed to connect to signaling server at {SIGNALING_SERVER}")
        logging.error("Make sure the signaling server is running and the address is correct.")
        return

async def send_data(data):
    global send_channel
    send_channel.send(data)
    logging.info(f'Sent Data: {data}')

async def close_data_channels():
    logging.info("Closing data channels ⛔")
    if send_channel:
        await send_channel.close()
    if receive_channel:
        await receive_channel.close()
    if local_connection:
        await local_connection.close()
    if remote_connection:
        await remote_connection.close()

def on_ice_candidate(pc, event):
    # Send ICE candidate to signaling server
    if event.candidate:
        candidate_json = event.candidate.to_json()
        asyncio.ensure_future(send_signaling_message(websockets.connect(SIGNALING_SERVER), {
            'candidate': candidate_json,
            'to': 'remote' if pc == local_connection else 'local'
        }))
        logging.info(f"{'Local' if pc == local_connection else 'Remote'} ICE candidate: {candidate_json}")

def receive_channel_callback(event):
    global receive_channel
    logging.info("Received data channel callback 🔄")
    receive_channel = event.channel
    receive_channel.on('message', on_receive_message)
    receive_channel.on('open', on_receive_channel_state_change)
    receive_channel.on('close', on_receive_channel_state_change)

def on_receive_message(message):
    logging.info(f"Received Message: {message}")

def on_send_channel_state_change():
    state = send_channel.readyState
    logging.info(f'Send channel state: {state}')
    if state == 'open':
        logging.info("Send channel is open, ready for action! 🚀")
        send_channel.send("Hello World")
        logging.info("Sent 'Hello World' message")

def on_receive_channel_state_change():
    state = receive_channel.readyState
    logging.info(f'Receive channel state: {state}')
    if state == 'open':
        logging.info("Receive channel is open, ready to receive messages 🎉")

# Run the main loop
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(create_connection())
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("Exiting... 🙌")
        loop.run_until_complete(close_data_channels())
    finally:
        loop.close()
