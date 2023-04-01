from dash import Input, Output, State, callback, ctx

from strategies import TechnicalStrategies
from Moduls.data_modul import Contract
from app import clients


def get_removed_row(prev_data, data):
    for item in prev_data:
        if item not in data:
            return item
        

@callback(Output(component_id="websocket-init", component_property="disabled"),
          Input(component_id="websocket-init", component_property="n_intervals"),
          prevent_initial_call=True)
def start_websockets(*args):
    for client in clients.values():
        client.run()
    return True

        
@callback(Output(component_id='watchlist-select', component_property='value'),
          Input(component_id='watchlist-select', component_property='value'))
def subscribe_to_new_stream(value: str):
    if value:
        exchange, symbol = value.split(" ")
        clients[exchange].new_subscribe(symbol, channel="bookTicker")
    return None


@callback(Output(component_id='watchlist-table', component_property='data'),
          Input(component_id='watchlist-table', component_property='data_previous'),
          Input(component_id='watchlist-interval', component_property='n_intervals'),
          State(component_id='watchlist-table', component_property='data'))
def update_watchlist_table(prev_data, n, data):
    triggered = ctx.triggered_id
    if triggered == 'watchlist-table':
        removed_row = get_removed_row(prev_data, data)
        exchange = removed_row['exchange']
        symbol = removed_row['symbol']
        clients[exchange].unsubscribe_channel(symbol, "bookTicker")
    else:
        data = [{'symbol': price.symbol, 'exchange': price.exchange,
                 'bidPrice': price.bid, 'askPrice': price.ask}
                for price in clients['Binance'].prices.values()]
    return data


@callback(Output(component_id='strategy-contracts-dropdown', component_property='value'),
          Input(component_id='add-strategy-btn', component_property='n_clicks'),
          State(component_id='strategy-contracts-dropdown', component_property='value'), 
          State(component_id='entry-pct', component_property='value'),
          State(component_id='take-profit', component_property='value'),
          State(component_id='stop-loss', component_property='value'),
          State(component_id='interval-dropdown', component_property='value'),
          State(component_id="strategy-type-select", component_property="value"),
          State(component_id='fast-ema', component_property='value'),
          State(component_id='slow-ema', component_property='value'),
          State(component_id='fast-macd', component_property='value'),
          State(component_id='slow-macd', component_property='value'),
          State(component_id='macd-signal', component_property='value'),
          State(component_id="rsi-period", component_property='value'),
          prevent_initial_call=True)
def start_strategy(n_click, contract: Contract, buy_pct,
                   tp, sl, interval, strategy_type,
                   fast_ema, slow_ema, fast_macd,
                   slow_macd, macd_signal, rsi):
    if strategy_type=="Technical":
        ema = {"fast": fast_ema,
               "slow": slow_ema}
        
        macd = {"fast": fast_macd,
                "slow": slow_macd, 
                "signal": macd_signal}
        
        exchange, symbol = contract.split(' ')
        TechnicalStrategies(client=clients[exchange], symbol=symbol,
                            interval=interval, tp=tp, sl=sl,
                            buy_pct=buy_pct, ema=ema, macd=macd,
                            rsi=rsi)
    return None