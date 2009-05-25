from django.utils.dateformat import format   
from datetime import datetime, timedelta
import sys
import math
from django.conf import settings
from time import mktime

FROM_GMT = -5
TZ_OFFSET = 60 * 60 * FROM_GMT

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
    for i in range(0, num_labels):
        if i % skip != 0:
            label_list[i] = ''    
    return skip

def compute_bin(timestamp, start_date, end_date, increment):
    ts = int(mktime(timestamp.timetuple())) + TZ_OFFSET
    start_ts = int(mktime(start_date.timetuple())) + TZ_OFFSET    
    end_ts = int(mktime(end_date.timetuple())) + TZ_OFFSET
    #interval = (end_ts - start_ts) / (num_slots - 1)
    return (ts - start_ts) / timedelta_to_seconds(increment)

def round_up_to_nearest_ten(value):
    return value + (10 - value % 10)

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
    if title is None:
        title = "Camels per second"

    dates = [d for d in datetimeIterator(start_date, end_date, increment)]    

    ## build values and bins
    labels = []    
    data_totals = []
    data_adds = []
    data_subs = []

    # generate labels, empty result array
    for d in dates: 
        labels.append(format(d, settings.DATE_FORMAT))
        data_totals.append(0)
        data_adds.append(0)
        data_subs.append(0)
    
    ops = ['adds',]
    if sub_queryset:
        ops.append('subs')
    
    def get_data(qs, value_field, datetime_field, start_date, end_date, increment, data ):
        hw = -sys.maxint # highwater mark
        lw = sys.maxint # lowwater mark
        for model in qs:
            value = 1
            if value_field is not None:
                value = getattr(model, value_field)
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
    xgrid_scale = float(skip) / (len(labels) - 1) * 100

    chart = {'size':'%ix%i' % (chart_width, chart_height), 
             'title': title, 
             'hw': data_hw, 
             'labels': labels, 
             'data': normalize_data(data_totals, data_hw),
             'ygrid': ygrid_scale,
             'xgrid': xgrid_scale }
    return labels, data_totals, data_adds, data_subs, chart