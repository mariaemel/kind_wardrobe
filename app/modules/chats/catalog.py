from enum import StrEnum


class MessageType(StrEnum):
    TEXT = "text"
    SYSTEM = "system"


class TransferStatus(StrEnum):
    CONFIRMATION_PENDING = "confirmation_pending"
    WAITING_SECOND_CONFIRMATION = "waiting_second_confirmation"
    COMPLETED = "completed"


class HistoryRole(StrEnum):
    OWNER = "owner"
    RECIPIENT = "recipient"
