_usg = None

def set_tracker(tracker):
    global _usg
    _usg = tracker


def get_tracker():
    return _usg
