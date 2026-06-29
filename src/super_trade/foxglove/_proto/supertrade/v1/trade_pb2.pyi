import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Equity(_message.Message):
    __slots__ = ("time", "equity", "cash", "drawdown")
    TIME_FIELD_NUMBER: _ClassVar[int]
    EQUITY_FIELD_NUMBER: _ClassVar[int]
    CASH_FIELD_NUMBER: _ClassVar[int]
    DRAWDOWN_FIELD_NUMBER: _ClassVar[int]
    time: _timestamp_pb2.Timestamp
    equity: float
    cash: float
    drawdown: float
    def __init__(
        self,
        time: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]
        ] = ...,
        equity: _Optional[float] = ...,
        cash: _Optional[float] = ...,
        drawdown: _Optional[float] = ...,
    ) -> None: ...

class Position(_message.Message):
    __slots__ = (
        "symbol",
        "shares",
        "avg_price",
        "price",
        "market_value",
        "unrealized_pnl",
        "weight",
    )
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    SHARES_FIELD_NUMBER: _ClassVar[int]
    AVG_PRICE_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    MARKET_VALUE_FIELD_NUMBER: _ClassVar[int]
    UNREALIZED_PNL_FIELD_NUMBER: _ClassVar[int]
    WEIGHT_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    shares: int
    avg_price: float
    price: float
    market_value: float
    unrealized_pnl: float
    weight: float
    def __init__(
        self,
        symbol: _Optional[str] = ...,
        shares: _Optional[int] = ...,
        avg_price: _Optional[float] = ...,
        price: _Optional[float] = ...,
        market_value: _Optional[float] = ...,
        unrealized_pnl: _Optional[float] = ...,
        weight: _Optional[float] = ...,
    ) -> None: ...

class Portfolio(_message.Message):
    __slots__ = ("time", "equity", "cash", "positions", "num_positions")
    TIME_FIELD_NUMBER: _ClassVar[int]
    EQUITY_FIELD_NUMBER: _ClassVar[int]
    CASH_FIELD_NUMBER: _ClassVar[int]
    POSITIONS_FIELD_NUMBER: _ClassVar[int]
    NUM_POSITIONS_FIELD_NUMBER: _ClassVar[int]
    time: _timestamp_pb2.Timestamp
    equity: float
    cash: float
    positions: _containers.RepeatedCompositeFieldContainer[Position]
    num_positions: int
    def __init__(
        self,
        time: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]
        ] = ...,
        equity: _Optional[float] = ...,
        cash: _Optional[float] = ...,
        positions: _Optional[_Iterable[_Union[Position, _Mapping]]] = ...,
        num_positions: _Optional[int] = ...,
    ) -> None: ...

class Fill(_message.Message):
    __slots__ = (
        "time",
        "symbol",
        "side",
        "shares",
        "price",
        "cost",
        "notional",
        "reason",
    )
    TIME_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    SIDE_FIELD_NUMBER: _ClassVar[int]
    SHARES_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    COST_FIELD_NUMBER: _ClassVar[int]
    NOTIONAL_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    time: _timestamp_pb2.Timestamp
    symbol: str
    side: str
    shares: int
    price: float
    cost: float
    notional: float
    reason: str
    def __init__(
        self,
        time: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]
        ] = ...,
        symbol: _Optional[str] = ...,
        side: _Optional[str] = ...,
        shares: _Optional[int] = ...,
        price: _Optional[float] = ...,
        cost: _Optional[float] = ...,
        notional: _Optional[float] = ...,
        reason: _Optional[str] = ...,
    ) -> None: ...

class Bar(_message.Message):
    __slots__ = ("time", "symbol", "open", "high", "low", "close", "volume")
    TIME_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    OPEN_FIELD_NUMBER: _ClassVar[int]
    HIGH_FIELD_NUMBER: _ClassVar[int]
    LOW_FIELD_NUMBER: _ClassVar[int]
    CLOSE_FIELD_NUMBER: _ClassVar[int]
    VOLUME_FIELD_NUMBER: _ClassVar[int]
    time: _timestamp_pb2.Timestamp
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    def __init__(
        self,
        time: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]
        ] = ...,
        symbol: _Optional[str] = ...,
        open: _Optional[float] = ...,
        high: _Optional[float] = ...,
        low: _Optional[float] = ...,
        close: _Optional[float] = ...,
        volume: _Optional[float] = ...,
    ) -> None: ...
