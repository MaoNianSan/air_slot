def parameter_grid(parameters):
    keys=tuple(parameters);rows=[{}]
    for key in keys:rows=[{**row,key:value} for row in rows for value in parameters[key]]
    return tuple(rows)
