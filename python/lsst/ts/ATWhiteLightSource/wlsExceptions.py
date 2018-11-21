class WattageTooHighException(Exception):
    """raised when user requests to set the White Light Source over 1200w"""
    pass

class WattageTooLowException(Exception):
    """raised when user requests to set the White Light Source under 800w"""
    pass

class BulbWearAndTearWarning(Warning):
    """warning when the bulb has accumulated 900 hours of use and needs to be replaced"""
    pass