from PyQt6.QtCore import QObject, pyqtSignal

class EventBus(QObject):
    message_received = pyqtSignal(str, str, str)
    # New signal: passes (msg_id, status) where status is "delivered"
    message_status_updated = pyqtSignal(str, str)

# Global instance
event_bus = EventBus()