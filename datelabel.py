"""Classes and utility methods for dealing with dates as expressed in filenames 
and paths. Intended use case is, eg, determining if a file contains data for a
given year from the filename, without having to open it and parse the header.

Note:
    These classes should *not* be used for calendar math! We currently implement
    and test comparison logic only, not anything more (eg addition, subtraction).
"""
import re
import datetime

class Date(datetime.datetime):
    """Define a date with variable level precision.
    """
    # define __new__, not __init__, because datetime is immutable
    def __new__(cls, *args, **kwargs):
        if len(args) == 1 and type(args[0]) is str:
            args = cls._parse_input_string(args[0])
        precision = len(args)
        if precision == 1:
            args = (args[0], 1, 1) # missing month & day
        elif precision == 2:
            args = (args[0], args[1], 1) # missing day
        obj = super(Date, cls).__new__(cls, *args, **kwargs) 
        obj.precision = precision
        return obj

    @classmethod
    def _parse_input_string(cls, s):
        """Parse date strings in `YYYY-MM-DD` or `YYYYMMDDHH` formats.
        """
        if '-' in s:
            return tuple([int(ss) for ss in s.split('-')])
        elif len(s) == 4:
            return (int(s[0:4]), )
        elif len(s) == 6: 
            return (int(s[0:4]), int(s[4:6]))
        elif len(s) == 8: 
            return (int(s[0:4]), int(s[4:6]), int(s[6:8]))
        elif len(s) == 10: 
            return (int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]))
        else:
            raise ValueError("Malformed input {}".format(s))

    def format(self):
        """Print date in YYYYMMDDHH format, with length being set automatically
        from precision. 
        
        Other formats can be obtained manually with `strftime`.
        """
        if self.precision == 1:
            return self.strftime('%Y')
        elif self.precision == 2:
            return self.strftime('%Y%m')
        elif self.precision == 3:
            return self.strftime('%Y%m%d')
        elif self.precision == 4:
            return self.strftime('%Y%m%d%H')
        else:
            raise ValueError("Malformed input")
    __str__ = format
    
    def __repr__(self):
        return "Date('{}')".format(self)   

    def __lt__(self, other):
        """Overload datetime.datetime's __lt__. Coerce to datetime.date if we're
        comparing with a datetime.date.
        """
        if isinstance(other, datetime.datetime):
            return super(Date, self).__lt__(other)
        else:
            return (self.date() < other)

    def __le__(self, other):
        """Overload datetime.datetime's __le__. Coerce to datetime.date if we're
        comparing with a datetime.date.
        """
        if isinstance(other, datetime.datetime):
            return super(Date, self).__le__(other)
        else:
            return (self.date() <= other)

    def __gt__(self, other):
        """Overload datetime.datetime's __gt__. Coerce to datetime.date if we're
        comparing with a datetime.date.
        """
        if isinstance(other, datetime.datetime):
            return super(Date, self).__gt__(other)
        else:
            return (self.date() > other)

    def __ge__(self, other):
        """Overload datetime.datetime's __ge__. Coerce to datetime.date if we're
        comparing with a datetime.date.
        """
        if isinstance(other, datetime.datetime):
            return super(Date, self).__ge__(other)
        else:
            return (self.date() >= other)

    def __eq__(self, other):
        """Overload datetime.datetime's __eq__. Require precision to match as
        well as date. Coerce to datetime.date if we're comparing with a datetime.date.
        """
        if isinstance(other, Date):
            return (self.precision == other.precision) and super(Date, self).__eq__(other)
        elif isinstance(other, datetime.datetime):
            return super(Date, self).__eq__(other)
        else:
            return (self.date() == other)

    def __ne__(self, other):
        return (not self.__eq__(other)) # more foolproof

    def increment(self):
        """Return a copy of Date advanced by one time unit as specified by
        the `precision` attribute.
        """
        if self.precision == 1:
            return Date(self.year + 1)
        elif self.precision == 2:
            if self.month == 12:
                return Date(self.year + 1, 1)
            else:
                return Date(self.year, self.month + 1)
        elif self.precision == 3:
            dt = self.__add__(datetime.timedelta(days = 1))
            return Date(dt.year, dt.month, dt.day)
        elif self.precision == 4:
            dt = self.__add__(datetime.timedelta(hours = 1))
            return Date(dt.year, dt.month, dt.day, dt.hour)
        else:
            raise ValueError("Malformed input")

    def decrement(self):
        """Return a copy of Date moved back by one time unit as specified by
        the `precision` attribute.
        """
        if self.precision == 1:
            return Date(self.year - 1)
        elif self.precision == 2:
            if self.month == 1:
                return Date(self.year - 1, 12)
            else:
                return Date(self.year, self.month - 1)
        elif self.precision == 3:
            dt = self.__add__(datetime.timedelta(days = -1))
            return Date(dt.year, dt.month, dt.day)
        elif self.precision == 4:
            dt = self.__add__(datetime.timedelta(hours = -1))
            return Date(dt.year, dt.month, dt.day, dt.hour)
        else:
            raise ValueError("Malformed input")


class DateRange(object):
    """Class representing a range of dates. 

    This is defined as a closed interval (containing both endpoints).
    """
    def __init__(self, start, end=None):
        if type(start) is str and (end is None):
            (start, end) = self._parse_input_string(start)
        elif isinstance(start, (list, tuple, set)) and (end is None):
            (start, end) = self._parse_input_collection(start)

        if not isinstance(start, Date):
            start = Date(start)
        if not isinstance(end, Date):
            end = Date(end)
        assert start < end

        self.start = start
        self.end = end

    @classmethod
    def _parse_input_string(cls, s):
        s2 = s.split('-')
        assert len(s2) == 2
        return tuple([Date(ss) for ss in s2])

    @classmethod
    def _parse_input_collection(cls, coll):
        if all(isinstance(item, DateRange) for item in coll):
            # given a bunch of DateRanges, return interval containing them
            # ONLY IF ranges are continguous and nonoverlapping
            dt_ranges = sorted(coll, key=lambda dtr: dtr.start)
            print dt_ranges
            for i in range(0, len(dt_ranges) - 1):
                if (dt_ranges[i].end.increment() != dt_ranges[i+1].start) \
                    or (dt_ranges[i+1].start.decrement() != dt_ranges[i].end):
                    raise ValueError("Date Ranges not contiguous and nonoverlapping.")
            return (dt_ranges[0].start, dt_ranges[-1].end)
        elif all(isinstance(item, Date) for item in coll):
            # given a bunch of Dates, return interval containing them
            return (min(coll), max(coll))
        elif len(coll) == 2 and (type(coll) is not set):
            # assume two entries meant to be start and end
            return tuple([Date(item) for item in coll])
        else:
            raise ValueError("Malformed input")
    
    def __eq__(self, other):
        return (self.start == other.start) and (self.end == other.end)

    def __ne__(self, other):
        return (not self.__eq__(other)) # more foolproof

    def __contains__(self, item): 
        return self.overlaps(item)
    def overlaps(self, item):
        """Comparison returning `True` if `item` has any overlap at all with the
        date range.

        This method overrides the `__contains__` method, so, e.g., 
        datetime.date('2019-09-18') in DateRange('2018-2019') will give
        `True`.
        """
        if isinstance(item, DateRange):
            return (self.start <= item.end) and (item.start <= self.end)
        else:
            return (self.start <= item) and (self.end >= item)

    def contains(self, item):
        """Comparison returning `True` if `item` is strictly contained within 
        the range.
        """
        if isinstance(item, DateRange):
            return (self.start <= item.start) and (self.end >= item.end)
        else:
            return (self.start <= item) and (self.end >= item)
    
    def format(self):
        return '{}-{}'.format(self.start, self.end)
    __str__ = format

    def __repr__(self):
        return "DateRange('{}')".format(self)        

class DateFrequency(datetime.timedelta):
    """Class representing a date frequency or period.

    Note:
        Period lengths are *not* defined accurately, eg. a year is taken as
        365 days and a month is taken as 30 days. 
    """
    # define __new__, not __init__, because timedelta is immutable
    def __new__(cls, quantity, unit=''):
        if (type(quantity) is str) and (unit == ''):
            (quantity, unit) = cls._parse_input_string(quantity)
        if (type(quantity) is not int) or (type(unit) is not str):
            raise ValueError("Malformed input")
        else:
            unit = unit.lower()

        if unit[0] == 'y':
            kwargs = {'days': 365 * quantity}
            unit = 'yr'
        elif unit[0] == 's':
            kwargs = {'days': 91 * quantity}
            unit = 'se'
        elif unit[0] == 'm':
            kwargs = {'days': 30 * quantity}
            unit = 'mo'
        elif unit[0] == 'w':
            kwargs = {'days': 7 * quantity}
            unit = 'wk'
        elif unit[0] == 'd':
            kwargs = {'days': quantity}
            unit = 'dy'
        elif unit[0] == 'h':
            kwargs = {'hours': quantity}
            unit = 'hr'
        else:
            raise ValueError("Malformed input")
        obj = super(DateFrequency, cls).__new__(cls, **kwargs) 
        obj.quantity = quantity
        obj.unit = unit
        return obj
        
    @classmethod    
    def _parse_input_string(cls, s):
        match = re.match(r"(?P<quantity>\d+)[ _]*(?P<unit>[a-zA-Z]+)", s)
        if match:
            quantity = int(match.group('quantity'))
            unit = match.group('unit')
        else:
            quantity = 1
            if s in ['yearly', 'year', 'y', 'annually', 'annual', 'ann']:
                unit = 'yr'
            elif s in ['seasonally', 'seasonal', 'season']:      
                unit = 'se'
            elif s in ['monthly', 'month', 'mon', 'mo']:      
                unit = 'mo'
            elif s in ['weekly', 'week', 'wk', 'w']:
                unit = 'wk'
            elif s in ['daily', 'day', 'd', 'diurnal', 'diurnally']:
                unit = 'dy' 
            elif s in ['hourly', 'hour', 'hr', 'h']:
                unit = 'hr' 
            else:
                raise ValueError("Malformed input {}".format(s))
        return (quantity, unit)

    def format_local(self):
        if self.unit == 'hr':
            return self.format()
        else:
            assert self.quantity == 1
            _local_dict = {
                'mo': 'mon',
                'da': 'day',
            }
            return _local_dict[self.unit]

    def format_frepp(self):
        # weekly not used in frepp
        assert self.quantity == 1
        _frepp_dict = {
            'yr': 'annual',
            'se': 'seasonal',
            'mo': 'monthly',
            'da': 'daily',
            'hr': 'hourly'
        }
        return _frepp_dict[self.unit]

    def format(self):
        # conversion? only hr and yr used
        return "{}{}".format(self.quantity, self.unit)
    __str__ = format

    def __repr__(self):
        return "DateFrequency('{}')".format(self)

    def __eq__(self, other):
        # Note: only want to match labels, don't want '24hr' == '1day'
        if isinstance(other, DateFrequency):
            return (self.quantity == other.quantity) and (self.unit == other.unit)
        else:
            return super(DateFrequency, self).__eq__(other)

    def __ne__(self, other):
        return (not self.__eq__(other)) # more foolproof
