import asyncio
import hashlib
import json
import hmac
import os
import time
from typing import *
from urllib.parse import urlencode
from threading import Thread

import requests
import websocket
from dotenv import load_dotenv
from requests.exceptions import RequestException

from Moduls.data_modul import *

load_dotenv()


class BinanceClient:
    def __init__(self):
        self._base_url = "https://testnet.binancefuture.com"
        self._ws_url = "wss://stream.binancefuture.com/ws"
        self._header = {"X-MBX-APIKEY": os.getenv("BinanceFutureTestAPIKey"),
                        'Content-Type':'application/json'}
        
        self._http_dict = {
            "GET": requests.get,
            "POST": requests.post,
            "DELETE": requests.delete,
        }

        # Check internet connection
        self._is_connected()

        self.contracts = self._get_contracts()
        self.prices: Dict[str, Price] = dict()
        
        # Websocket connection
        self._id = 1
        self.bookTicker_subscribtion_list: Dict[str, int] = dict()
        
        self._reconnect = True
        t = Thread(target=self._start_ws)
        t.start()
        
    def _execute_request(self, endpoint: str, params: Dict, http_method: str):
        try:
            # Get the timestamp
            params["timestamp"] = int(time.time() * 1000)
            # Generate the signature for the query
            params["signature"] = self._generate_signature(urlencode(params))

            response = self._http_dict[http_method](
                self._base_url + endpoint, params=params, headers=self._header
            )
            response.raise_for_status()
            return response

        except RequestException as e:
            print(f"Request error {e}")
        except Exception as e:
            print(f"Error: {e}")
        return False

    def _generate_signature(self, query_string: str):
        return hmac.new(
            os.getenv("BinanceFutureTestAPISecret").encode("utf-8"),
            query_string.encode("utf-8"), 
            hashlib.sha256).hexdigest()

    def _is_connected(self, print_status=False):
        response = self._execute_request(endpoint="/fapi/v1/ping", 
                                         params={}, http_method='GET')
        if response:
            print("Connected")
            return True
        else:
            print(f"Can't connect")
            return False

    ####################### MARKET DATA FUNCTION #######################
    def _get_contracts(self) -> Dict[str, Contract]|None:
        response = self._execute_request(endpoint="/fapi/v1/exchangeInfo",
                                         params={}, http_method='GET')
        if response:
            data = response.json()["symbols"]
            contracts = {symbol["symbol"]: Contract(symbol, exchange="Binance")
                         for symbol in data}
            return contracts
        return None
            
    def get_candlestick(self, contract: Contract, interval="4h") -> List[CandleStick]:
        params = {"symbol": contract.symbol, "interval": interval}
        response = self._execute_request(endpoint="/fapi/v1/klines", 
                                         params=params, http_method='GET')
        if response: 
            return [CandleStick(candle, "Binance") for candle in response.json()]
        return None

    def get_price(self, contract: Contract) -> Price | None:
        response = self._execute_request(endpoint="/fapi/v1/ticker/bookTicker",
                                         params={"symbol": contract.symbol},
                                         http_method='GET')
        if response:
            self.prices[contract.symbol] = Price(response.json(), "Binance")
            price = self.prices[contract.symbol]
            return price
        return None

    ########################## TRADE FUNCTION ##########################
    def make_order(self, contract: Contract, order_side: str, order_type: str, **kwargs) -> Order | None:
        # Add the mandotary parameters
        params = {"symbol": contract.symbol, "side": order_side, "type": order_type}
        # Add extra parameters
        params.update(kwargs)
        response = self._execute_request(endpoint="/fapi/v1/order", 
                                         params=params, http_method="POST")
        if response:
            return Order(response.json(), exchange="Binance")
        return None

    def order_status(self, order: Order) -> Order:
        params = {"symbol": order.symbol, "orderId": order.orderId}

        response = self._execute_request(endpoint="/fapi/v1/order", 
                                         params=params, http_method="GET")
        if response:
            return Order(response.json(), exchange="Binance")
        return None

    def delete_order(self, order: Order) -> Order:
        params = {"symbol": order.symbol, "orderId": order.orderId}
        
        response = self._execute_request(endpoint="/fapi/v1/order",
                                         params=params, http_method="DELETE")
        if response:
            return Order(response.json(), exchange="Binance")
        return None

    ########################## ACCOUNT ##########################
    @property
    def balance(self) -> Dict[str, Balance] | None:
        endpoint = "/fapi/v2/account"
        response = self._execute_request(endpoint, params={})
        if response:
            balance: Dict[str, Balance]
            
            data = response.json()["assets"]
            balance = {asset["asset"]: Balance(asset, "Binance")
                       for asset in data}
            return balance
        return None
    
    @balance.setter
    def balance(self, *args, **kwargs):
        print("Balance can't be edited manually")
        return self.balance

    ############################ Websocket ############################
    def _start_ws(self):
        self.ws = websocket.WebSocketApp(self._ws_url,
                                         on_open=self._on_open, on_close=self._on_close,
                                         on_error=self._on_error, on_message=self._on_message)
        # Reopen the websocket connection if it terminated
        while True:
            try:
                if self._reconnect:  # Reconnect unless the interface is closed by the user
                    self.ws.run_forever()  # Blocking method that ends only if the websocket connection drops
                else:
                    break
            except Exception as e:
                # Update the log about this error
                print("Binance error in run_forever() method: %s", e)
            # Add sleeping interval
            time.sleep(3)
    
    
    def _on_open(self, ws: websocket.WebSocketApp):
        print('Websocket connected')
        
    def _on_message(self, ws: websocket.WebSocketApp, msg):
        data = json.loads(msg)
        if 'e' in data.keys():
            if data['e']=='bookTicker':
                symbol = data['s']
                # If new untracked symbol
                if symbol not in self.prices.keys():
                    self.prices[symbol] = self.get_price(self.contracts[symbol])
                # Update ask/bid prices
                self.prices[symbol].bid = data['b']
                self.prices[symbol].ask = data['a']
                print(f"Symbol: {data['s']}\taskPrice: {data['a']}\tbidPrice: {data['b']}")
             
    def _on_error(self, ws: websocket.WebSocketApp, error):
        print(f"Error: {error}")
        
    def _on_close(self, ws: websocket.WebSocketApp):
        print("Websoccet disconnect")
        
    def new_subscribe(self, symbol='btcusdt', channel ='bookTicker'):
        params = f"{symbol.lower()}@{channel}"
        if symbol.lower() in self.bookTicker_subscribtion_list:
            print(f"Already subscribed to {params} channel")
        else:
            msg = {"method": 'SUBSCRIBE', "params":[params], "id": self._id}
            self.get_price(self.contracts[symbol.upper()])
            
            self.ws.send(json.dumps(msg))
            self.bookTicker_subscribtion_list[self._id] = {"params":[symbol.lower()+'@'+channel]}
            self.bookTicker_subscribtion_list[symbol.lower()] = self._id
            self._id += 1
            
    def unsubscribe_channel(self, symbol: str, channel='bookTicker'):
        symbol = symbol.lower()
        _id = self.bookTicker_subscribtion_list[symbol]
        msg = {"method": 'UNSUBSCRIBE', 
               'params':[f"{symbol}@{channel}"],
               "id": _id}
        self.ws.send(json.dumps(msg))
        self.bookTicker_subscribtion_list.pop(symbol)
        self.prices.pop(symbol.upper())
    
    