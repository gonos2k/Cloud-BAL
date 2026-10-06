"""Preserve unrelated NetCDF groups when rewriting a root-level fixture."""


def copy_groups(source, target):
    for name, original in source.groups.items():
        group = target.createGroup(name)
        group.setncatts({key: original.getncattr(key) for key in original.ncattrs()})
        for key, dimension in original.dimensions.items():
            group.createDimension(key, None if dimension.isunlimited() else len(dimension))
        for key, variable in original.variables.items():
            attributes = {attr: variable.getncattr(attr) for attr in variable.ncattrs()}
            output = group.createVariable(key, variable.datatype, variable.dimensions,
                                          fill_value=attributes.pop("_FillValue", False))
            output.setncatts(attributes)
            output[...] = variable[:]
        copy_groups(original, group)
