import base64
import json
import time
import uuid
import threading
from websocket import create_connection
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from config import PROD_ED_KEY

def load_private_key():
    """Load the private key from the PEM file."""
    with open('test-prv-key.pem', 'rb') as f:
        return load_pem_private_key(data=f.read(), password=None)

def sign_request(params, private_key):
    """Sign the request parameters using the private key."""
    payload = '&'.join(sorted([f'{param}={value}' for param, value in params.items()]))
    signature = base64.b64encode(private_key.sign(payload.encode('ASCII'))).decode('ASCII')
    return signature

class UserDataStream:
    def __init__(self, callback):
        self.callback = callback
        self.ws = None
        self.authenticated = False
        self.running = False
        self.thread = None
        
    def authenticate(self):
        """Authenticate the WebSocket connection."""
        try:
            private_key = load_private_key()
            timestamp = int(time.time() * 1000)
            
            # Prepare authentication parameters
            params = {
                'timestamp': timestamp,
                'apiKey': PROD_ED_KEY,
            }
            params['signature'] = sign_request(params, private_key)
            
            # Create authentication request
            auth_request = {
                'id': 1,
                'method': 'session.logon',
                'params': params
            }
            
            # Send authentication request
            self.ws.send(json.dumps(auth_request))
            auth_response = json.loads(self.ws.recv())
            
            if auth_response.get('status') != 200:
                raise Exception(f"Authentication failed: {auth_response}")
                
            self.authenticated = True
            
            # Subscribe to user data stream
            subscribe_request = {
                'id': 2,
                'method': 'userDataStream.subscribe'
            }
            
            # Send subscription request
            self.ws.send(json.dumps(subscribe_request))
            subscribe_response = json.loads(self.ws.recv())
            
            if subscribe_response.get('status') != 200:
                raise Exception(f"Failed to subscribe to user data stream: {subscribe_response}")
                
        except Exception as e:
            self.authenticated = False
            raise
            
    def _run(self):
        """Run the WebSocket connection in a loop."""
        while self.running:
            try:
                # Create new WebSocket connection
                self.ws = create_connection('wss://ws-api.testnet.binance.vision/ws-api/v3')
                
                # Authenticate and subscribe
                self.authenticate()
                
                # Main message loop
                while self.running and self.authenticated:
                    try:
                        message = self.ws.recv()
                        data = json.loads(message)
                        
                        # Handle ping messages
                        if isinstance(data, dict) and data.get('method') == 'ping':
                            pong_response = {
                                'id': data.get('id'),
                                'method': 'pong'
                            }
                            self.ws.send(json.dumps(pong_response))
                            continue
                            
                        # Handle user data stream messages
                        if self.callback:
                            self.callback(data)
                            
                    except Exception as e:
                        break
                        
            except Exception as e:
                pass
                
            finally:
                if self.ws:
                    try:
                        self.ws.close()
                    except:
                        pass
                        
            # Wait before reconnecting
            if self.running:
                time.sleep(5)
                
    def start(self):
        """Start the user data stream."""
        self.running = True
        self.thread = threading.Thread(target=self._run)
        self.thread.daemon = True
        self.thread.start()
        
    def stop(self):
        """Stop the user data stream."""
        self.running = False
        if self.ws:
            try:
                # Unsubscribe from user data stream
                if self.authenticated:
                    unsubscribe_request = {
                        'id': 3,
                        'method': 'userDataStream.unsubscribe'
                    }
                    self.ws.send(json.dumps(unsubscribe_request))
                    
                # Close WebSocket connection
                self.ws.close()
            except Exception as e:
                print(f"Error stopping user data stream: {e}")
                
        if self.thread:
            self.thread.join(timeout=5)

def get_user_data_stream(callback):
    """Get a user data stream using ED25519 authentication."""
    stream = UserDataStream(callback)
    stream.start()
    return stream

def close_user_data_stream(stream):
    """Close the user data stream."""
    if stream:
        stream.stop() 