import pprint
from datetime import date

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary, handling date objects as keys."""
    # Try direct lookup first
    result = dictionary.get(key, None)
    if result is not None:
        return result
    
    # If key is a date object, try to match it with other date objects
    if isinstance(key, date):
        for dict_key in dictionary:
            if isinstance(dict_key, date) and dict_key == key:
                return dictionary[dict_key]
    
    return {}


@register.filter
def multiply(value, arg):
    return value * arg
