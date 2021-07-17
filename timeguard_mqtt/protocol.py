from dataclasses import dataclass
import typing
from arrow.arrow import Arrow
from construct import Computed, Const, Int8ul, Int16ul, Int32ul, this, Switch, Bytes, Hex, HexDump, ExprValidator, BitsInteger, Flag, ByteSwapped, RestreamData, Timestamp, Rebuild, obj_, PaddedString
from construct_typed import DataclassMixin, DataclassBitStruct, DataclassStruct, EnumBase, FlagsEnumBase, TFlagsEnum, TEnum, csfield
import crcmod
from random import randrange


crc16_xmodem = crcmod.mkCrcFun(0x11021, rev=False, initCrc=0x0000, xorOut=0x0000)


class BoostState(EnumBase):
    OFF = 0
    ONE_HOUR = 1
    TWO_HOURS = 2
    UNSPECIFIED = 3


class AdvanceState(EnumBase):
    OFF = 0
    ON = 1


class WorkMode(EnumBase):
    AUTO = 0
    ALWAYS_OFF = 1
    ALWAYS_ON = 2
    HOLIDAY = 3


class MessageType(EnumBase):
    PING = 0
    UNKNOWN1 = 1
    CODE_VERSION = 2
    UNKNOWN2 = 3
    UNKNOWN3 = 4
    SCHEDULE = 5
    UNKNOWN4 = 6
    UNKNOWN5 = 7
    WORK_MODE = 8
    HOLIDAY = 9
    UPDATE_SCHEDULE_NAME = 10
    ACTIVE_SCHEDULE = 11
    ADVANCE = 12
    BOOST = 13


class MessageFlags(FlagsEnumBase):
    IS_SUCCESS = 1
    IS_UPDATE_REQUEST = 2
    UNKNOWN1 = 4
    IS_FROM_SERVER = 8
    RESERVED1 = 16
    RESERVED2 = 32
    RESERVED3 = 64
    RESERVED4 = 128

    def server(write: bool = False) -> 'MessageFlags':
        return MessageFlags(
            MessageFlags.IS_FROM_SERVER | MessageFlags.UNKNOWN1 |
            MessageFlags.IS_UPDATE_REQUEST if write else 0
        )


class SwitchState(EnumBase):
    OFF = 1
    ON = 2


@dataclass
class Boost(DataclassMixin):
    boost_type: BoostState = csfield(TEnum(BitsInteger(2), BoostState))
    minutes_from_sunday: int = csfield(BitsInteger(14))
    duration_in_minutes: int = csfield(Computed(
        lambda ctx: 60 if ctx.boost_type == 1 else 120 if ctx.boost_type == 2 else 0
    ))
    expected_finish_time: int = csfield(Computed(this.minutes_from_sunday + this.duration_in_minutes))


@dataclass
class DeviceState(DataclassMixin):
    switch_state: SwitchState = csfield(TEnum(BitsInteger(2), SwitchState))
    unknown1: int = csfield(BitsInteger(1))
    load_detected: bool = csfield(Flag)
    advance_mode_state: AdvanceState = csfield(TEnum(BitsInteger(1), AdvanceState))
    load_was_detected_previously: bool = csfield(Flag)
    unknown2: int = csfield(BitsInteger(2))


@dataclass
class PingRequest(DataclassMixin):
    state: DeviceState = csfield(DataclassBitStruct(DeviceState, reverse=True))
    unknown2: int = csfield(Hex(Bytes(3)))
    work_mode: WorkMode = csfield(TEnum(Int8ul, WorkMode))
    unknown3: int = csfield(Hex(Bytes(3)))
    uptime: int = csfield(Int32ul)
    boost: Boost = csfield(ByteSwapped(DataclassBitStruct(Boost)))
    unknown4: int = csfield(Int16ul)


@dataclass
class PingResponse(DataclassMixin):
    now: Arrow = csfield(Timestamp(Int32ul, 1, 1970))


@dataclass
class BoostRequest(DataclassMixin):
    boost_type: BoostState = csfield(TEnum(Int8ul, BoostState))


@dataclass
class BoostResponse(DataclassMixin):
    expected_finish_time: Boost = csfield(ByteSwapped(DataclassBitStruct(Boost)))
    boost_start_config: Boost = csfield(ByteSwapped(DataclassBitStruct(Boost)))


@dataclass
class Empty(DataclassMixin):
    pass


@dataclass
class GetCurrentScheduleRequest(Empty):
    pass


@dataclass
class GetHolidaySettingsRequest(Empty):
    pass


@dataclass
class InitializationSequence(DataclassMixin):
    code_version: str = csfield(PaddedString(13, 'ascii'))


@dataclass
class ReportCodeVersionRequest(InitializationSequence):
    pass


@dataclass
class ReportCodeVersionResponse(InitializationSequence):
    pass


@dataclass
class GetCodeVersionRequest(Empty):
    pass


@dataclass
class GetCodeVersionResponse(InitializationSequence):
    pass


@dataclass
class AdvanceModeRequest(DataclassMixin):
    mode: AdvanceState = csfield(TEnum(BitsInteger(1), AdvanceState))


@dataclass
class AdvanceModeResponse(AdvanceModeRequest):
    pass


@dataclass
class SetWorkmodeRequest(DataclassMixin):
    work_mode: WorkMode = csfield(TEnum(Int8ul, WorkMode))


@dataclass
class SetWorkmodeResponse(SetWorkmodeRequest):
    pass


@dataclass
class SetHolidayRequest(DataclassMixin):
    is_active: bool = csfield(Flag)
    unknown: int = csfield(Hex(Bytes(3)))
    end: Arrow = csfield(Timestamp(Int32ul, 1, 1970))
    start: Arrow = csfield(Timestamp(Int32ul, 1, 1970))


@dataclass
class SetHolidayResponse(SetHolidayRequest):
    pass


@dataclass
class GetHolidaySettingsRequest(Empty):
    pass


@dataclass
class GetHolidaySettingsResponse(SetHolidayRequest):
    pass


@dataclass
class GetCurrentScheduleRequest(Empty):
    pass


@dataclass
class GetCurrentScheduleResponse(DataclassMixin):
    schedule_id: int = csfield(Int8ul)


@dataclass
class SetCurrentScheduleRequest(GetCurrentScheduleResponse):
    pass


@dataclass
class SetCurrentScheduleResponse(SetCurrentScheduleRequest):
    pass


@dataclass
class SetScheduleNameRequest(DataclassMixin):
    schedule_id: int = csfield(Int8ul)
    name: str = csfield(PaddedString(50, 'utf-8'))


@dataclass
class SetScheduleNameResponse(GetCurrentScheduleResponse):
    pass


@dataclass
class GetScheduleInfoRequest(GetCurrentScheduleResponse):
    pass


@dataclass
class ScheduleTime(DataclassMixin):
    reserved: int = csfield(BitsInteger(3))
    is_enabled: bool = csfield(Flag)
    minutes_from_midnight: int = csfield(BitsInteger(12))


class ScheduleRepeats(FlagsEnumBase):
    NONE = 0
    SUNDAY = 1
    MONDAY = 2
    TUESDAY = 4
    WEDNESDAY = 8
    THURSDAY = 16
    FRIDAY = 32
    SATURDAY = 64


@dataclass
class Schedule(DataclassMixin):
    start: ScheduleTime = csfield(ByteSwapped(DataclassBitStruct(ScheduleTime)))
    end: ScheduleTime = csfield(ByteSwapped(DataclassBitStruct(ScheduleTime)))
    repeat: bytes = csfield(TFlagsEnum(Int8ul, ScheduleRepeats))
    unknown: bytes = csfield(Hex(Bytes(1)))


@dataclass
class GetScheduleInfoResponse(DataclassMixin):
    schedule_id: int = csfield(Int8ul)
    schedule1: Schedule = csfield(DataclassStruct(Schedule))
    schedule2: Schedule = csfield(DataclassStruct(Schedule))
    schedule3: Schedule = csfield(DataclassStruct(Schedule))
    schedule4: Schedule = csfield(DataclassStruct(Schedule))
    schedule5: Schedule = csfield(DataclassStruct(Schedule))
    schedule6: Schedule = csfield(DataclassStruct(Schedule))
    name: str = csfield(PaddedString(50, 'utf-8'))


@dataclass
class SetScheduleInfoRequest(GetScheduleInfoResponse):
    pass


@dataclass
class SetScheduleInfoResponse(GetScheduleInfoResponse):
    pass


@dataclass
class Payload(DataclassMixin):
    MESSAGE_TYPE_MAP = {
        98: ReportCodeVersionRequest,
        178: ReportCodeVersionResponse,
        194: GetCodeVersionRequest,
        82: GetCodeVersionResponse,

        96: PingRequest,
        240: PingResponse,

        237: BoostRequest,
        125: BoostResponse,

        236: AdvanceModeRequest,
        124: AdvanceModeResponse,

        232: SetWorkmodeRequest,
        120: SetWorkmodeResponse,

        233: SetHolidayRequest,
        121: SetHolidayResponse,

        201: GetHolidaySettingsRequest,
        89: GetHolidaySettingsResponse,

        203: GetCurrentScheduleRequest,
        91: GetCurrentScheduleResponse,

        235: SetCurrentScheduleRequest,
        123: SetCurrentScheduleResponse,

        234: SetScheduleNameRequest,
        122: SetScheduleNameResponse,

        197: GetScheduleInfoRequest,
        85: GetScheduleInfoResponse,

        229: SetScheduleInfoRequest,
        117: SetScheduleInfoResponse,
    }

    message_type: MessageType = csfield(TEnum(ExprValidator(Int8ul, obj_ & 0b11110000 == 0), MessageType))
    message_flags: MessageFlags = csfield(TFlagsEnum(ExprValidator(Int8ul, obj_ & 0b11110000 == 0), MessageFlags))
    message_type_id: int = csfield(
        Computed(lambda ctx: Payload.get_message_type_id(ctx.message_type, ctx.message_flags)))
    params_size: int = csfield(
        Rebuild(
            Int16ul,
            lambda ctx: len(DataclassStruct(ctx.params.__class__).build(ctx.params)
                            if isinstance(ctx.params, DataclassMixin) else ctx.params)
        )
    )
    seq: int = csfield(Int8ul)
    unknown: int = csfield(Hex(Bytes(3)))
    device_id: int = csfield(Hex(Int32ul))
    params: typing.Any = csfield(Switch(this.message_type_id, {
        key: DataclassStruct(value)
        for key, value in MESSAGE_TYPE_MAP.items()
    }, default=HexDump(Bytes(this.params_size))))

    def get_message_type_id(message_type: MessageType, message_flags: MessageFlags) -> int:
        return message_type + (message_flags << 4)


@dataclass
class Timeguard(DataclassMixin):
    header: bytes = csfield(Hex(Const(b"\xFA\xD4")))
    payload_size: int = csfield(
        Rebuild(
            Int16ul,
            lambda ctx: len(DataclassStruct(Payload).build(ctx.payload))
        )
    )
    message_id: int = csfield(Hex(Int32ul))
    payload_raw: bytes = csfield(
        Rebuild(
            Hex(Bytes(this.payload_size)),
            lambda ctx: DataclassStruct(Payload).build(ctx.payload)
        )
    )
    payload: Payload = csfield(RestreamData(this.payload_raw, DataclassStruct(Payload)))
    checksum: int = csfield(
        Hex(
            Rebuild(
                ExprValidator(
                    Int16ul,
                    lambda obj, ctx: obj == crc16_xmodem(ctx.payload_raw)
                ),
                lambda ctx: crc16_xmodem(ctx.payload_raw)
            )
        )
    )

    footer: bytes = csfield(Hex(Const(b"\x2D\xDF")))

    def prepare(message_type: MessageType, message_flags: MessageFlags, device_id: int, message_id: int = 0xFFFFFFFF, payload_seq: typing.Optional[int] = None, payload_unknown=0x000000, **payload_params_kwargs) -> 'Timeguard':
        message_type_id = Payload.get_message_type_id(message_type, message_flags)
        payload_params_class = Payload.MESSAGE_TYPE_MAP.get(message_type_id)

        if payload_params_class is None:
            raise Exception('Unknown message_type_id={} ({} / {})'.format(message_type_id, message_type, message_flags))

        payload_params = payload_params_class(**payload_params_kwargs)

        if payload_seq is None:
            if message_flags & MessageFlags.IS_FROM_SERVER == 0:
                payload_seq = 0xFF
            else:
                payload_seq = randrange(0, 0xFE)

        ret = Timeguard(message_id=message_id)
        ret.payload = Payload(
            message_type=message_type,
            message_flags=message_flags,
            seq=payload_seq,
            unknown=payload_unknown,
            device_id=device_id,
            params=payload_params
        )

        return ret


format = DataclassStruct(Timeguard)
