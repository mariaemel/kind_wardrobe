from enum import StrEnum


class MessageType(StrEnum):
    TEXT = "text"
    SYSTEM = "system"


class TransferKind(StrEnum):
    PEER = "peer"
    ORGANIZATION = "organization"


class TransferStatus(StrEnum):
    CONFIRMATION_PENDING = "confirmation_pending"
    WAITING_SECOND_CONFIRMATION = "waiting_second_confirmation"
    COMPLETED = "completed"


class HistoryRole(StrEnum):
    OWNER = "owner"
    RECIPIENT = "recipient"
    TO_ORGANIZATION = "to_organization"


class HistoryFilter(StrEnum):
    ALL = "all"
    TRANSFERRED = "transferred"
    RECEIVED = "received"
    TO_ORGANIZATIONS = "to_organizations"


HISTORY_STATUS_LABELS = {
    HistoryRole.OWNER: "Передано",
    HistoryRole.RECIPIENT: "Получено",
    HistoryRole.TO_ORGANIZATION: "Передано организации",
}
