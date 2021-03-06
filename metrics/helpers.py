from django.utils.dateformat import format   
from datetime import datetime, timedelta
import sys
import math
from django.conf import settings
from time import mktime

# FROM_GMT = -5
# TZ_OFFSET = 60 * 60 * FROM_GMT

def timedelta_to_seconds(td):
    return  td.seconds + td.days * 60 * 60 * 24

def normalize_data(data_list, high_water):
    return [(float(p) / high_water) * 100 if p is not 0 else 0.00001 for p in data_list]

def datetimeIterator(from_date, to_date, increment=timedelta(days=1)):
    """
    Generator for dates from from_date to to_date, increment can be any valid increment from timedelta
    """
    assert from_date is not None and to_date is not None
    while from_date <= to_date:
        yield from_date
        from_date = from_date + increment

def processLabels(label_list, chart_width):
    """ handle labels to make sure they don't draw over each other 
    returns the number of gap between drawn labels, modifies input 
    label_list and clears labels that occlude
    """
    label_width_guess = 100
    fit_labels = chart_width / label_width_guess
    num_labels = len(label_list)
    skip = num_labels / fit_labels
    # must skip x out of y labels to avoid overdrawing
    if skip != 0:
        for i in range(0, num_labels):
            if i % skip != 0:
                label_list[i] = ''    
    return skip

def compute_bin(timestamp, start_date, end_date, increment):
    if type(timestamp) is float or type(timestamp) is int:
        ts = int(timestamp) # + TZ_OFFSET # already a timestamp
    else:
        ts = int(mktime(timestamp.timetuple())) # + TZ_OFFSET
    start_ts = int(mktime(start_date.timetuple())) # + TZ_OFFSET    
    end_ts = int(mktime(end_date.timetuple())) # + TZ_OFFSET
    #interval = (end_ts - start_ts) / (num_slots - 1)
    return (ts - start_ts) / timedelta_to_seconds(increment)

def round_up_to_nearest_ten(value):
    return value + (10 - value % 10)


def date_label_format(start_date, end_date, timestamp):
    """ Transform a date into a string """
    if (end_date - start_date) < timedelta(hours=36):
        return '%s:00' % str(timestamp.hour)
    else:
        return format(timestamp, 'j M')

    
class Dataseries(object): 
    """
    Represent some simple information about a data series.  
    """
    def __init__(self, size):
        self.data = [0 for x in range(0, size)]
        self.hw = -sys.maxint
        self.lw = sys.maxint
    
    
def multiline_chart(raw_ds_iter, start_date, end_date, increment, title='', chart_width=500, chart_height=300):    
    """
    Input 
      raw_ds_iter: iterable object containing 1+ dataseries, each data series is a list containing datetime,value tuples: 
        series_iterable = (series1, series2, ...)
        series = [(datetime, 100), (datetime, 200), ...]
      start_date, end_date = datetime objects defining boundaries
      increment = timedelta increments used for binning.  Usually an hour or a day.  
    """
    assert start_date < end_date 
    
    # determines the number of bins
    dates = [d for d in datetimeIterator(start_date, end_date, increment)]
    # build the labels based on the number of bins
    labels = [] 
    for d in dates: 
        labels.append(date_label_format(start_date, end_date, d))

    def build_data(raw_ds, start_date, end_date, increment):
        series = Dataseries(len(dates))
        for timestamp, val in raw_ds:            
            # determine which bin we should be going in... 
            bin = compute_bin(timestamp, start_date, end_date, increment)
            series.data[bin] += val
            
            # set high and low water marks
            series.hw = series.data[bin] if series.data[bin] > series.hw else series.hw
            series.lw = series.data[bin] if series.data[bin] < series.lw else series.lw
        return series     

    series_ls = [build_data(raw, start_date, end_date, increment) for raw in raw_ds_iter]

    chart_hw = -sys.maxint
    chart_lw = sys.maxint
    for series in series_ls:
        chart_hw = series.hw if series.hw > chart_hw else chart_hw
        chart_lw = series.lw if series.lw < chart_lw else chart_lw

    ## Here we do some fudging ;) add a buffer of 25% and round to nearest 10
    buff = .25
    add_to_hw = round_up_to_nearest_ten(int(buff * chart_hw))
    chart_hw = round_up_to_nearest_ten(chart_hw) + add_to_hw

    ## y-grid scales # TODO: this can be made to do something more dynamic and intelligent?
    factor = int((len(str(chart_hw)) - 1))
    factor = 1 if factor < 1 else factor
    ygrid_scale = ((math.pow(10, factor) / 2) / chart_hw) * 100
    ## prevent label overdrawing
    skip = processLabels(labels, chart_width) 
    ## x-grid scale
    if skip == 0:
        skip = 1
    xgrid_scale = float(skip) / (len(labels) - 1) * 100

    chart = {'size':'%ix%i' % (chart_width, chart_height), 
             'title': title, 
             'hw': chart_hw, 
             'labels': labels, 
             'ygrid': ygrid_scale,
             'xgrid': xgrid_scale }
    for i, s in enumerate(series_ls):
        chart['data' + str(i)] = normalize_data(s.data, chart_hw)
        
    return labels, chart

    
def generic_stats(add_queryset, datetime_field, start_date, end_date, 
                  increment, value_field=None, title=None, sub_queryset=None, chart_width=500, chart_height=300):
    """
    Produce a chart and lists suitable for embedding into a table of stats based on 
    a single value of the specified queryset.  

    add_queryset: The queryset which adds to the totals
    datetime_field: the model's field which will be used to bin the values, ex: created_at
    start_date: the date to start binning
    end_date: the date to end binning
    increment: timedelta object specifying time intervals for binning
    sub_queryset: (optional) queryset which subtracts from the totals
    value_field: (optional) the model's field which is to be measured, 'None' just counts number of objects measured inside of each increment
    chart_width: (optional) width of output chart
    chart_height: (optional) height of output chart

    output: list of date labels, list of data total values, list of adds, list of removes, renderable chart object
    """
    assert start_date < end_date

    dates = [d for d in datetimeIterator(start_date, end_date, increment)]    

    ## build values and bins
    labels = []    
    data_totals = []
    data_adds = []
    data_subs = []
    
    # generate labels, empty result array
    for d in dates: 
        labels.append(date_label_format(start_date, end_date, d))
        data_totals.append(0)
        data_adds.append(0)
        data_subs.append(0)
    
    if len(labels):
        labels[0] = ''
        
    ops = ['adds',]
    if sub_queryset:
        ops.append('subs')
    
    def get_data(qs, value_field, datetime_field, start_date, end_date, increment, data ):
        hw = -sys.maxint # highwater mark
        lw = sys.maxint # lowwater mark
        for model in qs:
            value = 1
            if value_field is not None:
                if isinstance(model, dict):                    
                    value = model.get(value_field, 0)
                else:
                    value = getattr(model, value_field)
            
            if isinstance(model, dict):
                timestamp = model.get(datetime_field)
            else:
                timestamp = getattr(model, datetime_field)	
            
            # determine which bin we should be going in... 
            bin = compute_bin(timestamp, start_date, end_date, increment)
            data[bin] += value
            # set high and low water marks
            hw = data[bin] if data[bin] > hw else hw
            lw = data[bin] if data[bin] < lw else lw
        return hw, lw
    
    data_adds_hw, data_adds_lw = get_data(add_queryset, value_field, datetime_field, start_date, end_date, increment, data_adds)
    if sub_queryset:
        _, _ = get_data(sub_queryset, value_field, datetime_field, start_date, end_date, increment, data_subs)
        # need to compute totals, hw, lw
        data_hw = -sys.maxint # highwater mark
        data_lw = sys.maxint # lowwater mark
        for bin in range(0, len(data_totals)): 
            data_totals[bin] = data_adds[bin] - data_subs[bin]
            data_hw = data_totals[bin] if data_totals[bin] > data_hw else data_hw
            data_lw = data_totals[bin] if data_totals[bin] < data_lw else data_lw
    else:
        data_totals = data_adds
        data_hw = data_adds_hw
        data_lw = data_adds_lw
        
    ## add a buffer of 25% and round to nearest 10
    buff = .25
    add_to_hw = round_up_to_nearest_ten(int(buff * data_hw))
    data_hw = round_up_to_nearest_ten(data_hw) + add_to_hw

    ## y-grid scales # TODO: this can be made to do something more dynamic and intelligent?
    factor = int((len(str(data_hw)) - 1))
    factor = 1 if factor < 1 else factor
    ygrid_scale = ((math.pow(10, factor) / 2) / data_hw) * 100
    ## prevent label overdrawing
    skip = processLabels(labels, chart_width) 
    ## x-grid scale
    if skip == 0:
        skip = 1
    xgrid_scale = float(skip) / (len(labels) - 1) * 100

    chart = {'size':'%ix%i' % (chart_width, chart_height), 
             'title': title, 
             'hw': data_hw, 
             'labels': labels, 
             'data': normalize_data(data_totals, data_hw),
             'ygrid': ygrid_scale,
             'xgrid': xgrid_scale }
    return labels, data_totals, data_adds, data_subs, chart