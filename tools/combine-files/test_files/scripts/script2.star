def process(metric):
    metric.tags["processed_by"] = "script2"
    return metric

