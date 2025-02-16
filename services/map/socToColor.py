import matplotlib.colors as mcolors

def soc_to_color(soc: float) -> str:
    """Map SOC to a gradient color (green → red)"""
    cmap = mcolors.LinearSegmentedColormap.from_list("soc", ["green", "yellow", "red"])
    return mcolors.to_hex(cmap(1 - soc/100))
